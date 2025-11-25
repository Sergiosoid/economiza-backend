"""
Cliente para buscar notas fiscais de providers externos (Webmania/Serpro/Oobj)
"""
import requests
import xmltodict
import logging
import time
from urllib.parse import urlparse
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)

# Hosts permitidos para fetch_by_url (anti-SSRF)
ALLOWED_HOSTS = [
    "fazenda.gov.br",
    "nfe.fazenda.gov.br",
    "www.fazenda.gov.br",
    "nfce.fazenda.gov.br",
    "*.fazenda.gov.br",
]


class ProviderError(Exception):
    """Exceção genérica para erros do provider"""
    pass


class ProviderNotFound(ProviderError):
    """Exceção para quando a nota não é encontrada (404)"""
    pass


class ProviderRateLimit(ProviderError):
    """Exceção para rate limit (429)"""
    pass


def _is_allowed_host(host: str) -> bool:
    """
    Verifica se o host está na lista de permitidos (anti-SSRF).
    Suporta wildcards como *.fazenda.gov.br
    """
    for allowed in ALLOWED_HOSTS:
        if allowed.startswith("*."):
            # Wildcard: *.fazenda.gov.br
            domain = allowed[2:]
            if host.endswith(domain):
                return True
        elif host == allowed:
            return True
    return False


