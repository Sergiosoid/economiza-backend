"""
Serviço de recomendações de economia usando IA básica.
Analisa gastos do usuário e sugere alternativas mais baratas.
"""
import logging
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.models.receipt_item import ReceiptItem
from app.models.receipt import Receipt
from app.models.product import Product
from app.services.product_matcher import normalize_name, fuzzy_match_name

logger = logging.getLogger(__name__)


def generate_savings_suggestions(
    db: Session,
    user_id: UUID,
    limit: int = 3
) -> List[Dict[str, Any]]:
    """
    Gera sugestões de economia baseadas nos gastos do usuário.
    
    Algoritmo:
    1. Analisa top produtos mais comprados pelo usuário (últimos 90 dias)
    2. Para cada produto, busca alternativas mais baratas no catálogo
    3. Calcula economia estimada por mês
    4. Retorna sugestões ordenadas por economia potencial
    
    Args:
        db: Sessão do banco de dados
        user_id: ID do usuário
        limit: Número máximo de sugestões a retornar
        
    Returns:
        Lista de sugestões com rationale e economia estimada
    """
    logger.info(f"Generating savings suggestions for user: {user_id}")
    
    # 1. Buscar top produtos mais comprados (últimos 90 dias)
    cutoff_date = datetime.utcnow() - timedelta(days=90)
    
    top_items = db.query(
        ReceiptItem.description,
        func.sum(ReceiptItem.quantity).label('total_quantity'),
        func.avg(ReceiptItem.unit_price).label('avg_unit_price'),
        func.sum(ReceiptItem.total_price).label('total_spent'),
        func.count(ReceiptItem.id).label('purchase_count')
    ).join(
        Receipt, ReceiptItem.receipt_id == Receipt.id
    ).filter(
        and_(
            Receipt.user_id == user_id,
            Receipt.created_at >= cutoff_date
        )
    ).group_by(
        ReceiptItem.description
    ).order_by(
        func.sum(ReceiptItem.total_price).desc()
    ).limit(10).all()
    
    if not top_items:
        logger.info(f"No purchase history found for user: {user_id}")
        return []
    
    suggestions = []
    
    # 2. Para cada produto top, buscar alternativas mais baratas
    for item in top_items:
        description = item.description
        avg_price = float(item.avg_unit_price)
        total_quantity = float(item.total_quantity)
        purchase_count = item.purchase_count
        
        # Buscar produtos similares no catálogo
        alternative = _find_cheaper_alternative(
            db=db,
            product_name=description,
            current_price=avg_price,
            user_id=user_id
        )
        
        if alternative:
            # Calcular economia
            price_diff = avg_price - alternative['price']
            monthly_quantity = _estimate_monthly_quantity(total_quantity, purchase_count)
            monthly_savings = price_diff * monthly_quantity
            
            if monthly_savings > 0:
                suggestion = {
                    'current_product': description,
                    'current_price': round(avg_price, 2),
                    'suggested_product': alternative['name'],
                    'suggested_price': round(alternative['price'], 2),
                    'price_difference': round(price_diff, 2),
                    'monthly_quantity_estimate': round(monthly_quantity, 2),
                    'estimated_monthly_savings': round(monthly_savings, 2),
                    'rationale': _generate_rationale(
                        current_product=description,
                        suggested_product=alternative['name'],
                        price_diff=price_diff,
                        monthly_savings=monthly_savings
                    ),
                    'confidence': alternative.get('confidence', 0.8)
                }
                suggestions.append(suggestion)
    
    # Ordenar por economia estimada (maior primeiro)
    suggestions.sort(key=lambda x: x['estimated_monthly_savings'], reverse=True)
    
    # Retornar top N sugestões
    return suggestions[:limit]


