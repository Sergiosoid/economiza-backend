"""
Testes para o product_matcher
"""
import pytest
from unittest.mock import patch, MagicMock
from uuid import UUID, uuid4
from sqlalchemy.orm import Session
from app.database import SessionLocal, Base, engine
from app.models.product import Product
from app.services.product_matcher import (
    normalize_name,
    match_by_barcode,
    fuzzy_match_name,
    embed_match_name,
    get_or_create_product_from_item,
)


@pytest.fixture(scope="function")
def db_session():
    """Cria uma sessão de banco de dados para testes"""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_normalize_name_basic():
    """Testa normalização básica"""
    assert normalize_name("ARROZ TIPO 1 5KG") == "arroz tipo"
    assert normalize_name("Feijão Preto 1kg") == "feijao preto"
    assert normalize_name("Açúcar Cristal 500g") == "acucar cristal"


def test_normalize_name_remove_stopwords():
    """Testa remoção de stopwords"""
    assert normalize_name("Produto Tipo A Marca X") == "produto marca"
    assert normalize_name("Pacote de Arroz") == "pacote arroz"


def test_normalize_name_remove_measures():
    """Testa remoção de medidas e unidades"""
    assert normalize_name("Leite 1L") == "leite"
    assert normalize_name("Cerveja 350ml") == "cerveja"
    assert normalize_name("Arroz 2kg 500g") == "arroz"
    assert normalize_name("Produto 3un") == "produto"


def test_normalize_name_remove_accents():
    """Testa remoção de acentos"""
    assert normalize_name("Açúcar") == "acucar"
    assert normalize_name("Café") == "cafe"
    assert normalize_name("Ação") == "acao"
    assert normalize_name("Pão") == "pao"


def test_normalize_name_empty():
    """Testa normalização de strings vazias"""
    assert normalize_name("") == ""
    assert normalize_name("   ") == ""


def test_match_by_barcode_found(db_session):
    """Testa match por código de barras quando encontrado"""
    # Criar produto com barcode
    product = Product(
        normalized_name="arroz tipo",
        barcode="7891234567890"
    )
    db_session.add(product)
    db_session.commit()
    
    product_id = match_by_barcode(db_session, "7891234567890")
    
    assert product_id == product.id


def test_match_by_barcode_not_found(db_session):
    """Testa match por código de barras quando não encontrado"""
    product_id = match_by_barcode(db_session, "9999999999999")
    
    assert product_id is None


def test_match_by_barcode_empty(db_session):
    """Testa match por código de barras vazio"""
    product_id = match_by_barcode(db_session, "")
    
    assert product_id is None


def test_fuzzy_match_name_found(db_session):
    """Testa fuzzy matching quando encontrado"""
    # Criar produtos
    product1 = Product(normalized_name="arroz tipo branco")
    product2 = Product(normalized_name="feijao preto")
    db_session.add_all([product1, product2])
    db_session.commit()
    
    # Buscar com nome similar
    product_id = fuzzy_match_name(db_session, "Arroz Tipo 1 5KG", threshold=80)
    
    assert product_id == product1.id


def test_fuzzy_match_name_not_found(db_session):
    """Testa fuzzy matching quando não encontrado (threshold alto)"""
    product = Product(normalized_name="arroz tipo branco")
    db_session.add(product)
    db_session.commit()
    
    # Buscar com nome muito diferente
    product_id = fuzzy_match_name(db_session, "Produto Completamente Diferente", threshold=95)
    
    assert product_id is None


def test_fuzzy_match_name_empty(db_session):
    """Testa fuzzy matching com nome vazio"""
    product_id = fuzzy_match_name(db_session, "", threshold=85)
    
    assert product_id is None


def test_fuzzy_match_name_no_products(db_session):
    """Testa fuzzy matching quando não há produtos"""
    product_id = fuzzy_match_name(db_session, "Arroz", threshold=85)
    
    assert product_id is None


def test_embed_match_name_not_configured(db_session):
    """Testa embedding match quando vector DB não está configurado"""
    with patch('app.services.product_matcher.settings') as mock_settings:
        mock_settings.SUPABASE_URL = ""
        
        results = embed_match_name(db_session, "Arroz Tipo 1")
        
        assert results == []