def _validate_url(url: str) -> bool:
    """
    Valida se a URL é permitida (anti-SSRF).
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ["http", "https"]:
            return False
        host = parsed.netloc.split(":")[0]  # Remove porta
        return _is_allowed_host(host)
    except Exception:
        return False


def _get_provider_headers(provider_name: str) -> Dict[str, str]:
    """
    Retorna os headers corretos para cada provider.
    """
    provider_name = provider_name.lower()
    
    if provider_name == "webmania":
        return {
            "Authorization": f"Bearer {settings.PROVIDER_API_KEY}",
            "Content-Type": "application/json",
        }
    elif provider_name == "oobj":
        return {
            "Authorization-Token": settings.PROVIDER_API_KEY,
            "Content-Type": "application/json",
        }
    elif provider_name == "serpro":
        return {
            "Authorization": f"Bearer {settings.PROVIDER_API_KEY}",
            "Content-Type": "application/json",
        }
    else:
        # Default
        return {
            "Authorization": f"Bearer {settings.PROVIDER_API_KEY}",
            "Content-Type": "application/json",
        }


def _get_provider_endpoint(provider_name: str, key: str) -> str:
    """
    Retorna o endpoint correto para cada provider.
    """
    provider_name = provider_name.lower()
    base_url = settings.PROVIDER_API_URL.rstrip("/")
    
    if provider_name == "webmania":
        # Webmania: GET /nfe/{chave}
        return f"{base_url}/{key}"
    elif provider_name == "oobj":
        # Oobj: POST /consulta com body { chave }
        return f"{base_url}/consulta"
    elif provider_name == "serpro":
        # Serpro: GET /nfe/{chave}
        return f"{base_url}/{key}"
    else:
        # Default
        return f"{base_url}/{key}"


def _make_provider_request(
    method: str,
    url: str,
    headers: Dict[str, str],
    data: Optional[Dict] = None,
    timeout: int = 8,
    max_retries: int = 3
) -> requests.Response:
    """
    Faz requisição ao provider com retries exponenciais.
    """
    backoff = 1
    
    for attempt in range(max_retries):
        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=data, timeout=timeout)
            else:
                raise ValueError(f"Método HTTP não suportado: {method}")
            
            # Tratamento de status codes específicos
            if response.status_code == 404:
                logger.error("provider_fetch_fail: Not found (404)")
                raise ProviderNotFound("Nota fiscal não encontrada")
            
            if response.status_code == 429:
                logger.error("provider_fetch_fail: Rate limit (429)")
                raise ProviderRateLimit("Rate limit excedido. Tente novamente mais tarde.")
            
            if response.status_code >= 500:
                # Erro do servidor - pode tentar novar
                if attempt < max_retries - 1:
                    wait_time = backoff * (2 ** attempt)
                    logger.warning(
                        f"Server error {response.status_code}, retrying in {wait_time}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait_time)
                    backoff *= 2
                    continue
                else:
                    logger.error(f"provider_fetch_fail: Server error {response.status_code}")
                    raise ProviderError(f"Erro do servidor do provider: {response.status_code}")
            
            response.raise_for_status()
            return response
            
        except (ProviderNotFound, ProviderRateLimit):
            # Não fazer retry para esses erros
            raise
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait_time = backoff * (2 ** attempt)
                logger.warning(
                    f"Timeout, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(wait_time)
                backoff *= 2
                continue
            logger.error("provider_fetch_fail: Timeout after retries")
            raise ProviderError("Timeout ao buscar nota fiscal após tentativas")
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = backoff * (2 ** attempt)
                logger.warning(
                    f"Request error, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries}): {str(e)}"
                )
                time.sleep(wait_time)
                backoff *= 2
                continue
            logger.error(f"provider_fetch_fail: {str(e)}")
            raise ProviderError(f"Erro ao buscar nota fiscal: {str(e)}")
    
    raise ProviderError("Erro ao buscar nota fiscal após todas as tentativas")


def fetch_by_url(url: str) -> Dict[str, Any]:
    """
    Busca nota fiscal por URL.
    Valida o host para evitar SSRF e envia a URL ao provider se necessário.
    
    Args:
        url: URL da nota fiscal
        
    Returns:
        dict com os dados da nota
        
    Raises:
        ProviderError: Se houver erro ao buscar ou processar a nota
    """
    logger.info(f"Fetching note from URL: {url}")
    
    # Validar URL (anti-SSRF)
    if not _validate_url(url):
        logger.error(f"provider_fetch_fail: URL não permitida (SSRF protection): {url}")
        raise ProviderError("URL não permitida por questões de segurança")
    
    # Se temos provider configurado, tentar enviar URL ao provider
    # (se o provider suportar fetch por URL)
    # Por enquanto, fazemos request direto apenas para hosts permitidos
    # Em produção, pode ser implementado endpoint específico no provider
    try:
        response = requests.get(
            url,
            timeout=settings.PROVIDER_TIMEOUT,
            headers={"User-Agent": "Economiza-Backend/1.0"}
        )
        response.raise_for_status()
        
        content_type = response.headers.get("Content-Type", "").lower()
        
        # Se for XML, converter para dict
        if "xml" in content_type or response.text.strip().startswith("<?xml"):
            logger.info("provider_fetch_ok: URL (XML)")
            data = xmltodict.parse(response.text)
            return data
        
        # Se for JSON, retornar parseado
        if "json" in content_type:
            logger.info("provider_fetch_ok: URL (JSON)")
            return response.json()
        
        # Tentar parsear como JSON
        try:
            logger.info("provider_fetch_ok: URL (JSON fallback)")
            return response.json()
        except:
            return {"raw": response.text}
            
    except requests.exceptions.Timeout:
        logger.error("provider_fetch_fail: Timeout")
        raise ProviderError("Timeout ao buscar nota fiscal")
    except requests.exceptions.RequestException as e:
        logger.error(f"provider_fetch_fail: {str(e)}")
        raise ProviderError(f"Erro ao buscar nota fiscal: {str(e)}")


def fetch_by_key(key: str) -> Dict[str, Any]:
    """
    Busca nota fiscal por chave de acesso usando API do provider.
    Se não houver provider configurado, retorna JSON fake para desenvolvimento.
    
    Args:
        key: Chave de acesso da nota fiscal (44 dígitos)
        
    Returns:
        dict com os dados da nota
        
    Raises:
        ProviderError: Se houver erro ao buscar a nota
        ProviderNotFound: Se a nota não for encontrada (404)
        ProviderRateLimit: Se exceder rate limit (429)
    """
    # Se não houver provider configurado, retornar stub fake
    if not settings.PROVIDER_API_URL or not settings.PROVIDER_API_KEY:
        logger.info("Provider não configurado, retornando dados fake para desenvolvimento")
        return _get_fake_note(key)
    
    logger.info(f"Fetching note by key: {key[:10]}... (provider: {settings.PROVIDER_NAME})")
    
    provider_name = settings.PROVIDER_NAME.lower()
    headers = _get_provider_headers(provider_name)
    endpoint = _get_provider_endpoint(provider_name, key)
    
    try:
        # Webmania e Serpro usam GET, Oobj usa POST
        if provider_name == "oobj":
            response = _make_provider_request(
                "POST",
                endpoint,
                headers,
                data={"chave": key},
                timeout=settings.PROVIDER_TIMEOUT
            )
        else:
            response = _make_provider_request(
                "GET",
                endpoint,
                headers,
                timeout=settings.PROVIDER_TIMEOUT
            )
        
        content_type = response.headers.get("Content-Type", "").lower()
        
        # Se for XML, converter para dict
        if "xml" in content_type or response.text.strip().startswith("<?xml"):
            logger.info("provider_fetch_ok: Key (XML)")
            data = xmltodict.parse(response.text)
            return data
        
        # Se for JSON, retornar parseado
        logger.info("provider_fetch_ok: Key (JSON)")
        return response.json()
        
    except (ProviderNotFound, ProviderRateLimit):
        raise
    except ProviderError:
        raise
    except Exception as e:
        logger.error(f"provider_fetch_fail: {str(e)}")
        raise ProviderError(f"Erro ao buscar nota fiscal: {str(e)}")


def _get_fake_note(key: str) -> Dict[str, Any]:
    """
    Retorna uma nota fiscal fake para desenvolvimento.
    """
    return {
        "access_key": key,
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
            },
            {
                "description": "ACUCAR CRISTAL 1KG",
                "quantity": 1,
                "unit_price": 4.50,
                "total_price": 4.50,
                "tax_value": 0.25
            }
        ],
        "emitted_at": "2024-04-12T15:33:00"
    }
