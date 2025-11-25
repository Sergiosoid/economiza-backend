"""
Tasks do Celery para processamento de receipts em background
"""
import logging
import json
from uuid import UUID
from app.celery_app import celery_app
from app.database import SessionLocal
from app.services.receipt_parser import parse_note
from app.services.receipt_service import save_receipt

logger = logging.getLogger(__name__)


@celery_app.task(name="process_receipt_task", bind=True, max_retries=3)
def process_receipt_task(
    self,
    user_id: str,
    raw_note: dict,
    qr_text: str,
    access_key: str
):
    """
    Task para processar e salvar receipt em background.
    
    Args:
        user_id: UUID do usuário (como string)
        raw_note: Dados brutos da nota (dict)
        qr_text: Texto do QR code
        access_key: Chave de acesso da nota
    """
    db = SessionLocal()
    try:
        logger.info(f"Processing receipt task: user_id={user_id}, access_key={access_key[:10]}...")
        
        # Parsear nota
        parsed_data = parse_note(raw_note)
        if not parsed_data.get("access_key") and access_key:
            parsed_data["access_key"] = access_key
        
        # Preparar XML raw
        xml_raw = None
        if isinstance(raw_note, dict):
            xml_raw = json.dumps(raw_note)
        elif isinstance(raw_note, str):
            xml_raw = raw_note
        
        # Salvar no banco
        receipt = save_receipt(
            db=db,
            user_id=UUID(user_id),
            parsed_data=parsed_data,
            raw_qr_text=qr_text,
            xml_raw=xml_raw
        )
        
        logger.info(f"Receipt processed successfully: {receipt.id}")
        return {
            "status": "completed",
            "receipt_id": str(receipt.id)
        }
        
    except Exception as e:
        logger.error(f"Error processing receipt task: {e}", exc_info=True)
        # Retry com backoff exponencial
        raise self.retry(exc=e, countdown=2 ** self.request.retries)
    finally:
        db.close()

