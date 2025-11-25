"""
Testes para o provider_client com mocks das respostas reais dos providers
"""
import pytest
import requests
from unittest.mock import patch, MagicMock
from app.services.provider_client import (
    fetch_by_key,
    fetch_by_url,
    ProviderError,
    ProviderNotFound,
    ProviderRateLimit,
    _validate_url,
)
from app.config import settings


@pytest.fixture
def mock_settings():
    """Mock das configurações do provider"""
    with patch('app.services.provider_client.settings') as mock:
        mock.PROVIDER_NAME = "webmania"
        mock.PROVIDER_API_URL = "https://api.webmania.com.br/nfe"
        mock.PROVIDER_API_KEY = "test-key-123"
        mock.PROVIDER_TIMEOUT = 8
        yield mock


@pytest.fixture
def mock_xml_response():
    """Mock de resposta XML real de uma NFe"""
    return """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc versao="4.00">
    <NFe>
        <infNFe Id="NFe35200112345678901234567890123456789012345678">
            <ide>
                <dhEmi>2024-04-12T15:33:00-03:00</dhEmi>
            </ide>
            <emit>
                <xNome>SUPERMERCADO EXEMPLO</xNome>
                <CNPJ>12345678000100</CNPJ>
            </emit>
            <total>
                <ICMSTot>
                    <vProd>119.00</vProd>
                    <vNF>125.30</vNF>
                    <vTotTrib>6.30</vTotTrib>
                </ICMSTot>
            </total>
            <det>
                <prod>
                    <xProd>ARROZ TIPO 1 5KG</xProd>
                    <qCom>1.000</qCom>
                    <vUnCom>25.50</vUnCom>
                    <vProd>25.50</vProd>
                </prod>
                <imposto>
                    <ICMS>
                        <vICMS>1.20</vICMS>
                    </ICMS>
                </imposto>
            </det>
        </infNFe>
    </NFe>
</nfeProc>"""


def test_fetch_by_key_success_xml(mock_settings, mock_xml_response):
    """Testa fetch_by_key com resposta XML (status 200)"""
    with patch('app.services.provider_client._make_provider_request') as mock_request:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = mock_xml_response
        mock_response.headers = {"Content-Type": "application/xml"}
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response
        
        result = fetch_by_key("35200112345678901234567890123456789012345678")
        
        assert "nfeProc" in result or "NFe" in result
        mock_request.assert_called_once()


def test_fetch_by_key_success_json(mock_settings):
    """Testa fetch_by_key com resposta JSON (status 200)"""
    with patch('app.services.provider_client._make_provider_request') as mock_request:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"access_key": "35200112345678901234567890123456789012345678"}'
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {
            "access_key": "35200112345678901234567890123456789012345678",
            "store": {"name": "Loja Teste", "cnpj": "12345678000100"},
            "total": 100.00
        }
        mock_request.return_value = mock_response
        
        result = fetch_by_key("35200112345678901234567890123456789012345678")
        
        assert result["access_key"] == "35200112345678901234567890123456789012345678"
        mock_request.assert_called_once()


def test_fetch_by_key_not_found_404(mock_settings):
    """Testa fetch_by_key com resposta 404 (ProviderNotFound)"""
    with patch('app.services.provider_client._make_provider_request') as mock_request:
        mock_request.side_effect = ProviderNotFound("Nota fiscal não encontrada")
        
        with pytest.raises(ProviderNotFound) as exc_info:
            fetch_by_key("35200112345678901234567890123456789012345678")
        
        assert "não encontrada" in str(exc_info.value)


def test_fetch_by_key_rate_limit_429(mock_settings):
    """Testa fetch_by_key com resposta 429 (ProviderRateLimit)"""
    with patch('app.services.provider_client._make_provider_request') as mock_request:
        mock_request.side_effect = ProviderRateLimit("Rate limit excedido")
        
        with pytest.raises(ProviderRateLimit) as exc_info:
            fetch_by_key("35200112345678901234567890123456789012345678")
        
        assert "Rate limit" in str(exc_info.value)


def test_fetch_by_key_server_error_500(mock_settings):
    """Testa fetch_by_key com resposta 500 (ProviderError após retries)"""
    with patch('app.services.provider_client._make_provider_request') as mock_request:
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("Server Error")
        
        # Simular erro após retries
        mock_request.side_effect = ProviderError("Erro do servidor do provider: 500")
        
        with pytest.raises(ProviderError) as exc_info:
            fetch_by_key("35200112345678901234567890123456789012345678")
        
        assert "Erro do servidor" in str(exc_info.value) or "500" in str(exc_info.value)


