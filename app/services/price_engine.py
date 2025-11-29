"""
Price Engine - Serviço para estimar preços de itens em listas de compras
baseado no histórico de compras do usuário.
"""
import logging
from decimal import Decimal
from typing import Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from uuid import UUID
from app.models.product import Product
from app.models.receipt_item import ReceiptItem
from app.models.shopping_list import ShoppingListItem
import unicodedata
import re

logger = logging.getLogger(__name__)


def normalize_text(s: str) -> str:
    """
    Normaliza texto removendo acentos, convertendo para minúsculas
    e removendo caracteres especiais.
    
    Args:
        s: String a normalizar
        
    Returns:
        String normalizada
    """
    if not s:
        return ""
    
    # Remover acentos
    nfd = unicodedata.normalize('NFD', s)
    text = ''.join(char for char in nfd if unicodedata.category(char) != 'Mn')
    
    # Converter para minúsculas
    text = text.lower()
    
    # Remover caracteres especiais, manter apenas letras, números e espaços
    text = re.sub(r'[^a-z0-9\s]', '', text)
    
    # Remover espaços múltiplos
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def match_product(description: str, db: Session, user_id: UUID) -> Optional[Product]:
    """
    Busca produto correspondente usando match textual.
    
    Lógica:
    1. Buscar em products.normalized_name usando ILIKE
    2. Buscar em receipt_items.description usando similaridade
    3. Pontuação simples por substring
    4. Retornar a melhor correspondência
    
    Args:
        description: Descrição do item
        db: Sessão do banco de dados
        user_id: ID do usuário para filtrar histórico
        
    Returns:
        Product correspondente ou None
    """
    if not description:
        return None
    
    normalized_desc = normalize_text(description)
    words = normalized_desc.split()
    
    if not words:
        return None
    
    # Estratégia 1: Buscar produtos que o usuário já comprou (via receipt_items -> receipt)
    from app.models.receipt import Receipt
    
    products_from_history = (
        db.query(Product)
        .join(ReceiptItem)
        .join(Receipt)
        .filter(Receipt.user_id == user_id)
        .distinct()
        .all()
    )
    
    best_match = None
    best_score = 0.0
    
    # Buscar em produtos do histórico do usuário
    for product in products_from_history:
        normalized_product = normalize_text(product.normalized_name)
        
        # Calcular score por substring
        score = 0.0
        
        # Match exato
        if normalized_product == normalized_desc:
            score = 1.0
        # Match parcial (produto contém descrição ou vice-versa)
        elif normalized_desc in normalized_product or normalized_product in normalized_desc:
            score = 0.8
        # Match por palavras
        else:
            product_words = normalized_product.split()
            matching_words = sum(1 for word in words if word in product_words)
            if matching_words > 0:
                score = matching_words / max(len(words), len(product_words))
        
        if score > best_score:
            best_score = score
            best_match = product
    
    # Se encontrou match com score >= 0.5, retornar
    if best_match and best_score >= 0.5:
        logger.debug(f"Product match: '{description}' -> '{best_match.normalized_name}' (score: {best_score})")
        return best_match
    
    # Estratégia 2: Buscar em receipt_items.description diretamente do usuário
    # e tentar encontrar product_id mais comum
    receipt_items = (
        db.query(ReceiptItem)
        .join(Receipt)
        .filter(
            Receipt.user_id == user_id,
            ReceiptItem.description.ilike(f"%{description}%")
        )
        .all()
    )
    
    if receipt_items:
        # Contar product_id mais frequente
        product_counts = {}
        for item in receipt_items:
            if item.product_id:
                product_counts[item.product_id] = product_counts.get(item.product_id, 0) + 1
        
        if product_counts:
            most_common_product_id = max(product_counts, key=product_counts.get)
            product = db.query(Product).filter(Product.id == most_common_product_id).first()
            if product:
                logger.debug(f"Product match via receipt_items: '{description}' -> '{product.normalized_name}'")
                return product
    
    return None


