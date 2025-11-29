"""
Router para endpoints de desenvolvimento (seed de dados fake)
Só funciona se DEV_MODE=True
"""
import logging
import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from uuid import UUID
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.config import settings
from app.models.receipt import Receipt
from app.models.receipt_item import ReceiptItem
from app.models.product import Product
from app.services.product_matcher import normalize_name, get_or_create_product_from_item
from app.utils.encryption import encrypt_sensitive_data

logger = logging.getLogger(__name__)
router = APIRouter()

bearer_scheme = HTTPBearer(auto_error=False)


class ForceCreateItem(BaseModel):
    name: str = Field(..., description="Nome do produto")
    quantity: float = Field(..., gt=0, description="Quantidade")
    unit_price: float = Field(..., gt=0, description="Preço unitário")
    category: Optional[str] = Field(None, description="Categoria do produto")


class ForceCreateRequest(BaseModel):
    store_name: str = Field(..., description="Nome da loja")
    store_cnpj: str = Field(..., description="CNPJ da loja")
    emitted_at: datetime = Field(..., description="Data de emissão da nota")
    items: List[ForceCreateItem] = Field(..., min_length=1, description="Lista de itens")
    override: bool = Field(False, description="Permitir sobrescrever nota existente")


class ForceCreateResponse(BaseModel):
    status: str
    receipt_id: UUID


def _generate_fake_access_key() -> str:
    """Gera uma chave de acesso fake de 44 dígitos."""
    # Gerar 44 dígitos aleatórios
    import random
    return ''.join([str(random.randint(0, 9)) for _ in range(44)])


def _check_dev_mode() -> None:
    """Valida se DEV_MODE está habilitado."""
    if not settings.DEV_MODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available in development mode (DEV_MODE=true)"
        )


def _check_dev_token(cred: Optional[HTTPAuthorizationCredentials], request: Request) -> None:
    """Valida se o token é 'test' (apenas para dev)."""
    token = None
    if cred:
        token = cred.credentials
    else:
        # Tentar pegar do header diretamente
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif auth_header:
            token = auth_header.strip()
    
    if token != "test":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication. This endpoint only accepts 'Bearer test' in development mode"
        )


@router.post(
    "/receipts/force-create",
    status_code=status.HTTP_200_OK,
    response_model=ForceCreateResponse,
    responses={
        200: {"description": "Receipt criado com sucesso"},
        401: {"description": "Token de autenticação inválido"},
        403: {"description": "Endpoint disponível apenas em modo desenvolvimento"},
        409: {"description": "Receipt já existe (use override=true para sobrescrever)"},
    }
)
async def force_create_receipt(
    request: Request,
    create_request: ForceCreateRequest,
    db: Session = Depends(get_db),
    cred: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    user_id: UUID = Depends(get_current_user)
):
    """
    Endpoint de desenvolvimento para criar notas fiscais fake diretamente no banco.
    
    **ATENÇÃO**: Este endpoint só funciona se:
    - DEV_MODE=True
    - Authorization: Bearer test
    
    Útil para testes de analytics e IA.
    """
    # Validar DEV_MODE
    _check_dev_mode()
    
    # Validar token de desenvolvimento
    _check_dev_token(cred, request)
    
    logger.info(f"Force creating receipt for user: {user_id}")
    
    # Gerar access_key fake
    access_key = _generate_fake_access_key()
    
    # Verificar se já existe (a menos que override=true)
    existing_receipt = db.query(Receipt).filter(
        Receipt.user_id == user_id,
        Receipt.access_key == access_key
    ).first()
    
    if existing_receipt and not create_request.override:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Receipt with access_key {access_key} already exists. Use override=true to replace it."
        )
    
    # Se existe e override=true, deletar itens antigos
    if existing_receipt and create_request.override:
        logger.info(f"Overriding existing receipt: {existing_receipt.id}")
        # Deletar itens antigos (cascade já faz isso, mas vamos garantir)
        db.query(ReceiptItem).filter(ReceiptItem.receipt_id == existing_receipt.id).delete()
        db.delete(existing_receipt)
        db.flush()
    
    try:
        # Calcular totais
        subtotal = sum(item.unit_price * item.quantity for item in create_request.items)
        total_tax = subtotal * 0.05  # 5% fixo
        total_value = subtotal + total_tax
        
        # Criar raw_qr_text fake
        fake_qr_text = f"https://nfce.fazenda.fake/{access_key}"
        
        # Criar receipt
        receipt = Receipt(
            user_id=user_id,
            access_key=access_key,
            raw_qr_text=encrypt_sensitive_data(fake_qr_text),
            total_value=total_value,
            subtotal=subtotal,
            total_tax=total_tax,
            emitted_at=create_request.emitted_at,
            store_name=create_request.store_name,
            store_cnpj=create_request.store_cnpj,
        )
        db.add(receipt)
        db.flush()  # Para obter o ID
        
        # Criar produtos e itens
        for item_data in create_request.items:
            # Normalizar nome do produto
            normalized = normalize_name(item_data.name)
            
            # Criar ou buscar produto usando product_matcher
            product_id = get_or_create_product_from_item(
                db=db,
                item={
                    "description": item_data.name,
                    "barcode": None,
                    "category_id": None  # TODO: buscar categoria por nome se necessário
                }
            )
            
            # Calcular valores do item
            item_total_price = item_data.unit_price * item_data.quantity
            item_tax_value = item_total_price * 0.05  # 5% fixo
            
            # Criar receipt item
            receipt_item = ReceiptItem(
                receipt_id=receipt.id,
                product_id=product_id,
                description=item_data.name,
                quantity=item_data.quantity,
                unit_price=item_data.unit_price,
                total_price=item_total_price,
                tax_value=item_tax_value,
            )
            db.add(receipt_item)
        
        db.commit()
        db.refresh(receipt)
        
        logger.info(f"Receipt force created: {receipt.id} (access_key: {access_key})")
        
        return ForceCreateResponse(
            status="created",
            receipt_id=receipt.id
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error force creating receipt: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating receipt: {str(e)}"
        )

