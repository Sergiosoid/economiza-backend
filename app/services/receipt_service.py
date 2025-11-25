"""
Service para gerenciar receipts (notas fiscais)
"""
import logging
import hashlib
from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.receipt import Receipt
from app.models.receipt_item import ReceiptItem
from app.models.product import Product
from app.utils.encryption import encrypt_sensitive_data
from app.services.product_matcher import get_or_create_product_from_item

logger = logging.getLogger(__name__)


def get_or_create_product(
    db: Session,
    description: str,
    barcode: Optional[str] = None,
    category_id: Optional[UUID] = None
) -> Product:
    """
    Cria ou recupera um produto usando o product_matcher.
    Mantém compatibilidade com a interface antiga.
    """
    item = {
        "description": description,
        "barcode": barcode,
        "category_id": category_id
    }
    
    product_id = get_or_create_product_from_item(db, item)
    
    # Buscar produto criado/encontrado
    product = db.query(Product).filter(Product.id == product_id).first()
    
    # Atualizar barcode se fornecido e não existir
    if barcode and product and not product.barcode:
        product.barcode = barcode
        db.commit()
        db.refresh(product)
    
    return product


def check_receipt_exists(
    db: Session,
    user_id: UUID,
    access_key: str
) -> Optional[Receipt]:
    """
    Verifica se um receipt já existe (idempotência por access_key).
    """
    return db.query(Receipt).filter(
        Receipt.user_id == user_id,
        Receipt.access_key == access_key
    ).first()


def check_qr_text_exists(
    db: Session,
    qr_text: str
) -> Optional[Receipt]:
    """
    Verifica se um QR text já foi processado (idempotência por hash do QR).
    """
    qr_hash = hashlib.sha256(qr_text.encode()).hexdigest()
    
    # Buscar por raw_qr_text (precisa descriptografar para comparar)
    # Por simplicidade, vamos usar hash direto no banco
    # Em produção, pode criar uma coluna qr_hash
    receipts = db.query(Receipt).all()
    for receipt in receipts:
        try:
            from app.utils.encryption import decrypt_sensitive_data
            decrypted = decrypt_sensitive_data(receipt.raw_qr_text)
            if hashlib.sha256(decrypted.encode()).hexdigest() == qr_hash:
                return receipt
        except:
            continue
    
    return None


def save_receipt(
    db: Session,
    user_id: UUID,
    parsed_data: dict,
    raw_qr_text: str,
    xml_raw: Optional[str] = None
) -> Receipt:
    """
    Salva um receipt no banco de dados com todos os itens.
    """
    try:
        # Criptografar dados sensíveis
        encrypted_qr = encrypt_sensitive_data(raw_qr_text)
        encrypted_xml = encrypt_sensitive_data(xml_raw) if xml_raw else None
        
        # Criar receipt
        receipt = Receipt(
            user_id=user_id,
            access_key=parsed_data["access_key"],
            raw_qr_text=encrypted_qr,
            total_value=parsed_data["total_value"],
            subtotal=parsed_data["subtotal"],
            total_tax=parsed_data["total_tax"],
            emitted_at=parsed_data["emitted_at"],
            store_name=parsed_data["store_name"],
            store_cnpj=parsed_data["store_cnpj"],
        )
        db.add(receipt)
        db.flush()  # Para obter o ID
        
        # Criar produtos e itens
        for item_data in parsed_data["items"]:
            # Criar ou buscar produto
            product = get_or_create_product(
                db=db,
                description=item_data["description"],
                barcode=item_data.get("barcode"),
            )
            
            # Criar receipt item
            receipt_item = ReceiptItem(
                receipt_id=receipt.id,
                product_id=product.id,
                description=item_data["description"],
                quantity=item_data["quantity"],
                unit_price=item_data["unit_price"],
                total_price=item_data["total_price"],
                tax_value=item_data["tax_value"],
            )
            db.add(receipt_item)
        
        db.commit()
        db.refresh(receipt)
        
        logger.info(f"receipt_saved: {receipt.id}")
        return receipt
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving receipt: {e}")
        raise

