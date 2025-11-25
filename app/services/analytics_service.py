"""
Serviço de analytics com queries otimizadas e cache
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from uuid import UUID
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, extract, case
from sqlalchemy.sql import text
from app.models.receipt import Receipt
from app.models.receipt_item import ReceiptItem
from app.models.product import Product
from app.models.category import Category
from app.models.analytics_cache import AnalyticsCache

logger = logging.getLogger(__name__)


def get_monthly_summary(
    db: Session,
    user_id: UUID,
    year: int,
    month: int,
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    Retorna resumo mensal de gastos do usuário.
    Usa cache se disponível.
    
    Args:
        db: Sessão do banco de dados
        user_id: ID do usuário
        year: Ano
        month: Mês (1-12)
        use_cache: Se deve usar cache
        
    Returns:
        Dict com total_mes, total_por_categoria, top_10_itens, variacao_vs_mes_anterior
    """
    month_key = f"{year}-{month:02d}"
    
    # Verificar cache
    if use_cache:
        cache = db.query(AnalyticsCache).filter(
            and_(
                AnalyticsCache.user_id == user_id,
                AnalyticsCache.month == month_key
            )
        ).first()
        
        if cache:
            logger.info(f"Using cached analytics for {month_key}")
            return cache.data
    
    # Calcular dados
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)
    
    # Total do mês
    total_mes_result = db.query(
        func.sum(Receipt.total_value).label('total')
    ).filter(
        and_(
            Receipt.user_id == user_id,
            Receipt.emitted_at >= start_date,
            Receipt.emitted_at < end_date
        )
    ).scalar()
    
    total_mes = float(total_mes_result) if total_mes_result else 0.0
    
    # Total por categoria
    total_por_categoria = db.query(
        Category.name,
        func.sum(ReceiptItem.total_price).label('total')
    ).join(
        Product, ReceiptItem.product_id == Product.id
    ).join(
        Category, Product.category_id == Category.id
    ).join(
        Receipt, ReceiptItem.receipt_id == Receipt.id
    ).filter(
        and_(
            Receipt.user_id == user_id,
            Receipt.emitted_at >= start_date,
            Receipt.emitted_at < end_date
        )
    ).group_by(
        Category.name
    ).all()
    
    total_por_categoria_dict = {
        cat_name: float(total) 
        for cat_name, total in total_por_categoria
    }
    
    # Top 10 itens
    top_items = db.query(
        ReceiptItem.description,
        func.sum(ReceiptItem.quantity).label('total_quantity'),
        func.sum(ReceiptItem.total_price).label('total_spent'),
        func.count(ReceiptItem.id).label('purchase_count')
    ).join(
        Receipt, ReceiptItem.receipt_id == Receipt.id
    ).filter(
        and_(
            Receipt.user_id == user_id,
            Receipt.emitted_at >= start_date,
            Receipt.emitted_at < end_date
        )
    ).group_by(
        ReceiptItem.description
    ).order_by(
        func.sum(ReceiptItem.total_price).desc()
    ).limit(10).all()
    
    top_10_itens = [
        {
            "description": item.description,
            "total_quantity": float(item.total_quantity),
            "total_spent": float(item.total_spent),
            "purchase_count": item.purchase_count
        }
        for item in top_items
    ]
    
    # Variação vs mês anterior
    prev_month = month - 1
    prev_year = year
    if prev_month == 0:
        prev_month = 12
        prev_year = year - 1
    
    prev_start = datetime(prev_year, prev_month, 1)
    if prev_month == 12:
        prev_end = datetime(prev_year + 1, 1, 1)
    else:
        prev_end = datetime(prev_year, prev_month + 1, 1)
    
    prev_total_result = db.query(
        func.sum(Receipt.total_value).label('total')
    ).filter(
        and_(
            Receipt.user_id == user_id,
            Receipt.emitted_at >= prev_start,
            Receipt.emitted_at < prev_end
        )
    ).scalar()
    
    prev_total = float(prev_total_result) if prev_total_result else 0.0
    
    variacao_vs_mes_anterior = 0.0
    if prev_total > 0:
        variacao_vs_mes_anterior = ((total_mes - prev_total) / prev_total) * 100
    
    result = {
        "total_mes": total_mes,
        "total_por_categoria": total_por_categoria_dict,
        "top_10_itens": top_10_itens,
        "variacao_vs_mes_anterior": round(variacao_vs_mes_anterior, 2),
        "month": month_key
    }
    
    # Salvar no cache (atualizar se já existir)
    if use_cache:
        existing_cache = db.query(AnalyticsCache).filter(
            and_(
                AnalyticsCache.user_id == user_id,
                AnalyticsCache.month == month_key
            )
        ).first()
        
        if existing_cache:
            existing_cache.data = result
        else:
            cache = AnalyticsCache(
                user_id=user_id,
                month=month_key,
                data=result
            )
            db.add(cache)
        
        db.commit()
        logger.info(f"Cached analytics for {month_key}")
    
    return result