def _find_cheaper_alternative(
    db: Session,
    product_name: str,
    current_price: float,
    user_id: UUID
) -> Optional[Dict[str, Any]]:
    """
    Busca um produto alternativo mais barato no catálogo.
    
    Args:
        db: Sessão do banco
        product_name: Nome do produto atual
        current_price: Preço atual do produto
        user_id: ID do usuário (para filtrar produtos já comprados)
        
    Returns:
        Dict com nome, preço e confiança da alternativa, ou None
    """
    # Normalizar nome do produto
    normalized = normalize_name(product_name)
    
    # Buscar todos os produtos no catálogo
    all_products = db.query(Product).all()
    
    if not all_products:
        return None
    
    # Buscar preços médios de cada produto (baseado em compras de todos os usuários)
    product_prices = {}
    
    for product in all_products:
        # Buscar preço médio deste produto
        avg_price_result = db.query(
            func.avg(ReceiptItem.unit_price)
        ).join(
            Receipt, ReceiptItem.receipt_id == Receipt.id
        ).filter(
            and_(
                ReceiptItem.product_id == product.id,
                ReceiptItem.description.ilike(f"%{product.normalized_name}%")
            )
        ).scalar()
        
        if avg_price_result:
            product_prices[product.id] = {
                'name': product.normalized_name,
                'price': float(avg_price_result)
            }
    
    # Buscar produtos similares usando fuzzy matching
    similar_products = []
    
    for product in all_products:
        # Verificar similaridade
        similarity = _calculate_similarity(normalized, product.normalized_name)
        
        if similarity >= 0.7:  # Threshold de similaridade
            # Buscar preço médio
            price_info = product_prices.get(product.id)
            
            if price_info:
                price = price_info['price']
                
                # Só considerar se for mais barato (pelo menos 5% mais barato)
                if price < current_price * 0.95:
                    similar_products.append({
                        'name': product.normalized_name,
                        'price': price,
                        'similarity': similarity,
                        'product_id': product.id
                    })
    
    if not similar_products:
        return None
    
    # Ordenar por preço (mais barato primeiro) e similaridade
    similar_products.sort(key=lambda x: (x['price'], -x['similarity']))
    
    # Retornar a melhor alternativa
    best = similar_products[0]
    
    return {
        'name': best['name'],
        'price': best['price'],
        'confidence': best['similarity']
    }


def _calculate_similarity(name1: str, name2: str) -> float:
    """
    Calcula similaridade entre dois nomes de produtos (0-1).
    """
    from rapidfuzz import fuzz
    
    # Usar WRatio para similaridade flexível
    similarity = fuzz.WRatio(name1, name2) / 100.0
    return similarity


def _estimate_monthly_quantity(total_quantity: float, purchase_count: int) -> float:
    """
    Estima quantidade mensal baseada no histórico de compras.
    
    Args:
        total_quantity: Quantidade total comprada nos últimos 90 dias
        purchase_count: Número de compras
        
    Returns:
        Quantidade estimada por mês
    """
    if purchase_count == 0:
        return 0.0
    
    # Média de quantidade por compra
    avg_per_purchase = total_quantity / purchase_count
    
    # Estimar frequência de compra (compras por mês)
    # Assumindo que 90 dias = 3 meses
    purchases_per_month = purchase_count / 3.0
    
    # Quantidade mensal estimada
    monthly_quantity = avg_per_purchase * purchases_per_month
    
    return monthly_quantity


def _generate_rationale(
    current_product: str,
    suggested_product: str,
    price_diff: float,
    monthly_savings: float
) -> str:
    """
    Gera uma explicação (rationale) para a sugestão.
    """
    percentage_savings = (price_diff / (price_diff + (price_diff * 0.1))) * 100 if price_diff > 0 else 0
    
    rationale = (
        f"Você compra '{current_product}' regularmente. "
        f"Encontramos '{suggested_product}' como alternativa similar, "
        f"que custa R$ {price_diff:.2f} menos por unidade. "
        f"Com base no seu histórico de compras, você pode economizar "
        f"aproximadamente R$ {monthly_savings:.2f} por mês fazendo essa troca."
    )
    
    return rationale

