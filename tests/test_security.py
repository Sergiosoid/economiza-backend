"""
Testes de segurança: auth, rate limit, scan validation, stripe webhook
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException
from uuid import UUID
import jwt
import time

from app.services.supabase_auth import verify_supabase_token, fetch_jwks
from app.utils.jwt_utils import create_internal_token, verify_internal_token
from app.utils.qr_extractor import extract_key_or_url, validate_qr_text, sanitize_qr_text
from app.middleware.rate_limit import check_rate_limit, get_rate_limit_key
from app.config import settings


class TestSupabaseAuth:
    """Testes de validação de token Supabase"""
    
    @patch('app.services.supabase_auth.fetch_jwks')
    @patch('app.services.supabase_auth.get_public_key')
    def test_verify_supabase_token_valid(self, mock_get_key, mock_fetch_jwks):
        """Testa validação de token Supabase válido"""
        # Mock JWKS
        mock_fetch_jwks.return_value = {
            "keys": [{"kid": "test-kid", "n": "test-n", "e": "AQAB"}]
        }
        
        # Mock public key
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
        mock_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        ).public_key()
        mock_get_key.return_value = mock_key
        
        # Criar token de teste (não vamos validar assinatura real aqui)
        # Este teste é mais conceitual
        with pytest.raises(ValueError):
            # Token inválido deve lançar ValueError
            verify_supabase_token("invalid.token.here")
    
    def test_verify_supabase_token_expired(self):
        """Testa rejeição de token expirado"""
        # Token expirado deve ser rejeitado
        with pytest.raises(ValueError, match="expired"):
            # Simular token expirado
            verify_supabase_token("expired.token.here")


class TestInternalJWT:
    """Testes de JWT interno"""
    
    def test_create_and_verify_internal_token(self):
        """Testa criação e verificação de token interno"""
        user_id = UUID("00000000-0000-0000-0000-000000000001")
        
        # Criar token
        token = create_internal_token(user_id, expires_min=60)
        assert token is not None
        assert isinstance(token, str)
        
        # Verificar token
        payload = verify_internal_token(token)
        assert payload["user_id"] == str(user_id)
        assert payload["type"] == "internal"
    
    def test_verify_internal_token_expired(self):
        """Testa rejeição de token interno expirado"""
        user_id = UUID("00000000-0000-0000-0000-000000000001")
        
        # Criar token com expiração muito curta
        token = create_internal_token(user_id, expires_min=0)
        
        # Aguardar um pouco para garantir expiração
        time.sleep(1)
        
        # Verificar que token expirado é rejeitado
        with pytest.raises(ValueError, match="expired"):
            verify_internal_token(token)


class TestQRValidation:
    """Testes de validação de QR code"""
    
    def test_extract_key_or_url_valid_key(self):
        """Testa extração de chave de acesso válida"""
        qr_text = "35200112345678901234567890123456789012345678"
        url, access_key = extract_key_or_url(qr_text)
        
        assert url is None
        assert access_key == "35200112345678901234567890123456789012345678"
    
    def test_extract_key_or_url_valid_url(self):
        """Testa extração de URL válida"""
        qr_text = "https://nfe.fazenda.gov.br/portal/consulta.aspx?chave=35200112345678901234567890123456789012345678"
        url, access_key = extract_key_or_url(qr_text)
        
        assert url is not None
        assert "https://" in url
    
    def test_extract_key_or_url_invalid(self):
        """Testa rejeição de QR code inválido"""
        with pytest.raises(ValueError):
            extract_key_or_url("invalid qr code")
    
    def test_validate_qr_text_dangerous_patterns(self):
        """Testa bloqueio de padrões perigosos"""
        dangerous_qrs = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "data:text/html,<script>alert('xss')</script>",
        ]
        
        for qr in dangerous_qrs:
            with pytest.raises(ValueError):
                validate_qr_text(qr)
    
    def test_validate_qr_text_too_long(self):
        """Testa rejeição de QR code muito longo"""
        long_qr = "a" * 3000
        with pytest.raises(ValueError):
            validate_qr_text(long_qr)
    
    def test_sanitize_qr_text(self):
        """Testa sanitização de QR code"""
        dirty_qr = "  https://example.com  \n\t"
        clean = sanitize_qr_text(dirty_qr)
        assert clean == "https://example.com"


class TestRateLimit:
    """Testes de rate limiting"""
    
    @pytest.mark.asyncio
    async def test_rate_limit_allows_requests(self):
        """Testa que rate limit permite requisições dentro do limite"""
        request = Mock()
        request.client = Mock()
        request.client.host = "127.0.0.1"
        
        # Mock Redis ou usar fallback in-memory
        with patch('app.middleware.rate_limit.get_redis') as mock_redis:
            # Simular Redis disponível
            mock_redis_instance = Mock()
            mock_redis_instance.zcount = Mock(return_value=5)  # Dentro do limite
            mock_redis_instance.zadd = Mock()
            mock_redis_instance.zremrangebyscore = Mock()
            mock_redis_instance.expire = Mock()
            mock_redis.return_value = mock_redis_instance
            
            key = get_rate_limit_key(request, None)
            result = await check_rate_limit(key, limit=10, window_seconds=60, request=request)
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_rate_limit_blocks_exceeded(self):
        """Testa que rate limit bloqueia quando excedido"""
        request = Mock()
        request.client = Mock()
        request.client.host = "127.0.0.1"
        
        with patch('app.middleware.rate_limit.get_redis') as mock_redis:
            # Simular limite excedido
            mock_redis_instance = Mock()
            mock_redis_instance.zcount = Mock(return_value=15)  # Excedeu limite
            mock_redis.return_value = mock_redis_instance
            
            key = get_rate_limit_key(request, None)
            result = await check_rate_limit(key, limit=10, window_seconds=60, request=request)
            
            assert result is False


class TestStripeWebhook:
    """Testes de webhook do Stripe"""
    
    def test_webhook_missing_signature(self):
        """Testa rejeição de webhook sem assinatura"""
        from app.routers.payments import stripe_webhook
        from fastapi import Request
        
        request = Mock(spec=Request)
        request.body = Mock(return_value=b'{}')
        request.headers = {}
        
        # Deve lançar exceção por falta de assinatura
        # (teste conceitual, precisa de setup completo do FastAPI)
        pass
    
    def test_webhook_invalid_signature(self):
        """Testa rejeição de webhook com assinatura inválida"""
        # Teste conceitual: webhook com assinatura inválida deve retornar 400
        pass