def get_top_items(
    db: Session,
    user_id: UUID,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Retorna os itens mais comprados pelo usuário.
    
    Args:
        db: Sessão do banco de dados
        user_id: ID do usuário
        limit: Número máximo de itens a retornar
        
    Returns:
        Lista de itens ordenados por total gasto
    """
    top_items = db.query(
        ReceiptItem.description,
        func.sum(ReceiptItem.quantity).label('total_quantity'),
        func.sum(ReceiptItem.total_price).label('total_spent'),
        func.avg(ReceiptItem.unit_price).label('avg_price'),
        func.count(ReceiptItem.id).label('purchase_count')
    ).join(
        Receipt, ReceiptItem.receipt_id == Receipt.id
    ).filter(
        Receipt.user_id == user_id
    ).group_by(
        ReceiptItem.description
    ).order_by(
        func.sum(ReceiptItem.total_price).desc()
    ).limit(limit).all()
    
    return [
        {
            "description": item.description,
            "total_quantity": float(item.total_quantity),
            "total_spent": float(item.total_spent),
            "avg_price": float(item.avg_price) if item.avg_price else 0.0,
            "purchase_count": item.purchase_count
        }
        for item in top_items
    ]


def compare_store_prices(
    db: Session,
    user_id: UUID,
    product_id: UUID
) -> Dict[str, Any]:
    """
    Compara preços de um produto em diferentes supermercados.
    
    Args:
        db: Sessão do banco de dados
        user_id: ID do usuário
        product_id: ID do produto
        
    Returns:
        Dict com preço médio por supermercado e menor preço encontrado
    """
    # Buscar produto
    product = db.query(Product).filter(Product.id == product_id).first()
    
    if not product:
        raise ValueError(f"Product not found: {product_id}")
    
    # Preço médio por supermercado
    store_prices = db.query(
        Receipt.store_name,
        func.avg(ReceiptItem.unit_price).label('avg_price'),
        func.min(ReceiptItem.unit_price).label('min_price'),
        func.max(ReceiptItem.unit_price).label('max_price'),
        func.count(ReceiptItem.id).label('purchase_count')
    ).join(
        Receipt, ReceiptItem.receipt_id == Receipt.id
    ).filter(
        and_(
            Receipt.user_id == user_id,
            ReceiptItem.product_id == product_id,
            Receipt.store_name.isnot(None),
            Receipt.store_name != ''
        )
    ).group_by(
        Receipt.store_name
    ).order_by(
        func.avg(ReceiptItem.unit_price).asc()
    ).all()
    
    preco_medio_por_supermercado = [
        {
            "store_name": store.store_name,
            "avg_price": float(store.avg_price),
            "min_price": float(store.min_price),
            "max_price": float(store.max_price),
            "purchase_count": store.purchase_count
        }
        for store in store_prices
    ]
    
    # Menor preço encontrado
    menor_preco_result = db.query(
        func.min(ReceiptItem.unit_price).label('min_price')
    ).join(
        Receipt, ReceiptItem.receipt_id == Receipt.id
    ).filter(
        and_(
            Receipt.user_id == user_id,
            ReceiptItem.product_id == product_id
        )
    ).scalar()
    
    menor_preco = float(menor_preco_result) if menor_preco_result else None
    
    # Buscar loja com menor preço
    menor_preco_store = None
    if menor_preco:
        menor_preco_item = db.query(
            Receipt.store_name,
            ReceiptItem.unit_price,
            Receipt.emitted_at
        ).join(
            Receipt, ReceiptItem.receipt_id == Receipt.id
        ).filter(
            and_(
                Receipt.user_id == user_id,
                ReceiptItem.product_id == product_id,
                ReceiptItem.unit_price == menor_preco_result
            )
        ).order_by(
            Receipt.emitted_at.desc()
        ).first()
        
        if menor_preco_item:
            menor_preco_store = menor_preco_item.store_name
    
    return {
        "product_id": str(product_id),
        "product_name": product.normalized_name,
        "preco_medio_por_supermercado": preco_medio_por_supermercado,
        "menor_preco_encontrado": menor_preco,
        "loja_menor_preco": menor_preco_store,
        "total_comparacoes": len(preco_medio_por_supermercado)
    }

