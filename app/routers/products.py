"""
Router para endpoints de produtos
"""
import logging
from typing import List
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from uuid import UUID
from pydantic import BaseModel
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.product import Product
from app.models.category import Category
from app.models.receipt_item import ReceiptItem

logger = logging.getLogger(__name__)
router = APIRouter()


class ProductListItem(BaseModel):
    id: UUID
    name: str
    category: str | None = None
    times_bought: int = 0
    avg_price: float | None = None


@router.get(
    "/list",
    response_model=List[ProductListItem],
    dependencies=[Depends(get_current_user)]
)
async def list_products(
    request: Request,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Lista todos os produtos com estatísticas de compra.
    
    Retorna:
    - id: ID do produto
    - name: Nome normalizado do produto
    - category: Nome da categoria (se houver)
    - times_bought: Quantidade de vezes que o produto foi comprado
    - avg_price: Preço médio do produto
    
    Ordenado por vezes comprado (desc) e nome (asc).
    """
    logger.info("Listing products")
    
    try:
        # Query usando SQLAlchemy ORM
        results = db.query(
            Product.id,
            Product.normalized_name,
            Category.name.label('category'),
            func.count(ReceiptItem.id).label('times_bought'),
            func.avg(ReceiptItem.unit_price).label('avg_price')
        ).outerjoin(
            Category, Product.category_id == Category.id
        ).outerjoin(
            ReceiptItem, ReceiptItem.product_id == Product.id
        ).group_by(
            Product.id,
            Product.normalized_name,
            Category.name
        ).order_by(
            func.count(ReceiptItem.id).desc(),
            Product.normalized_name.asc()
        ).all()
        
        logger.info(f"Products found: {len(results)}")
        
        # Converter resultados para o schema de resposta
        products = []
        for row in results:
            products.append(ProductListItem(
                id=row.id,
                name=row.normalized_name,
                category=row.category,
                times_bought=row.times_bought or 0,
                avg_price=float(row.avg_price) if row.avg_price else None
            ))
        
        return products
        
    except Exception as e:
        logger.error(f"Error listing products: {e}", exc_info=True)
        raise

