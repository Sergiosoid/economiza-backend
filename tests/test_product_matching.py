"""
Testes específicos para matching avançado de produtos
Garante que produtos iguais em notas diferentes sejam mapeados para o mesmo product_id
"""
import pytest
from app.database import SessionLocal, Base, engine
from app.models.product import Product
from app.services.product_matcher import (
    normalize_name,
    fuzzy_match,
    get_or_create_product,
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


def test_normalize_arroz_variations():
    """Testa que variações de 'Arroz Tipo 1 5kg' normalizam para o mesmo resultado"""
    name1 = normalize_name("Arroz Tipo 1 5kg")
    name2 = normalize_name("Arroz T.1 5 KG")
    name3 = normalize_name("ARROZ TIPO 1 5KG")
    name4 = normalize_name("Arroz Tipo 1 - 5kg")
    
    # Todas devem normalizar para o mesmo resultado (sem números, sem unidades, sem "tipo")
    # "tipo" está em STOPWORDS e será removido
    assert name1 == name2
    assert name2 == name3
    assert name3 == name4
    assert "arroz" in name1
    assert "tipo" not in name1  # "tipo" está em STOPWORDS e deve ser removido


def test_normalize_coca_cola_variations():
    """Testa que variações de 'Coca Cola Lata 350ml' normalizam para o mesmo resultado"""
    name1 = normalize_name("Coca Cola Lata 350ml")
    name2 = normalize_name("Coca-Cola 350 ML")
    name3 = normalize_name("COCA COLA LATA 350ML")
    name4 = normalize_name("Coca Cola - 350ml")
    
    # Todas devem normalizar para o mesmo resultado
    assert name1 == name2
    assert name2 == name3
    assert name3 == name4
    assert "coca" in name1
    assert "cola" in name1
    assert "lata" in name1


def test_normalize_remove_punctuation():
    """Testa remoção de pontuações"""
    name1 = normalize_name("Produto-Teste")
    name2 = normalize_name("Produto Teste")
    name3 = normalize_name("Produto/Teste")
    
    assert name1 == name2
    assert name2 == name3


def test_normalize_remove_generic_words():
    """Testa remoção de palavras genéricas"""
    name1 = normalize_name("Arroz Tipo 1")
    name2 = normalize_name("Arroz 1")
    
    # "tipo" deve ser removido
    assert "tipo" not in name1
    assert name1 == name2


def test_matching_arroz_same_product(db_session):
    """Testa que 'Arroz Tipo 1 5kg' e 'Arroz T.1 5 KG' resultam no mesmo produto"""
    # Criar primeiro produto
    item1 = {
        "description": "Arroz Tipo 1 5kg",
        "barcode": None
    }
    
    product_id1 = get_or_create_product(db_session, item1)
    
    # Tentar criar segundo produto com variação
    item2 = {
        "description": "Arroz T.1 5 KG",
        "barcode": None
    }
    
    product_id2 = get_or_create_product(db_session, item2)
    
    # Devem ser o mesmo produto
    assert product_id1 == product_id2
    
    # Verificar que só existe um produto
    products = db_session.query(Product).all()
    assert len(products) == 1
    assert products[0].id == product_id1


def test_matching_coca_cola_same_product(db_session):
    """Testa que 'Coca Cola Lata 350ml' e 'Coca-Cola 350 ML' resultam no mesmo produto"""
    # Criar primeiro produto
    item1 = {
        "description": "Coca Cola Lata 350ml",
        "barcode": None
    }
    
    product_id1 = get_or_create_product(db_session, item1)
    
    # Tentar criar segundo produto com variação
    item2 = {
        "description": "Coca-Cola 350 ML",
        "barcode": None
    }
    
    product_id2 = get_or_create_product(db_session, item2)
    
    # Devem ser o mesmo produto
    assert product_id1 == product_id2
    
    # Verificar que só existe um produto
    products = db_session.query(Product).all()
    assert len(products) == 1


def test_matching_with_barcode(db_session):
    """Testa matching com barcode igual"""
    barcode = "7891234567890"
    
    # Criar primeiro produto com barcode
    item1 = {
        "description": "Arroz Tipo 1 5kg",
        "barcode": barcode
    }
    
    product_id1 = get_or_create_product(db_session, item1)
    
    # Tentar criar segundo produto com mesmo barcode mas descrição diferente
    item2 = {
        "description": "Arroz T.1 5 KG",  # Descrição diferente
        "barcode": barcode  # Mesmo barcode
    }
    
    product_id2 = get_or_create_product(db_session, item2)
    
    # Devem ser o mesmo produto (match por barcode)
    assert product_id1 == product_id2
    
    # Verificar que só existe um produto
    products = db_session.query(Product).all()
    assert len(products) == 1
    assert products[0].barcode == barcode


def test_matching_different_products(db_session):
    """Testa que produtos realmente diferentes não são agrupados"""
    # Criar produtos diferentes
    item1 = {
        "description": "Arroz Tipo 1 5kg",
        "barcode": None
    }
    
    item2 = {
        "description": "Feijão Preto 1kg",
        "barcode": None
    }
    
    product_id1 = get_or_create_product(db_session, item1)
    product_id2 = get_or_create_product(db_session, item2)
    
    # Devem ser produtos diferentes
    assert product_id1 != product_id2
    
    # Verificar que existem dois produtos
    products = db_session.query(Product).all()
    assert len(products) == 2


def test_fuzzy_match_threshold(db_session):
    """Testa que fuzzy_match respeita o threshold"""
    # Criar produto
    product = Product(normalized_name="arroz tipo branco")
    db_session.add(product)
    db_session.commit()
    
    # Buscar com nome similar (deve encontrar)
    normalized = normalize_name("Arroz Tipo 1 5kg")
    product_id = fuzzy_match(db_session, normalized, threshold=80)
    
    assert product_id == product.id
    
    # Buscar com threshold muito alto (não deve encontrar)
    product_id = fuzzy_match(db_session, normalized, threshold=95)
    
    assert product_id is None


def test_normalize_remove_numbers_and_units():
    """Testa remoção de números isolados e unidades"""
    assert normalize_name("Produto 5kg") == "produto"
    assert normalize_name("Produto 1l") == "produto"
    assert normalize_name("Produto 350ml") == "produto"
    assert normalize_name("Produto 2un") == "produto"
    assert normalize_name("Produto 3pct") == "produto"


def test_matching_case_insensitive(db_session):
    """Testa que matching é case-insensitive"""
    item1 = {
        "description": "ARROZ TIPO 1 5KG",
        "barcode": None
    }
    
    item2 = {
        "description": "arroz tipo 1 5kg",
        "barcode": None
    }
    
    product_id1 = get_or_create_product(db_session, item1)
    product_id2 = get_or_create_product(db_session, item2)
    
    assert product_id1 == product_id2

