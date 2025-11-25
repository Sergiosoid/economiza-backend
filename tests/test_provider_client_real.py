"""
Testes para provider_client com formato real do Webmania/Oobj
"""
import pytest
from unittest.mock import patch, MagicMock
from app.services.provider_client import (
    ProviderClient,
    ProviderError,
    ProviderNotFound,
    ProviderRateLimit,
    ProviderUnauthorized,
)
from app.config import settings


@pytest.fixture
def mock_settings():
    """Mock das configurações do provider"""
    with patch('app.services.provider_client.settings') as mock:
        mock.PROVIDER_NAME = "webmania"
        mock.PROVIDER_API_URL = "https://api.webmania.com.br/2/nfce/consulta"
        mock.PROVIDER_APP_KEY = "test-app-key"
        mock.PROVIDER_APP_SECRET = "test-app-secret"
        mock.PROVIDER_TIMEOUT = 10
        mock.WHITELIST_DOMAINS = ""
        yield mock


@pytest.fixture
def provider_client(mock_settings):
    """Cria instância do ProviderClient"""
    return ProviderClient()


@pytest.fixture
def mock_webmania_response_success():
    """Mock de resposta real do Webmania (sucesso)"""
    return {
        "retorno": {
            "chave": "35200112345678901234567890123456789012345678",
            "data_emissao": "2024-04-12T15:33:00-03:00",
            "emitente": {
                "razao_social": "SUPERMERCADO EXEMPLO LTDA",
                "cnpj": "12345678000100"
            },
            "produto": [
                {
                    "descricao": "ARROZ TIPO 1 5KG",
                    "quantidade": "1.000",
                    "valor_unitario": "25.50",
                    "valor_total": "25.50",
                    "valor_imposto": "1.20",
                    "codigo_barras": "7891234567890"
                },
                {
                    "descricao": "FEIJAO PRETO 1KG",
                    "quantidade": "2.000",
                    "valor_unitario": "8.50",
                    "valor_total": "17.00",
                    "valor_imposto": "0.85"
                }
            ],
            "total": "125.30",
            "subtotal": "119.00",
            "total_impostos": "6.30"
        }
    }


def test_fetch_by_key_success(provider_client, mock_webmania_response_success):
    """Testa busca por chave com sucesso"""
    with patch('app.services.provider_client.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = mock_webmania_response_success
        mock_get.return_value = mock_response
        
        result = provider_client.fetch_by_key("35200112345678901234567890123456789012345678")
        
        assert "retorno" in result
        assert result["retorno"]["chave"] == "35200112345678901234567890123456789012345678"
        assert "produto" in result["retorno"]


def test_fetch_by_key_not_found(provider_client):
    """Testa busca por chave inexistente"""
    with patch('app.services.provider_client.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        with pytest.raises(ProviderNotFound):
            provider_client.fetch_by_key("35200112345678901234567890123456789012345678")


def test_fetch_by_key_rate_limit(provider_client):
    """Testa rate limit (429)"""
    with patch('app.services.provider_client.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response
        
        with pytest.raises(ProviderRateLimit):
            provider_client.fetch_by_key("35200112345678901234567890123456789012345678")


def test_fetch_by_key_unauthorized(provider_client):
    """Testa erro de autenticação (401)"""
    with patch('app.services.provider_client.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response
        
        with pytest.raises(ProviderUnauthorized):
            provider_client.fetch_by_key("35200112345678901234567890123456789012345678")


def test_fetch_by_key_invalid_key(provider_client):
    """Testa chave inválida"""
    with pytest.raises(ProviderError, match="Chave de acesso inválida"):
        provider_client.fetch_by_key("123")  # Chave muito curta


def test_fetch_by_key_provider_error_response(provider_client):
    """Testa resposta com erro do provider"""
    error_response = {
        "erro": {
            "mensagem": "Nota fiscal não encontrada",
            "codigo": "404"
        }
    }
    
    with patch('app.services.provider_client.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = error_response
        mock_get.return_value = mock_response
        
        with pytest.raises(ProviderNotFound):
            provider_client.fetch_by_key("35200112345678901234567890123456789012345678")


def test_fetch_by_url_valid(provider_client, mock_webmania_response_success):
    """Testa fetch por URL válida"""
    url = "https://nfce.fazenda.gov.br/consulta?chave=35200112345678901234567890123456789012345678"
    
    with patch('app.services.provider_client.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = mock_webmania_response_success
        mock_get.return_value = mock_response
        
        result = provider_client.fetch_by_url(url)
        
        assert "retorno" in result


def test_fetch_by_url_invalid_host(provider_client):
    """Testa fetch por URL com host não permitido (SSRF)"""
    url = "http://malicious-site.com/note.xml"
    
    with pytest.raises(ProviderError, match="URL não permitida"):
        provider_client.fetch_by_url(url)


def test_fetch_by_url_no_key(provider_client):
    """Testa fetch por URL sem chave de acesso"""
    url = "https://nfce.fazenda.gov.br/consulta"
    
    with pytest.raises(ProviderError, match="Não foi possível extrair chave"):
        provider_client.fetch_by_url(url)


def test_provider_not_configured():
    """Testa quando provider não está configurado"""
    with patch('app.services.provider_client.settings') as mock_settings:
        mock_settings.PROVIDER_API_URL = ""
        mock_settings.PROVIDER_APP_KEY = ""
        mock_settings.PROVIDER_APP_SECRET = ""
        
        client = ProviderClient()
        
        with pytest.raises(ProviderError, match="Provider não configurado"):
            client.fetch_by_key("35200112345678901234567890123456789012345678")

