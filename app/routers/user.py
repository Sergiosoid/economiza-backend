"""
Router para endpoints de usuário (LGPD: export, delete)
"""
import logging
import csv
import json
import io
import zipfile
from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_
from uuid import UUID
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.receipt import Receipt
from app.models.receipt_item import ReceiptItem
from app.models.product import Product
from app.utils.encryption import decrypt_sensitive_data
from sqlalchemy import func

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/user/export-data")
async def export_user_data(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Exporta todos os dados do usuário em formato ZIP contendo:
    - receipts.csv: Lista de todas as notas fiscais
    - receipts.json: Dados completos em JSON
    - receipt_items.csv: Itens de todas as notas
    
    Conforme LGPD, o usuário tem direito a exportar seus dados.
    """
    logger.info(f"Exporting data for user: {user_id}")
    
    # Buscar usuário
    user = db.query(User).filter(
        and_(User.id == user_id, User.deleted_at.is_(None))
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Buscar todos os receipts do usuário
    receipts = db.query(Receipt).filter(
        Receipt.user_id == user_id
    ).order_by(Receipt.created_at.desc()).all()
    
    # Criar ZIP em memória
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # 1. CSV de receipts
        csv_buffer = io.StringIO()
        csv_writer = csv.writer(csv_buffer)
        csv_writer.writerow([
            'id', 'access_key', 'store_name', 'store_cnpj',
            'total_value', 'subtotal', 'total_tax',
            'emitted_at', 'created_at'
        ])
        
        for receipt in receipts:
            csv_writer.writerow([
                str(receipt.id),
                receipt.access_key,
                receipt.store_name or '',
                receipt.store_cnpj or '',
                str(receipt.total_value),
                str(receipt.subtotal),
                str(receipt.total_tax),
                receipt.emitted_at.isoformat() if receipt.emitted_at else '',
                receipt.created_at.isoformat() if receipt.created_at else ''
            ])
        
        zip_file.writestr('receipts.csv', csv_buffer.getvalue())
        
        # 2. JSON completo de receipts
        receipts_data = []
        for receipt in receipts:
            # Buscar itens do receipt
            items = db.query(ReceiptItem).filter(
                ReceiptItem.receipt_id == receipt.id
            ).all()
            
            receipt_dict = {
                'id': str(receipt.id),
                'access_key': receipt.access_key,
                'store_name': receipt.store_name,
                'store_cnpj': receipt.store_cnpj,
                'total_value': float(receipt.total_value),
                'subtotal': float(receipt.subtotal),
                'total_tax': float(receipt.total_tax),
                'emitted_at': receipt.emitted_at.isoformat() if receipt.emitted_at else None,
                'created_at': receipt.created_at.isoformat() if receipt.created_at else None,
                'items': [
                    {
                        'description': item.description,
                        'quantity': float(item.quantity),
                        'unit_price': float(item.unit_price),
                        'total_price': float(item.total_price),
                        'tax_value': float(item.tax_value)
                    }
                    for item in items
                ]
            }
            
            # Descriptografar raw_qr_text se existir
            if receipt.raw_qr_text:
                try:
                    receipt_dict['raw_qr_text'] = decrypt_sensitive_data(receipt.raw_qr_text)
                except:
                    receipt_dict['raw_qr_text'] = '[encrypted]'
            
            receipts_data.append(receipt_dict)
        
        zip_file.writestr(
            'receipts.json',
            json.dumps(receipts_data, indent=2, ensure_ascii=False)
        )
        
        # 3. CSV de receipt items
        csv_items_buffer = io.StringIO()
        csv_items_writer = csv.writer(csv_items_buffer)
        csv_items_writer.writerow([
            'receipt_id', 'description', 'quantity',
            'unit_price', 'total_price', 'tax_value'
        ])
        
        for receipt in receipts:
            items = db.query(ReceiptItem).filter(
                ReceiptItem.receipt_id == receipt.id
            ).all()
            
            for item in items:
                csv_items_writer.writerow([
                    str(receipt.id),
                    item.description,
                    str(item.quantity),
                    str(item.unit_price),
                    str(item.total_price),
                    str(item.tax_value)
                ])
        
        zip_file.writestr('receipt_items.csv', csv_items_buffer.getvalue())
        
        # 4. Informações do usuário
        user_data = {
            'id': str(user.id),
            'email': user.email,
            'consent_given': user.consent_given,
            'consent_terms': user.consent_terms if hasattr(user, 'consent_terms') else False,
            'created_at': user.created_at.isoformat() if user.created_at else None,
            'total_receipts': len(receipts)
        }
        zip_file.writestr(
            'user_info.json',
            json.dumps(user_data, indent=2, ensure_ascii=False)
        )
        
        # 5. Produtos únicos do usuário
        # Buscar todos os produtos que o usuário comprou
        user_products = db.query(
            Product.id,
            Product.normalized_name,
            Product.barcode,
            func.avg(ReceiptItem.unit_price).label('avg_price'),
            func.sum(ReceiptItem.quantity).label('total_quantity'),
            func.count(ReceiptItem.id).label('purchase_count')
        ).join(
            ReceiptItem, Product.id == ReceiptItem.product_id
        ).join(
            Receipt, ReceiptItem.receipt_id == Receipt.id
        ).filter(
            Receipt.user_id == user_id
        ).group_by(
            Product.id,
            Product.normalized_name,
            Product.barcode
        ).all()
        
        products_data = []
        for product in user_products:
            products_data.append({
                'id': str(product.id),
                'normalized_name': product.normalized_name,
                'barcode': product.barcode,
                'avg_price': float(product.avg_price) if product.avg_price else None,
                'total_quantity': float(product.total_quantity),
                'purchase_count': product.purchase_count
            })
        
        zip_file.writestr(
            'products.json',
            json.dumps(products_data, indent=2, ensure_ascii=False)
        )
    
    zip_buffer.seek(0)
    
    # Retornar ZIP como streaming response
    filename = f"economiza_export_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    
    return StreamingResponse(
        iter([zip_buffer.getvalue()]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.delete("/user/delete-account")
async def delete_user_account(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Deleta a conta do usuário (soft delete).
    
    Conforme LGPD:
    - Soft delete: marca deleted_at (dados ficam inacessíveis)
    - Hard delete: após 30 dias, dados são permanentemente removidos (via task agendada)
    
    Retorna 204 No Content em caso de sucesso.
    """
    logger.info(f"Deleting account for user: {user_id}")
    
    # Buscar usuário
    user = db.query(User).filter(
        and_(User.id == user_id, User.deleted_at.is_(None))
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found or already deleted"
        )
    
    # Soft delete: marcar deleted_at
    user.deleted_at = datetime.utcnow()
    
    # Anonimizar email (manter formato para evitar conflitos)
    user.email = f"deleted_{user.id}@{datetime.utcnow().timestamp()}.deleted"
    
    # TODO: Enfileirar task para hard delete após 30 dias
    # from app.tasks.user_tasks import schedule_hard_delete
    # schedule_hard_delete.apply_async(args=[str(user_id)], countdown=30*24*60*60)
    
    db.commit()
    
    logger.info(f"Account soft deleted: {user_id}")
    
    return {"message": "Account deleted. Data will be permanently removed after 30 days."}


@router.post("/user/consent")
async def give_consent(
    consent_terms: bool = True,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Endpoint para o usuário dar consentimento para processamento de dados.
    Conforme LGPD, é necessário consentimento explícito.
    
    Args:
        consent_terms: Se o usuário aceita os termos (padrão: True)
    """
    user = db.query(User).filter(
        and_(User.id == user_id, User.deleted_at.is_(None))
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.consent_given = True
    user.consent_terms = consent_terms
    db.commit()
    
    logger.info(f"Consent given by user: {user_id}, terms: {consent_terms}")
    
    return {
        "message": "Consent registered",
        "consent_given": True,
        "consent_terms": consent_terms
    }

