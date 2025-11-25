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
    """Mock de resposta do provider"""
    return {
        "nfeProc": {
            "NFe": {
                "infNFe": {
                    "@Id": "NFe35200112345678901234567890123456789012345678",
                    "ide": {
                        "dhEmi": "2024-01-15T10:30:00-03:00"
                    },
                    "emit": {
                        "xNome": "Loja Teste",
                        "CNPJ": "12345678000190"
                    },
                    "total": {
                        "ICMSTot": {
                            "vProd": "100.00",
                            "vNF": "120.00",
                            "vTotTrib": "20.00"
                        }
                    },
                    "det": [
                        {
                            "prod": {
                                "xProd": "Produto Teste",
                                "qCom": "1.000",
                                "vUnCom": "100.00",
                                "vProd": "100.00",
                                "cEAN": "7891234567890"
                            },
                            "imposto": {
                                "ICMS": {
                                    "vICMS": "18.00"
                                }
                            }
                        }
                    ]
                }
            }
        }
    }


def test_scan_receipt_success(db_session, mock_provider_response):
    """Testa scan de receipt com sucesso"""
    with patch('app.services.provider_client.fetch_note_by_key') as mock_fetch:
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


def test_scan_receipt_idempotency(db_session, mock_provider_response):
    """Testa idempotência - chamar duas vezes retorna 409"""
    with patch('app.services.provider_client.fetch_note_by_key') as mock_fetch:
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
        assert "receipt_id" in data or "detail" in data


def test_scan_receipt_invalid_qr():
    """Testa com QR inválido (sem URL nem chave)"""
    response = client.post(
        "/api/v1/receipts/scan",
        json={"qr_text": "texto inválido sem chave nem URL"},
        headers={"Authorization": "Bearer test-token"}
    )
    
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data


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

