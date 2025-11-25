"""
Serviço para matching de produtos usando múltiplas estratégias:
- Match por código de barras
- Fuzzy matching com rapidfuzz
- Embedding matching com vector DB (opcional)
"""
import re
import unicodedata
import logging
from typing import Optional, List, Dict, Any
from uuid import UUID
from sqlalchemy.orm import Session
from rapidfuzz import process, fuzz
from app.models.product import Product

logger = logging.getLogger(__name__)

# Stopwords em português (comuns em nomes de produtos)
STOPWORDS = {
    'a', 'o', 'e', 'de', 'do', 'da', 'em', 'um', 'uma', 'para', 'com', 'por',
    'que', 'na', 'no', 'as', 'os', 'ao', 'pelo', 'pela', 'dos', 'das',
    'tipo', 'marca', 'sabor', 'sabor', 'unidade', 'un', 'pacote', 'pac',
    'caixa', 'cx', 'embalagem', 'emb'
}

# Modelo de embeddings (carregado sob demanda)
_embedding_model = None
_supabase_client = None


def normalize_name(text: str) -> str:
    """
    Normaliza o nome do produto:
    - lowercase
    - remove acentos
    - remove medidas, unidades e stopwords
    
    Args:
        text: Nome do produto
        
    Returns:
        Nome normalizado
    """
    if not text:
        return ""
    
    # Lowercase
    normalized = text.lower().strip()
    
    # Remover acentos
    normalized = unicodedata.normalize('NFD', normalized)
    normalized = ''.join(char for char in normalized if unicodedata.category(char) != 'Mn')
    
    # Remover medidas e unidades (ex: "500g", "1kg", "250ml", "2un")
    normalized = re.sub(r'\d+\s*(kg|g|ml|l|lt|un|pct|pac|cx|emb|und|gr|mg|cl|dl)', '', normalized, flags=re.IGNORECASE)
    
    # Remover números soltos (ex: "produto 123")
    normalized = re.sub(r'\b\d+\b', '', normalized)
    
    # Remover stopwords
    words = normalized.split()
    words = [w for w in words if w not in STOPWORDS and len(w) > 2]
    normalized = ' '.join(words)
    
    # Remover espaços extras e caracteres especiais
    normalized = re.sub(r'[^\w\s]', ' ', normalized)
    normalized = ' '.join(normalized.split())
    
    return normalized.strip()


def match_by_barcode(db: Session, barcode: str) -> Optional[UUID]:
    """
    Busca produto por código de barras.
    
    Args:
        db: Sessão do banco de dados
        barcode: Código de barras
        
    Returns:
        product_id se encontrado, None caso contrário
    """
    if not barcode:
        return None
    
    product = db.query(Product).filter(Product.barcode == barcode).first()
    
    if product:
        logger.debug(f"Product matched by barcode: {barcode} -> {product.id}")
        return product.id
    
    return None


def fuzzy_match_name(
    db: Session,
    name: str,
    threshold: int = 85
) -> Optional[UUID]:
    """
    Busca produto usando fuzzy matching com rapidfuzz.
    
    Args:
        db: Sessão do banco de dados
        name: Nome do produto a buscar
        threshold: Threshold de similaridade (0-100)
        
    Returns:
        product_id se encontrado com similaridade >= threshold, None caso contrário
    """
    if not name:
        return None
    
    normalized = normalize_name(name)
    
    if not normalized:
        return None
    
    # Buscar todos os produtos
    products = db.query(Product).all()
    
    if not products:
        return None
    
    # Criar lista de nomes normalizados para matching
    product_names = {p.id: p.normalized_name for p in products}
    
    # Usar rapidfuzz para encontrar melhor match
    result = process.extractOne(
        normalized,
        product_names,
        scorer=fuzz.WRatio,
        score_cutoff=threshold
    )
    
    if result:
        product_id, score, matched_name = result
        logger.debug(f"Product fuzzy matched: '{name}' -> {product_id} (score: {score:.1f}%)")
        return product_id
    
    return None


def embed_match_name(
    db: Session,
    name: str,
    top_k: int = 5
) -> List[UUID]:
    """
    Busca produtos usando embeddings e vector DB (se configurado).
    Retorna lista vazia se vector DB não estiver configurado.
    
    Args:
        db: Sessão do banco de dados
        name: Nome do produto a buscar
        top_k: Número de resultados a retornar
        
    Returns:
        Lista de product_ids ordenados por similaridade
    """
    try:
        from supabase import create_client, Client
        from sentence_transformers import SentenceTransformer
        from app.config import settings
    except ImportError:
        logger.debug("Vector DB dependencies not available, skipping embedding match")
        return []
    
    # Verificar se vector DB está configurado
    supabase_url = getattr(settings, 'SUPABASE_URL', '')
    supabase_key = getattr(settings, 'SUPABASE_KEY', '')
    
    if not supabase_url or not supabase_key:
        logger.debug("Supabase not configured, skipping embedding match")
        return []
    
    try:
        global _embedding_model, _supabase_client
        
        # Carregar modelo de embeddings (lazy loading)
        if _embedding_model is None:
            logger.info("Loading sentence transformer model...")
            _embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        
        # Inicializar cliente Supabase (lazy loading)
        if _supabase_client is None:
            _supabase_client = create_client(supabase_url, supabase_key)
        
        # Gerar embedding do nome
        normalized = normalize_name(name)
        embedding = _embedding_model.encode(normalized).tolist()
        
        # Buscar no vector DB
        response = _supabase_client.rpc(
            'match_products',
            {
                'query_embedding': embedding,
                'match_threshold': 0.7,
                'match_count': top_k
            }
        ).execute()
        
        if response.data:
            product_ids = [UUID(item['product_id']) for item in response.data]
            logger.debug(f"Product embedding matched: '{name}' -> {len(product_ids)} results")
            return product_ids
        
    except Exception as e:
        logger.warning(f"Error in embedding match: {e}")
        return []
    
    return []


def get_or_create_product_from_item(
    db: Session,
    item: Dict[str, Any]
) -> UUID:
    """
    Busca ou cria produto usando múltiplas estratégias combinadas:
    1. Match por código de barras (se disponível)
    2. Fuzzy matching por nome
    3. Embedding matching (se vector DB configurado)
    4. Cria novo produto se nenhuma estratégia encontrar match
    
    Args:
        db: Sessão do banco de dados
        item: Dicionário com dados do item (description, barcode, etc)
        
    Returns:
        product_id (existente ou recém-criado)
    """
    description = item.get("description", "")
    barcode = item.get("barcode")
    
    product_id = None
    
    # Estratégia 1: Match por código de barras
    if barcode:
        product_id = match_by_barcode(db, barcode)
        if product_id:
            logger.info(f"Product matched by barcode: {barcode}")
            return product_id
    
    # Estratégia 2: Fuzzy matching por nome
    if description:
        product_id = fuzzy_match_name(db, description, threshold=85)
        if product_id:
            logger.info(f"Product matched by fuzzy name: '{description}'")
            return product_id
    
    # Estratégia 3: Embedding matching (se configurado)
    if description:
        embedding_matches = embed_match_name(db, description, top_k=5)
        if embedding_matches:
            # Usar o primeiro resultado (mais similar)
            product_id = embedding_matches[0]
            logger.info(f"Product matched by embedding: '{description}'")
            return product_id
    
    # Estratégia 4: Criar novo produto
    normalized = normalize_name(description) if description else "produto sem nome"
    
    product = Product(
        normalized_name=normalized,
        barcode=barcode,
        category_id=item.get("category_id")
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    
    logger.info(f"Product created: {product.id} - '{normalized}'")
    return product.id

