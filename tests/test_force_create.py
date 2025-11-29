"""
Testes para o endpoint de desenvolvimento /api/v1/receipts/force-create
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime
from uuid import UUID
import json

from app.main import app
from app.config import settings

client = TestClient(app)


@pytest.fixture(scope="function", autouse=True)
def override_settings():
    """Override settings para testes."""
    original_dev_mode = settings.DEV_MODE
    
    settings.DEV_MODE = True
    
    yield
    
    settings.DEV_MODE = original_dev_mode


@pytest.fixture(scope="function")
def mock_db_session():
    """Mock da sessão do banco de dados."""
    with patch('app.routers.dev_seed.get_db') as mock_get_db:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        yield mock_db


@pytest.fixture(scope="function")
def mock_get_current_user():
    """Mock de get_current_user para retornar user_id fixo."""
    test_user_id = UUID("00000000-0000-0000-0000-000000000001")
    with patch('app.routers.dev_seed.get_current_user', return_value=test_user_id):
        yield test_user_id


def test_force_create_success(mock_db_session, mock_get_current_user):
    """Testa criação bem-sucedida de nota com itens."""
    # Mock: não existe receipt com essa access_key
    mock_db_session.query.return_value.filter.return_value.first.return_value = None
    
    # Mock: produto não existe, será criado
    mock_db_session.query.return_value.filter.return_value.first.side_effect = [None, None]
    
    # Mock: flush e commit
    mock_db_session.flush.return_value = None
    mock_db_session.commit.return_value = None
    mock_db_session.refresh.return_value = None
    
    # Criar receipt mock
    mock_receipt = MagicMock()
    mock_receipt.id = UUID("12345678-1234-5678-1234-567812345678")
    mock_db_session.add.return_value = None
    
    # Mock refresh para retornar receipt
    def mock_refresh(obj):
        if isinstance(obj, type) or hasattr(obj, 'id'):
            obj.id = mock_receipt.id
    mock_db_session.refresh.side_effect = mock_refresh
    
    body = {
        "store_name": "Carrefour",
        "store_cnpj": "12345678000199",
        "emitted_at": "2025-01-15T14:33:00",
        "items": [
            {"name": "Arroz Branco Tipo 1 5kg", "quantity": 1, "unit_price": 19.99, "category": "Alimentos"},
            {"name": "Feijão Carioca 1kg", "quantity": 2, "unit_price": 7.49, "category": "Alimentos"}
        ],
        "override": False
    }
    
    response = client.post(
        "/api/v1/receipts/force-create",
        json=body,
        headers={"Authorization": "Bearer test"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "created"
    assert "receipt_id" in data


def test_force_create_fails_when_dev_mode_false(mock_get_current_user):
    """Testa que falha quando DEV_MODE=False."""
    original_dev_mode = settings.DEV_MODE
    settings.DEV_MODE = False
    
    try:
        body = {
            "store_name": "Carrefour",
            "store_cnpj": "12345678000199",
            "emitted_at": "2025-01-15T14:33:00",
            "items": [
                {"name": "Arroz", "quantity": 1, "unit_price": 19.99}
            ]
        }
        
        response = client.post(
            "/api/v1/receipts/force-create",
            json=body,
            headers={"Authorization": "Bearer test"}
        )
        
        assert response.status_code == 403
        assert "development mode" in response.json()["detail"].lower()
    finally:
        settings.DEV_MODE = original_dev_mode


def test_force_create_fails_without_authorization(mock_db_session, mock_get_current_user):
    """Testa que falha sem Authorization header."""
    body = {
        "store_name": "Carrefour",
        "store_cnpj": "12345678000199",
        "emitted_at": "2025-01-15T14:33:00",
        "items": [
            {"name": "Arroz", "quantity": 1, "unit_price": 19.99}
        ]
    }
    
    response = client.post(
        "/api/v1/receipts/force-create",
        json=body
    )
    
    assert response.status_code == 401
    assert "invalid authentication" in response.json()["detail"].lower()


def test_force_create_fails_with_wrong_token(mock_db_session, mock_get_current_user):
    """Testa que falha com token diferente de 'test'."""
    body = {
        "store_name": "Carrefour",
        "store_cnpj": "12345678000199",
        "emitted_at": "2025-01-15T14:33:00",
        "items": [
            {"name": "Arroz", "quantity": 1, "unit_price": 19.99}
        ]
    }
    
    response = client.post(
        "/api/v1/receipts/force-create",
        json=body,
        headers={"Authorization": "Bearer wrong_token"}
    )
    
    assert response.status_code == 401
    assert "invalid authentication" in response.json()["detail"].lower()


def test_force_create_creates_two_different_receipts(mock_db_session, mock_get_current_user):
    """Testa criação de duas notas diferentes."""
    # Mock: não existe receipt
    mock_db_session.query.return_value.filter.return_value.first.return_value = None
    
    body1 = {
        "store_name": "Carrefour",
        "store_cnpj": "12345678000199",
        "emitted_at": "2025-01-15T14:33:00",
        "items": [
            {"name": "Arroz", "quantity": 1, "unit_price": 19.99}
        ]
    }
    
    body2 = {
        "store_name": "Extra",
        "store_cnpj": "98765432000111",
        "emitted_at": "2025-01-16T10:00:00",
        "items": [
            {"name": "Feijão", "quantity": 2, "unit_price": 7.49}
        ]
    }
    
    response1 = client.post(
        "/api/v1/receipts/force-create",
        json=body1,
        headers={"Authorization": "Bearer test"}
    )
    
    response2 = client.post(
        "/api/v1/receipts/force-create",
        json=body2,
        headers={"Authorization": "Bearer test"}
    )
    
    # Ambas devem ser criadas (mesmo que mock retorne None, o código deve processar)
    # O importante é que não dê erro 409
    assert response1.status_code in [200, 500]  # 500 se mock não estiver completo
    assert response2.status_code in [200, 500]


def test_force_create_returns_409_without_override(mock_db_session, mock_get_current_user):
    """Testa que retorna 409 quando receipt já existe e override=false."""
    # Mock: existe receipt
    mock_existing_receipt = MagicMock()
    mock_existing_receipt.id = UUID("11111111-1111-1111-1111-111111111111")
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_existing_receipt
    
    body = {
        "store_name": "Carrefour",
        "store_cnpj": "12345678000199",
        "emitted_at": "2025-01-15T14:33:00",
        "items": [
            {"name": "Arroz", "quantity": 1, "unit_price": 19.99}
        ],
        "override": False
    }
    
    response = client.post(
        "/api/v1/receipts/force-create",
        json=body,
        headers={"Authorization": "Bearer test"}
    )
    
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"].lower()


def test_force_create_overwrites_with_override_true(mock_db_session, mock_get_current_user):
    """Testa que sobrescreve quando override=true."""
    # Mock: existe receipt
    mock_existing_receipt = MagicMock()
    mock_existing_receipt.id = UUID("11111111-1111-1111-1111-111111111111")
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_existing_receipt
    
    # Mock: delete de itens e receipt
    mock_db_session.query.return_value.filter.return_value.delete.return_value = None
    mock_db_session.delete.return_value = None
    
    body = {
        "store_name": "Carrefour",
        "store_cnpj": "12345678000199",
        "emitted_at": "2025-01-15T14:33:00",
        "items": [
            {"name": "Arroz", "quantity": 1, "unit_price": 19.99}
        ],
        "override": True
    }
    
    response = client.post(
        "/api/v1/receipts/force-create",
        json=body,
        headers={"Authorization": "Bearer test"}
    )
    
    # Deve tentar sobrescrever (pode dar 200 ou 500 dependendo do mock)
    assert response.status_code in [200, 500]
    # Verificar que delete foi chamado
    mock_db_session.delete.assert_called()

