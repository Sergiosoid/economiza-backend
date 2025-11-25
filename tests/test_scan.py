"""
Testes para o endpoint /api/receipts/scan
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app
from app.database import SessionLocal, Base, engine
from app.models.receipt import Receipt
from app.models.receipt_item import ReceiptItem
from app.models.product import Product
from app.models.user import User

client = TestClient(app)


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


@pytest.fixture
def mock_provider_response():
    """Mock de resposta do provider (formato JSON fake)"""
    return {
        "access_key": "35200112345678901234567890123456789012345678",
        "store": {
            "name": "SUPERMERCADO EXEMPLO",
            "cnpj": "12345678000100"
        },
        "total": 125.30,
        "subtotal": 119.00,
        "tax": 6.30,
        "items": [
            {
                "description": "ARROZ TIPO 1 5KG",
                "quantity": 1,
                "unit_price": 25.50,
                "total_price": 25.50,
                "tax_value": 1.20
            },
            {
                "description": "FEIJAO PRETO 1KG",
                "quantity": 2,
                "unit_price": 8.50,
                "total_price": 17.00,
                "tax_value": 0.85
            }
        ],
        "emitted_at": "2024-04-12T15:33:00"
    }


def test_scan_receipt_success_200(db_session, mock_provider_response):
    """Testa scan de receipt com sucesso (200)"""
    with patch('app.services.provider_client.fetch_by_key') as mock_fetch:
        mock_fetch.return_value = mock_provider_response
        
        response = client.post(
            "/api/v1/receipts/scan",
            json={"qr_text": "35200112345678901234567890123456789012345678"},
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "receipt_id" in data
        assert data["status"] == "saved"
        
        # Verificar se foi salvo no banco
        receipt = db_session.query(Receipt).first()
        assert receipt is not None
        assert receipt.access_key == "35200112345678901234567890123456789012345678"
        assert receipt.store_name == "SUPERMERCADO EXEMPLO"
        
        # Verificar se os itens foram salvos
        items = db_session.query(ReceiptItem).filter(
            ReceiptItem.receipt_id == receipt.id
        ).all()
        assert len(items) == 2
        
        # Verificar se os produtos foram criados
        products = db_session.query(Product).all()
        assert len(products) >= 2


def test_scan_receipt_idempotency_409(db_session, mock_provider_response):
    """Testa idempotência - chamar duas vezes retorna 409"""
    with patch('app.services.provider_client.fetch_by_key') as mock_fetch:
        mock_fetch.return_value = mock_provider_response
        
        qr_text = "35200112345678901234567890123456789012345678"
        
        # Primeira chamada
        response1 = client.post(
            "/api/v1/receipts/scan",
            json={"qr_text": qr_text},
            headers={"Authorization": "Bearer test-token"}
        )
        assert response1.status_code == 200
        
        # Segunda chamada (deve retornar 409)
        response2 = client.post(
            "/api/v1/receipts/scan",
            json={"qr_text": qr_text},
            headers={"Authorization": "Bearer test-token"}
        )
        assert response2.status_code == 409
        data = response2.json()
        assert "receipt_id" in data
        assert data["detail"] == "receipt already exists"


def test_scan_receipt_invalid_qr_400():
    """Testa com QR inválido (sem URL nem chave) - retorna 400"""
    response = client.post(
        "/api/v1/receipts/scan",
        json={"qr_text": "texto inválido sem chave nem URL"},
        headers={"Authorization": "Bearer test-token"}
    )
    
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "invalid qr code" in data["detail"].lower()


def test_scan_receipt_with_url(db_session, mock_provider_response):
    """Testa scan com URL no QR text"""
    with patch('app.services.provider_client.fetch_by_url') as mock_fetch:
        mock_fetch.return_value = mock_provider_response
        
        response = client.post(
            "/api/v1/receipts/scan",
            json={"qr_text": "https://nfe.sefaz.gov.br/consulta?chave=35200112345678901234567890123456789012345678"},
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "receipt_id" in data
        assert data["status"] == "saved"
        
        mock_fetch.assert_called_once()


def test_scan_receipt_provider_error_500():
    """Testa erro do provider - retorna 500"""
    with patch('app.services.provider_client.fetch_by_key') as mock_fetch:
        from app.services.provider_client import ProviderError
        mock_fetch.side_effect = ProviderError("Erro ao buscar nota")
        
        response = client.post(
            "/api/v1/receipts/scan",
            json={"qr_text": "35200112345678901234567890123456789012345678"},
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "provider error" in data["detail"].lower()


def test_scan_receipt_missing_auth():
    """Testa sem header de autenticação"""
    response = client.post(
        "/api/v1/receipts/scan",
        json={"qr_text": "35200112345678901234567890123456789012345678"}
    )
    
    assert response.status_code == 401


def test_scan_receipt_empty_qr():
    """Testa com QR vazio"""
    response = client.post(
        "/api/v1/receipts/scan",
        json={"qr_text": ""},
        headers={"Authorization": "Bearer test-token"}
    )
    
    assert response.status_code == 422  # Validation error
