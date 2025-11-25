"""
Router para endpoints de receipts (notas fiscais)
"""
import re
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from uuid import UUID
from app.database import get_db
from app.dependencies import get_current_user
from app.services.provider_client import fetch_note_by_url, fetch_note_by_key
from app.services.receipt_parser import parse_note
from app.services.receipt_service import (
    check_receipt_exists,
    check_qr_text_exists,
    save_receipt
)

logger = logging.getLogger(__name__)
router = APIRouter()


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


class ScanReceiptConflictResponse(BaseModel):
    detail: str
    receipt_id: UUID


@router.post(
    "/receipts/scan",
    response_model=ScanReceiptResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Receipt salvo com sucesso"},
        202: {"description": "Receipt em processamento"},
        400: {"description": "Erro de validação"},
        409: {"description": "Receipt já existe"},
        500: {"description": "Erro interno"},
    }
)
async def scan_receipt(
    request: ScanReceiptRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Endpoint para escanear QR code de nota fiscal e salvar no banco.
    
    Fluxo:
    1. Valida qr_text
    2. Extrai URL ou chave de acesso
    3. Verifica idempotência
    4. Busca nota do provider
    5. Parseia dados
    6. Salva no banco
    """
    logger.info("scan_received", extra={"user_id": str(user_id), "qr_length": len(request.qr_text)})
    
    try:
        # 1. Validação e extração
        url = None
        access_key = None
        
        # Verificar se contém URL
        url_pattern = r'https?://[^\s]+'
        url_match = re.search(url_pattern, request.qr_text)
        if url_match:
            url = url_match.group(0)
            logger.info(f"URL encontrada: {url[:50]}...")
        else:
            # Buscar chave de acesso (44 dígitos)
            key_pattern = r'\d{44}'
            key_match = re.search(key_pattern, request.qr_text)
            if key_match:
                access_key = key_match.group(0)
                logger.info(f"Chave de acesso encontrada: {access_key[:10]}...")
        
        if not url and not access_key:
            logger.warning("Nenhuma URL ou chave de acesso encontrada")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="QR text não contém URL válida nem chave de acesso (44 dígitos)"
            )
        
        # 2. Verificar idempotência
        if access_key:
            existing_receipt = check_receipt_exists(db, user_id, access_key)
            if existing_receipt:
                logger.info(f"Receipt já existe: {existing_receipt.id}")
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content={
                        "detail": "Receipt already exists",
                        "receipt_id": str(existing_receipt.id)
                    }
                )
        
        # Verificar por QR text hash
        existing_by_qr = check_qr_text_exists(db, request.qr_text)
        if existing_by_qr:
            logger.info(f"QR text já processado: {existing_by_qr.id}")
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "detail": "Receipt already exists",
                    "receipt_id": str(existing_by_qr.id)
                }
            )
        
        # 3. Buscar nota do provider
        try:
            if url:
                raw_note = fetch_note_by_url(url)
            else:
                raw_note = fetch_note_by_key(access_key)
        except Exception as e:
            logger.error(f"Erro ao buscar nota do provider: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao buscar nota fiscal: {str(e)}"
            )
        
        # 4. Parsear nota
        try:
            parsed_data = parse_note(raw_note)
            # Garantir que access_key está presente
            if not parsed_data.get("access_key") and access_key:
                parsed_data["access_key"] = access_key
        except Exception as e:
            logger.error(f"parse_error: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Erro ao parsear nota fiscal: {str(e)}"
            )
        
        # 5. Salvar no banco
        try:
            xml_raw = None
            if isinstance(raw_note, dict):
                import json
                xml_raw = json.dumps(raw_note)
            elif isinstance(raw_note, str):
                xml_raw = raw_note
            
            receipt = save_receipt(
                db=db,
                user_id=user_id,
                parsed_data=parsed_data,
                raw_qr_text=request.qr_text,
                xml_raw=xml_raw
            )
            
            logger.info(f"receipt_saved: {receipt.id}")
            return ScanReceiptResponse(
                receipt_id=receipt.id,
                status="saved"
            )
            
        except Exception as e:
            logger.error(f"Erro ao salvar receipt: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao salvar nota fiscal: {str(e)}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro inesperado: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno do servidor"
        )

