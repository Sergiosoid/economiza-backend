"""
Serviço de IA para sugestões de economia
"""
import logging
from typing import List, Dict, Any, Optional
from uuid import UUID
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from app.models.receipt import Receipt
from app.models.receipt_item import ReceiptItem
from app.models.product import Product
from app.services.product_matcher import normalize_name, fuzzy_match_name

logger = logging.getLogger(__name__)


def generate_savings_suggestions(
    db: Session,
    user_id: UUID,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Gera sugestões de economia para o usuário.
    
    Identifica os top produtos mais caros comprados frequentemente,
    busca alternativas mais baratas e calcula economia estimada.
    
    Args:
        db: Sessão do banco de dados
        user_id: ID do usuário
        limit: Número máximo de sugestões (padrão: 5)
        
    Returns:
        Lista de sugestões com produto atual, alternativa, economia estimada e rationale
    """
    suggestions = []
    
    # 1. Identificar top produtos mais caros comprados frequentemente
    # Buscar produtos com maior gasto total E frequência de compra
    top_expensive_items = db.query(
        ReceiptItem.product_id,
        ReceiptItem.description,
        func.avg(ReceiptItem.unit_price).label('avg_price'),
        func.sum(ReceiptItem.quantity).label('total_quantity'),
        func.sum(ReceiptItem.total_price).label('total_spent'),
        func.count(ReceiptItem.id).label('purchase_count')
    ).join(
        Receipt, ReceiptItem.receipt_id == Receipt.id
    ).filter(
        and_(
            Receipt.user_id == user_id,
            ReceiptItem.product_id.isnot(None)
        )
    ).group_by(
        ReceiptItem.product_id,
        ReceiptItem.description
    ).having(
        func.count(ReceiptItem.id) >= 2  # Comprado pelo menos 2 vezes
    ).order_by(
        func.avg(ReceiptItem.unit_price).desc(),  # Mais caro primeiro
        func.sum(ReceiptItem.total_price).desc()  # Depois por total gasto
    ).limit(limit * 2).all()  # Buscar mais para ter opções
    
    if not top_expensive_items:
        logger.info(f"No expensive items found for user {user_id}")
        return []
    
    # 2. Para cada produto caro, buscar alternativas mais baratas
    for item in top_expensive_items[:limit]:
        product_id = item.product_id
        current_description = item.description
        current_avg_price = float(item.avg_price)
        purchase_count = item.purchase_count
        total_quantity = float(item.total_quantity)
        
        # Buscar produto no banco
        current_product = db.query(Product).filter(Product.id == product_id).first()
        if not current_product:
            continue
        
        # Normalizar nome para buscar similares
        normalized_name = normalize_name(current_description)
        
        # Buscar produtos similares (excluindo o atual)
        similar_products = db.query(
            Product,
            func.avg(ReceiptItem.unit_price).label('avg_price'),
            func.min(ReceiptItem.unit_price).label('min_price'),
            func.count(ReceiptItem.id).label('purchase_count')
        ).join(
            ReceiptItem, Product.id == ReceiptItem.product_id
        ).join(
            Receipt, ReceiptItem.receipt_id == Receipt.id
        ).filter(
            and_(
                Product.id != product_id,
                Receipt.user_id == user_id
            )
        ).group_by(
            Product.id
        ).all()
        
        # Filtrar produtos similares usando fuzzy matching
        alternative_product = None
        alternative_price = None
        best_match_score = 0
        
        for similar_product, avg_price, min_price, count in similar_products:
            # Verificar se produtos são similares usando fuzzy matching
            # Comparar nomes normalizados diretamente
            if _are_similar(normalized_name, similar_product.normalized_name, threshold=0.7):
                avg_price_float = float(avg_price) if avg_price else 0.0
                min_price_float = float(min_price) if min_price else 0.0
                
                # Preferir produto com preço médio menor
                if avg_price_float < current_avg_price * 0.9:  # Pelo menos 10% mais barato
                    # Calcular score de similaridade
                    from rapidfuzz import fuzz
                    score = fuzz.WRatio(normalized_name, similar_product.normalized_name) / 100.0
                    
                    if score > best_match_score:
                        best_match_score = score
                        alternative_product = similar_product
                        alternative_price = avg_price_float
        
        # Se não encontrou alternativa similar, buscar por categoria ou nome parcial
        if not alternative_product:
            # Buscar produtos na mesma categoria com preço menor
            if current_product.category_id:
                category_alternatives = db.query(
                    Product,
                    func.avg(ReceiptItem.unit_price).label('avg_price')
                ).join(
                    ReceiptItem, Product.id == ReceiptItem.product_id
                ).join(
                    Receipt, ReceiptItem.receipt_id == Receipt.id
                ).filter(
                    and_(
                        Product.category_id == current_product.category_id,
                        Product.id != product_id,
                        Receipt.user_id == user_id
                    )
                ).group_by(
                    Product.id
                ).having(
                    func.avg(ReceiptItem.unit_price) < current_avg_price * 0.9
                ).order_by(
                    func.avg(ReceiptItem.unit_price).asc()
                ).first()
                
                if category_alternatives:
                    alternative_product, alternative_price = category_alternatives
                    alternative_price = float(alternative_price) if alternative_price else 0.0
        
        # Se encontrou alternativa, calcular economia
        if alternative_product and alternative_price:
            # Calcular economia por unidade
            savings_per_unit = current_avg_price - alternative_price
            
            # Estimar compras mensais (baseado na frequência histórica)
            # Assumir que compra mensalmente se comprou pelo menos 2 vezes
            monthly_purchases = max(1, purchase_count / 3)  # Estimativa conservadora
            
            # Quantidade média por compra
            avg_quantity_per_purchase = total_quantity / purchase_count if purchase_count > 0 else 1
            
            # Economia mensal estimada
            monthly_savings = savings_per_unit * monthly_purchases * avg_quantity_per_purchase
            
            # Gerar rationale
            rationale = _generate_rationale(
                current_description,
                alternative_product.normalized_name,
                current_avg_price,
                alternative_price,
                monthly_savings,
                savings_per_unit
            )
            
            suggestions.append({
                "current_product": {
                    "id": str(product_id),
                    "name": current_description,
                    "normalized_name": normalized_name,
                    "avg_price": current_avg_price,
                    "purchase_count": purchase_count
                },
                "alternative_product": {
                    "id": str(alternative_product.id),
                    "name": alternative_product.normalized_name,
                    "avg_price": alternative_price
                },
                "savings": {
                    "per_unit": round(savings_per_unit, 2),
                    "monthly_estimated": round(monthly_savings, 2),
                    "annual_estimated": round(monthly_savings * 12, 2),
                    "percentage": round((savings_per_unit / current_avg_price) * 100, 1)
                },
                "rationale": rationale
            })
    
    # Ordenar por economia mensal estimada (maior primeiro)
    suggestions.sort(key=lambda x: x["savings"]["monthly_estimated"], reverse=True)
    
    return suggestions


def _are_similar(name1: str, name2: str, threshold: float = 0.7) -> bool:
    """
    Verifica se dois nomes normalizados são similares.
    """
    if not name1 or not name2:
        return False
    
    from rapidfuzz import fuzz
    
    # Calcular similaridade
    similarity = fuzz.WRatio(name1, name2) / 100.0
    
    return similarity >= threshold


def _generate_rationale(
    current_name: str,
    alternative_name: str,
    current_price: float,
    alternative_price: float,
    monthly_savings: float,
    savings_per_unit: float
) -> str:
    """
    Gera texto explicativo sugerindo a substituição.
    """
    savings_percent = (savings_per_unit / current_price) * 100
    
    rationale = f"Substitua '{current_name}' por '{alternative_name}'. "
    rationale += f"Você economiza R$ {savings_per_unit:.2f} por unidade "
    rationale += f"({savings_percent:.1f}% mais barato). "
    
    if monthly_savings > 0:
        rationale += f"Com base no seu histórico de compras, isso pode gerar uma economia estimada de R$ {monthly_savings:.2f} por mês "
        rationale += f"(R$ {monthly_savings * 12:.2f} por ano)."
    
    return rationale

