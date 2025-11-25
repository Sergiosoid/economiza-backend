"""
Testes para endpoints de pagamento (Stripe)
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, Base, engine
from app.models.user import User
import uuid

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
def test_user(db_session):
    """Cria um usuário de teste"""
    user = User(
        email="test@example.com",
        password_hash="hashed_password",
        consent_given=True,
        is_pro=False
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_create_checkout_session_success(db_session, test_user):
    """Testa criação de sessão de checkout com sucesso"""
    with patch('app.routers.payments.stripe.checkout.Session.create') as mock_create:
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/test"
        mock_session.id = "cs_test_123"
        mock_create.return_value = mock_session
        
        # Mock get_current_user
        with patch('app.routers.payments.get_current_user', return_value=test_user.id):
            response = client.post(
                "/api/v1/payments/create-checkout-session?plan=pro",
                headers={"Authorization": "Bearer test_token"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "checkout_url" in data
        assert "session_id" in data
        assert data["checkout_url"] == "https://checkout.stripe.com/test"


def test_create_checkout_session_already_pro(db_session, test_user):
    """Testa criação de checkout quando usuário já é PRO"""
    test_user.is_pro = True
    db_session.commit()
    
    with patch('app.routers.payments.get_current_user', return_value=test_user.id):
        response = client.post(
            "/api/v1/payments/create-checkout-session?plan=pro",
            headers={"Authorization": "Bearer test_token"}
        )
    
    assert response.status_code == 400
    assert "já possui assinatura PRO" in response.json()["detail"]


def test_create_checkout_session_invalid_plan(db_session, test_user):
    """Testa criação de checkout com plano inválido"""
    with patch('app.routers.payments.get_current_user', return_value=test_user.id):
        response = client.post(
            "/api/v1/payments/create-checkout-session?plan=invalid",
            headers={"Authorization": "Bearer test_token"}
        )
    
    assert response.status_code == 400
    assert "Plano inválido" in response.json()["detail"]


def test_get_subscription_status(db_session, test_user):
    """Testa obtenção de status de assinatura"""
    with patch('app.routers.payments.get_current_user', return_value=test_user.id):
        response = client.get(
            "/api/v1/payments/subscription-status",
            headers={"Authorization": "Bearer test_token"}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert "is_pro" in data
    assert "subscription_id" in data
    assert data["is_pro"] == False


def test_webhook_checkout_completed(db_session, test_user):
    """Testa webhook de checkout completado"""
    import json
    import time
    
    # Criar evento mock do Stripe
    event = {
        "id": "evt_test",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "subscription": "sub_test_123",
                "metadata": {
                    "user_id": str(test_user.id),
                    "plan": "pro"
                }
            }
        }
    }
    
    with patch('app.routers.payments.stripe.Webhook.construct_event') as mock_construct:
        mock_construct.return_value = event
        
        response = client.post(
            "/api/v1/payments/webhook",
            content=json.dumps(event),
            headers={
                "stripe-signature": "test_signature"
            }
        )
        
        assert response.status_code == 200
        
        # Verificar se usuário foi atualizado
        db_session.refresh(test_user)
        assert test_user.is_pro == True
        assert test_user.subscription_id == "sub_test_123"


def test_webhook_subscription_deleted(db_session, test_user):
    """Testa webhook de assinatura cancelada"""
    import json
    
    # Marcar usuário como PRO primeiro
    test_user.is_pro = True
    test_user.subscription_id = "sub_test_123"
    db_session.commit()
    
    event = {
        "id": "evt_test",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_test_123",
                "metadata": {
                    "user_id": str(test_user.id)
                }
            }
        }
    }
    
    with patch('app.routers.payments.stripe.Webhook.construct_event') as mock_construct:
        mock_construct.return_value = event
        
        response = client.post(
            "/api/v1/payments/webhook",
            content=json.dumps(event),
            headers={
                "stripe-signature": "test_signature"
            }
        )
        
        assert response.status_code == 200
        
        # Verificar se usuário foi atualizado
        db_session.refresh(test_user)
        assert test_user.is_pro == False
        assert test_user.subscription_id is None

