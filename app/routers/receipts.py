"""
Router para endpoints de receipts (notas fiscais)
"""
import logging
import json
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from uuid import UUID
from app.database import get_db
from app.dependencies import get_current_user
from app.utils.qr_extractor import extract_key_or_url
from app.services.provider_client import fetch_by_url, fetch_by_key, ProviderError
from app.services.receipt_parser import parse_note
from app.services.receipt_service import (
    check_receipt_exists,
    save_receipt
)
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.tasks.receipt_tasks import process_receipt_task
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Tamanho limite para processar em background (em bytes de JSON serializado)
BACKGROUND_PROCESSING_THRESHOLD = 50000  # ~50KB


class ScanReceiptRequest(BaseModel):
    qr_text: str = Field(..., min_length=1, max_length=2000, description="Texto do QR code da nota fiscal")
    
    @field_validator('qr_text')
    @classmethod
    def validate_qr_text(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("qr_text não pode ser vazio")
        if len(v) > 2000:
            raise ValueError("qr_text não pode ter mais de 2000 caracteres")
        return v.strip()


class ScanReceiptResponse(BaseModel):
    receipt_id: UUID
    status: str


class ScanReceiptProcessingResponse(BaseModel):
    status: str
    task_id: str
    message: str


def _should_process_in_background(raw_note: dict) -> bool:
    """
    Decide se o processamento deve ser feito em background.
    Considera tamanho do XML/JSON e complexidade.
    """
    try:
        # Serializar para estimar tamanho
        serialized = json.dumps(raw_note)
        size = len(serialized.encode('utf-8'))
        
        # Se for muito grande, processar em background
        if size > BACKGROUND_PROCESSING_THRESHOLD:
            logger.info(f"Note size ({size} bytes) exceeds threshold, queuing for background processing")
            return True
        
        # Se tiver muitos itens, também processar em background
        if isinstance(raw_note, dict):
            # Tentar contar itens
            items_count = 0
            if "items" in raw_note:
                items_count = len(raw_note["items"])
            elif "det" in raw_note:
                det = raw_note["det"]
                items_count = len(det) if isinstance(det, list) else 1
            
            if items_count > 50:
                logger.info(f"Note has {items_count} items, queuing for background processing")
                return True
        
        return False
    except Exception:
        # Em caso de erro, processar em background por segurança
        return True


@router.post(
    "/receipts/scan",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Receipt salvo com sucesso"},
        202: {"description": "Receipt em processamento em background"},
        400: {"description": "QR code inválido"},
        409: {"description": "Receipt já existe"},
        429: {"description": "Rate limit excedido"},
        500: {"description": "Erro do provider"},
    }
)
async def scan_receipt(
    request: Request,
    scan_request: ScanReceiptRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Endpoint para escanear QR code de nota fiscal e salvar no banco.
    
    Para notas grandes ou complexas, o processamento é feito em background
    e retorna 202 Accepted com task_id.
    
    Rate limiting: 30 req/min por IP, 60 req/min por usuário.
    
    Fluxo completo:
    1. Recebe qr_text
    2. Extrai chave de acesso ou URL
    3. Consulta a nota fiscal em um provedor externo
    4. Decide se processa síncrono ou assíncrono
    5. Parseia e salva (ou enfileira)
    6. Retorna receipt_id ou task_id
    """
    # Rate limiting é aplicado automaticamente pelo middleware slowapi
    # Limites: 30 req/min por IP (padrão), 60 req/min por usuário (aplicado via decorator se necessário)
    
    logger.info("qr_received", extra={"user_id": str(user_id), "qr_length": len(scan_request.qr_text)})
    
    try:
        # 1. Extrair chave de acesso ou URL
        try:
            url, access_key = extract_key_or_url(scan_request.qr_text)
        except ValueError as e:
            logger.warning(f"invalid_qr_code: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid qr code"
            )
        
        # 2. Verificar idempotência (se temos access_key)
        if access_key:
            existing_receipt = check_receipt_exists(db, user_id, access_key)
            if existing_receipt:
                logger.info(f"receipt_already_exists: {existing_receipt.id}")
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content={
                        "detail": "receipt already exists",
                        "receipt_id": str(existing_receipt.id)
                    }
                )
        
        # 3. Consultar provider
        try:
            if url:
                raw_note = fetch_by_url(url)
            else:
                raw_note = fetch_by_key(access_key)
            logger.info("provider_fetch_ok")
        except ProviderError as e:
            logger.error(f"provider_fetch_fail: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="provider error"
            )
        
        # 4. Decidir se processa em background
        if _should_process_in_background(raw_note):
            # Enfileirar task
            task = process_receipt_task.delay(
                user_id=str(user_id),
                raw_note=raw_note,
                qr_text=scan_request.qr_text,
                access_key=access_key or ""
            )
            
            logger.info(f"Receipt queued for background processing: task_id={task.id}")
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "status": "processing",
                    "task_id": task.id,
                    "message": "Receipt está sendo processado em background"
                }
            )
        
        # 5. Processar síncrono (notas pequenas)
        try:
            parsed_data = parse_note(raw_note)
            # Garantir que access_key está presente
            if not parsed_data.get("access_key") and access_key:
                parsed_data["access_key"] = access_key
        except ValueError as e:
            logger.error(f"parse_error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid qr code: {str(e)}"
            )
        
        # 6. Salvar no banco
        try:
            xml_raw = None
            if isinstance(raw_note, dict):
                xml_raw = json.dumps(raw_note)
            elif isinstance(raw_note, str):
                xml_raw = raw_note
            
            receipt = save_receipt(
                db=db,
                user_id=user_id,
                parsed_data=parsed_data,
                raw_qr_text=scan_request.qr_text,
                xml_raw=xml_raw
            )
            
            logger.info(f"receipt_saved: {receipt.id}")
            return ScanReceiptResponse(
                receipt_id=receipt.id,
                status="saved"
            )
            
        except Exception as e:
            logger.error(f"Error saving receipt: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro ao salvar nota fiscal"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro inesperado: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno do servidor"
        )
