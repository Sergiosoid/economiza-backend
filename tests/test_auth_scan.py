"""
Testes de autenticação e scan de recibos
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app
from app.database import SessionLocal, Base, engine

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
def mock_provider_and_parser():
    """Mock do provider client e parser para evitar chamadas reais"""
    with patch('app.routers.receipts.fetch_by_key') as mock_fetch, \
         patch('app.routers.receipts.parse_note') as mock_parse:
        
        # Mock de resposta do provider
        mock_fetch.return_value = {
            "retorno": {
                "emitente": {
                    "razao_social": "SUPERMERCADO TESTE",
                    "cnpj": "12345678000190"
                },
                "produto": [
                    {
                        "descricao": "ARROZ TIPO 1 5KG",
                        "valor_unitario": "25.50",
                        "valor_total": "25.50",
                        "quantidade": "1.000"
                    }
                ],
                "total": "25.50",
                "subtotal": "25.50",
                "imposto": "0.00"
            }
        }
        
        # Mock de dados parseados
        mock_parse.return_value = {
            "access_key": "35200112345678000190650010000000011234567890",
            "total_value": 25.50,
            "subtotal": 25.50,
            "total_tax": 0.00,
            "emitted_at": "2024-01-15T10:30:00-03:00",
            "store_name": "SUPERMERCADO TESTE",
            "store_cnpj": "12345678000190",
            "items": [
                {
                    "description": "ARROZ TIPO 1 5KG",
                    "quantity": 1.0,
                    "unit_price": 25.50,
                    "total_price": 25.50,
                    "tax_value": 0.00
                }
            ]
        }
        
        yield mock_fetch, mock_parse


def test_scan_with_bearer_token(mock_provider_and_parser, db_session):
    """Testa scan com header Authorization: Bearer test"""
    response = client.post(
        "/api/v1/receipts/scan",
        json={"qr_text": "35200112345678000190650010000000011234567890"},
        headers={"Authorization": "Bearer test"}
    )
    assert response.status_code in [200, 201, 202]
    assert "receipt_id" in response.json() or "task_id" in response.json() or "status" in response.json()


def test_scan_with_token_only(mock_provider_and_parser, db_session):
    """Testa scan com header Authorization: test (sem Bearer)"""
    response = client.post(
        "/api/v1/receipts/scan",
        json={"qr_text": "35200112345678000190650010000000011234567890"},
        headers={"Authorization": "test"}
    )
    assert response.status_code in [200, 201, 202]
    assert "receipt_id" in response.json() or "task_id" in response.json() or "status" in response.json()


def test_scan_with_lowercase_bearer(mock_provider_and_parser, db_session):
    """Testa scan com header Authorization: bearer test (case-insensitive)"""
    response = client.post(
        "/api/v1/receipts/scan",
        json={"qr_text": "35200112345678000190650010000000011234567890"},
        headers={"Authorization": "bearer test"}
    )
    assert response.status_code in [200, 201, 202]
    assert "receipt_id" in response.json() or "task_id" in response.json() or "status" in response.json()


def test_scan_without_authorization():
    """Testa scan sem header Authorization - deve retornar 401"""
    response = client.post(
        "/api/v1/receipts/scan",
        json={"qr_text": "35200112345678000190650010000000011234567890"}
    )
    assert response.status_code == 401
    assert "Authorization header missing" in response.json()["detail"]


def test_scan_with_invalid_token(mock_provider_and_parser):
    """Testa scan com token inválido - deve retornar 401"""
    response = client.post(
        "/api/v1/receipts/scan",
        json={"qr_text": "35200112345678000190650010000000011234567890"},
        headers={"Authorization": "Bearer invalid_token"}
    )
    assert response.status_code == 401
    assert "Invalid authentication credentials" in response.json()["detail"]


def test_analytics_with_bearer_token(db_session):
    """Testa endpoint de analytics com Bearer token"""
    response = client.get(
        "/api/v1/analytics/top-items?limit=10",
        headers={"Authorization": "Bearer test"}
    )
    assert response.status_code == 200
    assert "items" in response.json()


def test_analytics_without_authorization():
    """Testa analytics sem header Authorization - deve retornar 401"""
    response = client.get("/api/v1/analytics/top-items?limit=10")
    assert response.status_code == 401
    assert "Authorization header missing" in response.json()["detail"]


def test_user_export_with_bearer_token(db_session):
    """Testa export de dados do usuário com Bearer token"""
    response = client.get(
        "/api/v1/user/export-data",
        headers={"Authorization": "Bearer test"}
    )
    # Pode retornar 200 (com dados) ou 404 (sem dados), mas não 401
    assert response.status_code != 401


def test_user_export_without_authorization():
    """Testa export sem header Authorization - deve retornar 401"""
    response = client.get("/api/v1/user/export-data")
    assert response.status_code == 401
    assert "Authorization header missing" in response.json()["detail"]
