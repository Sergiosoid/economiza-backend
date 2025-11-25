"""
Router para endpoints de receipts (notas fiscais)
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
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


@router.post(
    "/receipts/scan",
    response_model=ScanReceiptResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Receipt salvo com sucesso"},
        400: {"description": "QR code inválido"},
        409: {"description": "Receipt já existe"},
        500: {"description": "Erro do provider"},
    }
)
async def scan_receipt(
    request: ScanReceiptRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Endpoint para escanear QR code de nota fiscal e salvar no banco.
    
    Fluxo completo:
    1. Recebe qr_text
    2. Extrai chave de acesso ou URL
    3. Consulta a nota fiscal em um provedor externo
    4. Parseia a nota (itens, loja, impostos, total)
    5. Salva em receipts, products e receipt_items
    6. Retorna receipt_id
    """
    logger.info("qr_received", extra={"user_id": str(user_id), "qr_length": len(request.qr_text)})
    
    try:
        # 1. Extrair chave de acesso ou URL
        try:
            url, access_key = extract_key_or_url(request.qr_text)
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
        
        # 4. Parsear nota
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