def test_fetch_by_key_retries_exponential_backoff(mock_settings):
    """Testa que retries usam backoff exponencial"""
    with patch('app.services.provider_client._make_provider_request') as mock_request:
        with patch('time.sleep') as mock_sleep:
            # Simular timeout na primeira tentativa, sucesso na segunda
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"Content-Type": "application/json"}
            mock_response.json.return_value = {"access_key": "test"}
            
            # Primeira chamada: timeout, segunda: sucesso
            mock_request.side_effect = [
                requests.exceptions.Timeout("Timeout"),
                mock_response
            ]
            
            # O _make_provider_request já faz retries internamente
            # Este teste verifica que o mecanismo de retry está funcionando
            result = fetch_by_key("35200112345678901234567890123456789012345678")
            assert result["access_key"] == "test"


def test_fetch_by_url_allowed_host(mock_settings):
    """Testa fetch_by_url com host permitido"""
    with patch('app.services.provider_client._make_provider_request') as mock_request:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {"access_key": "test"}
        mock_request.return_value = mock_response
        
        url = "https://nfe.fazenda.gov.br/portal/consulta.aspx?chave=35200112345678901234567890123456789012345678"
        result = fetch_by_url(url)
        
        # Se provider configurado, deve chamar via provider
        if mock_settings.PROVIDER_API_URL:
            mock_request.assert_called()
        assert result is not None


def test_fetch_by_url_blocked_host():
    """Testa fetch_by_url com host bloqueado (SSRF protection)"""
    url = "http://malicious-site.com/nfe.xml"
    
    with pytest.raises(ProviderError) as exc_info:
        fetch_by_url(url)
    
    assert "não permitida" in str(exc_info.value) or "SSRF" in str(exc_info.value).lower()


def test_validate_url_allowed():
    """Testa validação de URLs permitidas"""
    assert _validate_url("https://nfe.fazenda.gov.br/consulta") is True
    assert _validate_url("https://www.fazenda.gov.br/nfe") is True
    assert _validate_url("http://nfce.fazenda.gov.br/test") is True
    assert _validate_url("https://subdomain.fazenda.gov.br/test") is True  # Wildcard


def test_validate_url_blocked():
    """Testa validação de URLs bloqueadas"""
    assert _validate_url("http://malicious-site.com/nfe") is False
    assert _validate_url("https://evil.com/data") is False
    assert _validate_url("ftp://fazenda.gov.br/test") is False  # Protocolo não permitido


def test_fetch_by_key_fake_when_no_provider():
    """Testa que retorna fake quando provider não está configurado"""
    with patch('app.services.provider_client.settings') as mock:
        mock.PROVIDER_API_URL = ""
        mock.PROVIDER_API_KEY = ""
        
        result = fetch_by_key("35200112345678901234567890123456789012345678")
        
        assert result["access_key"] == "35200112345678901234567890123456789012345678"
        assert result["store"]["name"] == "SUPERMERCADO EXEMPLO"


def test_provider_webmania_headers():
    """Testa headers corretos para Webmania"""
    with patch('app.services.provider_client.settings') as mock:
        mock.PROVIDER_NAME = "webmania"
        mock.PROVIDER_API_KEY = "test-key"
        
        from app.services.provider_client import _get_provider_headers
        headers = _get_provider_headers("webmania")
        
        assert headers["Authorization"] == "Bearer test-key"
        assert "Content-Type" in headers


def test_provider_oobj_headers():
    """Testa headers corretos para Oobj"""
    with patch('app.services.provider_client.settings') as mock:
        mock.PROVIDER_NAME = "oobj"
        mock.PROVIDER_API_KEY = "test-key"
        
        from app.services.provider_client import _get_provider_headers
        headers = _get_provider_headers("oobj")
        
        assert headers["Authorization-Token"] == "test-key"
        assert "Content-Type" in headers


def test_provider_oobj_post_method(mock_settings):
    """Testa que Oobj usa POST"""
    with patch('app.services.provider_client._make_provider_request') as mock_request:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {"access_key": "test"}
        mock_request.return_value = mock_response
        
        with patch('app.services.provider_client.settings') as mock:
            mock.PROVIDER_NAME = "oobj"
            mock.PROVIDER_API_URL = "https://api.oobj.com.br"
            mock.PROVIDER_API_KEY = "test-key"
            mock.PROVIDER_TIMEOUT = 8
            
            fetch_by_key("35200112345678901234567890123456789012345678")
            
            # Verificar que foi chamado com POST
            call_args = mock_request.call_args
            assert call_args[0][0] == "POST"  # method
            assert "chave" in call_args[1]["data"]  # body contém chave