def test_embed_match_name_configured(db_session):
    """Testa embedding match quando vector DB está configurado"""
    with patch('app.services.product_matcher.settings') as mock_settings:
        mock_settings.SUPABASE_URL = "https://test.supabase.co"
        mock_settings.SUPABASE_KEY = "test-key"
        
        # Mock do modelo e cliente Supabase
        mock_model = MagicMock()
        mock_model.encode.return_value = [[0.1, 0.2, 0.3]]  # Embedding fake
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [
            {"product_id": str(uuid4()), "similarity": 0.85},
            {"product_id": str(uuid4()), "similarity": 0.80}
        ]
        mock_client.rpc.return_value.execute.return_value = mock_response
        
        with patch('app.services.product_matcher.SentenceTransformer', return_value=mock_model):
            with patch('app.services.product_matcher.create_client', return_value=mock_client):
                # Resetar globals
                import app.services.product_matcher as pm
                pm._embedding_model = None
                pm._supabase_client = None
                
                results = embed_match_name(db_session, "Arroz Tipo 1", top_k=5)
                
                assert len(results) == 2
                assert all(isinstance(r, UUID) for r in results)


def test_get_or_create_product_from_item_by_barcode(db_session):
    """Testa criação/busca de produto usando código de barras"""
    # Criar produto existente
    existing_product = Product(
        normalized_name="arroz tipo",
        barcode="7891234567890"
    )
    db_session.add(existing_product)
    db_session.commit()
    
    item = {
        "description": "Arroz Tipo 1 5KG",
        "barcode": "7891234567890"
    }
    
    product_id = get_or_create_product_from_item(db_session, item)
    
    assert product_id == existing_product.id


def test_get_or_create_product_from_item_by_fuzzy(db_session):
    """Testa criação/busca de produto usando fuzzy matching"""
    # Criar produto existente
    existing_product = Product(normalized_name="arroz tipo branco")
    db_session.add(existing_product)
    db_session.commit()
    
    item = {
        "description": "Arroz Tipo 1 5KG",
        "barcode": None
    }
    
    product_id = get_or_create_product_from_item(db_session, item)
    
    assert product_id == existing_product.id


def test_get_or_create_product_from_item_create_new(db_session):
    """Testa criação de novo produto quando nenhum match é encontrado"""
    item = {
        "description": "Produto Novo e Inexistente",
        "barcode": None
    }
    
    product_id = get_or_create_product_from_item(db_session, item)
    
    # Verificar que foi criado
    product = db_session.query(Product).filter(Product.id == product_id).first()
    assert product is not None
    assert "produto novo inexistente" in product.normalized_name


def test_get_or_create_product_from_item_strategy_order(db_session):
    """Testa que as estratégias são executadas na ordem correta"""
    # Criar produto com barcode
    product_with_barcode = Product(
        normalized_name="produto diferente",
        barcode="7891234567890"
    )
    # Criar produto com nome similar (mas sem barcode)
    product_similar_name = Product(normalized_name="arroz tipo branco")
    db_session.add_all([product_with_barcode, product_similar_name])
    db_session.commit()
    
    item = {
        "description": "Arroz Tipo 1 5KG",  # Similar ao product_similar_name
        "barcode": "7891234567890"  # Match com product_with_barcode
    }
    
    product_id = get_or_create_product_from_item(db_session, item)
    
    # Deve priorizar barcode sobre fuzzy matching
    assert product_id == product_with_barcode.id


def test_get_or_create_product_from_item_with_category(db_session):
    """Testa criação de produto com categoria"""
    from app.models.category import Category
    
    category = Category(name="Alimentos")
    db_session.add(category)
    db_session.commit()
    
    item = {
        "description": "Produto Novo",
        "barcode": None,
        "category_id": category.id
    }
    
    product_id = get_or_create_product_from_item(db_session, item)
    
    product = db_session.query(Product).filter(Product.id == product_id).first()
    assert product.category_id == category.id

