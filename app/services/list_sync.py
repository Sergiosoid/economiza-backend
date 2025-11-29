"""
List Sync Service - Serviço para sincronizar listas de compras com notas fiscais
"""
import logging
from decimal import Decimal
from typing import Optional, Tuple, Dict, List
from sqlalchemy.orm import Session
from uuid import UUID
from app.models.shopping_list import ShoppingListItem
from app.models.receipt_item import ReceiptItem
from app.models.product import Product
import unicodedata
import re

logger = logging.getLogger(__name__)

# Tolerance values
PRICE_TOLERANCE_PERCENT = Decimal('2.0')
QUANTITY_TOLERANCE_PERCENT = Decimal('5.0')


def normalize_text(s: str) -> str:
    """
    Normaliza texto removendo acentos, convertendo para minúsculas
    e removendo caracteres especiais.
    Reutiliza lógica do price_engine.
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


def find_best_match_for_list_item(
    list_item: ShoppingListItem,
    receipt_items: List[ReceiptItem],
    db: Session,
    user_id: UUID
) -> Tuple[Optional[ReceiptItem], float]:
    """
    Encontra o melhor match para um item da lista entre os receipt_items.
    
    Estratégia (ordem de preferência):
    1. Se list_item.product_id existe: buscar receipt_item com mesmo product_id (score=1.0)
    2. Match exato de descrição (normalizada): score 0.95
    3. Match por substring: score 0.85
    4. Match por overlap de palavras: score = overlap_ratio (0..0.8)
    5. Caso contrário, sem match (None, score 0)
    
    Args:
        list_item: Item da lista de compras
        receipt_items: Lista de receipt_items disponíveis (não marcados como matched)
        db: Sessão do banco de dados
        user_id: ID do usuário
        
    Returns:
        Tuple (matched_receipt_item, score)
    """
    if not receipt_items:
        return None, 0.0
    
    best_match = None
    best_score = 0.0
    best_index = -1
    
    normalized_list_desc = normalize_text(list_item.description)
    list_words = set(normalized_list_desc.split())
    
    # Estratégia 1: Match por product_id
    if list_item.product_id:
        for idx, receipt_item in enumerate(receipt_items):
            if receipt_item.product_id == list_item.product_id:
                logger.debug(f"Match por product_id: {list_item.description} -> {receipt_item.description}")
                return receipt_item, 1.0
    
    # Estratégia 2-4: Match textual
    for idx, receipt_item in enumerate(receipt_items):
        normalized_receipt_desc = normalize_text(receipt_item.description)
        receipt_words = set(normalized_receipt_desc.split())
        
        score = 0.0
        
        # Match exato
        if normalized_list_desc == normalized_receipt_desc:
            score = 0.95
        # Match por substring
        elif normalized_list_desc in normalized_receipt_desc or normalized_receipt_desc in normalized_list_desc:
            score = 0.85
        # Match por overlap de palavras
        elif list_words and receipt_words:
            intersection = list_words.intersection(receipt_words)
            union = list_words.union(receipt_words)
            if union:
                overlap_ratio = len(intersection) / len(union)
                score = min(0.8, overlap_ratio * 0.8)
        
        if score > best_score:
            best_score = score
            best_match = receipt_item
            best_index = idx
    
    if best_match and best_score > 0:
        logger.debug(f"Match textual: {list_item.description} -> {best_match.description} (score: {best_score})")
        return best_match, best_score
    
    return None, 0.0


def normalize_quantity_to_base(quantity: Decimal, unit_code: str, unit_multiplier: int) -> Decimal:
    """
    Normaliza quantidade para a unidade base (menor unidade).
    
    Args:
        quantity: Quantidade na unidade especificada
        unit_code: Código da unidade (ex: 'kg', 'g', 'L', 'ml')
        unit_multiplier: Multiplicador para converter para unidade base
        
    Returns:
        Quantidade normalizada na unidade base
    """
    # Se já está na unidade base (multiplier = 1), retornar como está
    if unit_multiplier == 1:
        return quantity
    
    # Converter para unidade base
    # Ex: 5kg com multiplier=1000 -> 5000g
    return quantity * Decimal(str(unit_multiplier))


def compare_quantities_and_price(
    list_item: ShoppingListItem,
    receipt_item: ReceiptItem
) -> Dict:
    """
    Compara quantidades e preços entre item da lista e item da nota.
    
    Args:
        list_item: Item da lista de compras
        receipt_item: Item da nota fiscal
        
    Returns:
        Dict com planned_quantity, real_quantity, planned_unit_price, real_unit_price,
        planned_total, real_total, difference, difference_percent, flags
    """
    # Normalizar quantidades para mesma base
    # list_item.quantity já está na menor unidade (base)
    planned_quantity_base = Decimal(str(list_item.quantity))
    
    # receipt_item.quantity está na unidade do item (precisamos assumir que é a mesma base)
    # Por enquanto, assumimos que receipt_item.quantity já está normalizada
    real_quantity_base = Decimal(str(receipt_item.quantity))
    
    # Calcular preços unitários
    # list_item pode ter price_estimate, senão usar None
    planned_unit_price = Decimal(str(list_item.price_estimate)) if list_item.price_estimate else None
    
    # receipt_item: unit_price já está disponível
    real_unit_price = Decimal(str(receipt_item.unit_price))
    
    # Calcular totais
    if planned_unit_price:
        planned_total = planned_unit_price * planned_quantity_base
    else:
        planned_total = None
    
    real_total = Decimal(str(receipt_item.total_price))
    
    # Calcular diferença
    difference = None
    difference_percent = None
    
    if planned_total is not None:
        difference = real_total - planned_total
        if planned_total > 0:
            difference_percent = (difference / planned_total) * Decimal('100')
    
    # Flags
    price_higher = False
    price_lower = False
    quantity_different = False
    
    if planned_unit_price and real_unit_price:
        price_diff_percent = abs((real_unit_price - planned_unit_price) / planned_unit_price * Decimal('100'))
        if real_unit_price > planned_unit_price:
            price_higher = price_diff_percent > PRICE_TOLERANCE_PERCENT
        else:
            price_lower = price_diff_percent > PRICE_TOLERANCE_PERCENT
    
    if planned_quantity_base > 0:
        qty_diff_percent = abs((real_quantity_base - planned_quantity_base) / planned_quantity_base * Decimal('100'))
        quantity_different = qty_diff_percent > QUANTITY_TOLERANCE_PERCENT
    
    return {
        "planned_quantity": float(planned_quantity_base),
        "real_quantity": float(real_quantity_base),
        "planned_unit_price": float(planned_unit_price) if planned_unit_price else None,
        "real_unit_price": float(real_unit_price),
        "planned_total": float(planned_total) if planned_total else None,
        "real_total": float(real_total),
        "difference": float(difference) if difference is not None else None,
        "difference_percent": float(difference_percent) if difference_percent is not None else None,
        "price_higher": price_higher,
        "price_lower": price_lower,
        "quantity_different": quantity_different
    }


def build_item_comparison(
    list_item: ShoppingListItem,
    receipt_item: Optional[ReceiptItem],
    comparison_data: Optional[Dict] = None
) -> Dict:
    """
    Constrói objeto de comparação de item com status.
    
    Args:
        list_item: Item da lista
        receipt_item: Item da nota (pode ser None se não encontrado)
        comparison_data: Dados de comparação (se receipt_item existe)
        
    Returns:
        Dict com campos do ItemComparisonResponse incluindo status
    """
    status = "PLANNED_NOT_PURCHASED"
    
    if receipt_item and comparison_data:
        # Item foi encontrado na nota
        if not comparison_data["price_higher"] and not comparison_data["price_lower"] and not comparison_data["quantity_different"]:
            status = "PLANNED_AND_MATCHED"
        elif comparison_data["price_higher"]:
            status = "PRICE_HIGHER_THAN_EXPECTED"
        elif comparison_data["price_lower"]:
            status = "PRICE_LOWER_THAN_EXPECTED"
        elif comparison_data["quantity_different"]:
            status = "QUANTITY_DIFFERENT"
        else:
            status = "PLANNED_AND_MATCHED"
    elif receipt_item:
        # Receipt item sem dados de comparação (não deveria acontecer)
        status = "PLANNED_AND_MATCHED"
    
    return {
        "id": str(list_item.id),
        "description": list_item.description,
        "planned_quantity": comparison_data["planned_quantity"] if comparison_data else float(list_item.quantity),
        "planned_unit_code": list_item.unit_code,
        "real_quantity": comparison_data["real_quantity"] if comparison_data else None,
        "real_unit_code": None,  # Receipt items não têm unit_code armazenado
        "planned_unit_price": comparison_data["planned_unit_price"] if comparison_data else None,
        "real_unit_price": comparison_data["real_unit_price"] if comparison_data else None,
        "planned_total": comparison_data["planned_total"] if comparison_data else None,
        "real_total": comparison_data["real_total"] if comparison_data else None,
        "difference": comparison_data["difference"] if comparison_data else None,
        "difference_percent": comparison_data["difference_percent"] if comparison_data else None,
        "status": status
    }


def build_unplanned_item_comparison(receipt_item: ReceiptItem) -> Dict:
    """
    Constrói objeto de comparação para item da nota não planejado.
    
    Args:
        receipt_item: Item da nota que não foi encontrado na lista
        
    Returns:
        Dict com campos do ItemComparisonResponse com status PURCHASED_NOT_PLANNED
    """
    return {
        "id": None,
        "description": receipt_item.description,
        "planned_quantity": None,
        "planned_unit_code": None,
        "real_quantity": float(receipt_item.quantity),
        "real_unit_code": None,  # Receipt items não têm unit_code armazenado
        "planned_unit_price": None,
        "real_unit_price": float(receipt_item.unit_price),
        "planned_total": None,
        "real_total": float(receipt_item.total_price),
        "difference": None,
        "difference_percent": None,
        "status": "PURCHASED_NOT_PLANNED"
    }