def get_latest_price(product_id: UUID, db: Session, user_id: UUID) -> Optional[Decimal]:
    """
    Busca o preço unitário mais recente de um produto.
    
    Calcula: preço unitário = total_price / quantity normalizada
    
    Args:
        product_id: ID do produto
        db: Sessão do banco de dados
        user_id: ID do usuário para filtrar histórico
        
    Returns:
        Preço unitário mais recente ou None
    """
    # Buscar receipt_item mais recente do produto
    # Assumindo que ReceiptItem tem relação com Receipt que tem user_id
    from app.models.receipt import Receipt
    
    latest_item = db.query(ReceiptItem).join(Receipt).filter(
        ReceiptItem.product_id == product_id,
        Receipt.user_id == user_id
    ).order_by(desc(ReceiptItem.created_at)).first()
    
    if not latest_item or not latest_item.quantity or latest_item.quantity <= 0:
        return None
    
    # Calcular preço unitário
    try:
        unit_price = Decimal(str(latest_item.total_price)) / Decimal(str(latest_item.quantity))
        return unit_price
    except (ValueError, ZeroDivisionError):
        logger.warning(f"Erro ao calcular preço unitário para product_id={product_id}")
        return None


def estimate_item_price(
    item: ShoppingListItem,
    db: Session,
    user_id: UUID
) -> Dict[str, Optional[Decimal] | float]:
    """
    Estima preço de um item da lista de compras.
    
    Args:
        item: ShoppingListItem a estimar
        db: Sessão do banco de dados
        user_id: ID do usuário
        
    Returns:
        {
            "unit_price_estimate": Decimal | None,
            "total_price_estimate": Decimal | None,
            "confidence": float
        }
    """
    unit_price_estimate = None
    total_price_estimate = None
    confidence = 0.0
    
    product = None
    
    # Estratégia 1: Se item.product_id existe, usar esse produto
    if item.product_id:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product:
            confidence = 1.0
            logger.debug(f"Using product_id for item: {item.description}")
    
    # Estratégia 2: Se não encontrou, fazer match textual
    if not product:
        product = match_product(item.description, db, user_id)
        if product:
            # Ajustar confidence baseado na qualidade do match
            normalized_desc = normalize_text(item.description)
            normalized_product = normalize_text(product.normalized_name)
            
            if normalized_product == normalized_desc:
                confidence = 0.8
            elif normalized_desc in normalized_product or normalized_product in normalized_desc:
                confidence = 0.7
            else:
                confidence = 0.5
            logger.debug(f"Matched product via text for item: {item.description}")
    
    # Se encontrou produto, buscar preço mais recente
    if product:
        latest_price = get_latest_price(product.id, db, user_id)
        
        if latest_price:
            # Normalizar unidades
            # latest_price está em "unidade base" do receipt_item
            # item.quantity está em "unidade base" do item (já normalizada)
            # Precisamos garantir que estão na mesma unidade
            
            # Por enquanto, assumir que latest_price já está na unidade correta
            # (receipt_items.quantity já deve estar normalizada)
            unit_price_estimate = latest_price
            
            # Calcular total
            try:
                total_price_estimate = unit_price_estimate * Decimal(str(item.quantity))
            except (ValueError, TypeError):
                logger.warning(f"Erro ao calcular total_price_estimate para item {item.id}")
                total_price_estimate = None
        else:
            # Produto encontrado mas sem histórico de preço
            confidence = confidence * 0.5  # Reduzir confidence
            logger.debug(f"Product found but no price history: {item.description}")
    else:
        # Nenhum produto encontrado
        confidence = 0.2  # Fallback
        logger.debug(f"No product match found for: {item.description}")
    
    return {
        "unit_price_estimate": unit_price_estimate,
        "total_price_estimate": total_price_estimate,
        "confidence": confidence
    }

