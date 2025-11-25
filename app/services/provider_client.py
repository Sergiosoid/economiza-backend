"""
Cliente para buscar notas fiscais de providers externos (Webmania/Serpro/Oobj)
"""
import requests
import xmltodict
import logging
import time
from typing import Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Exceção para erros do provider"""
    pass


def fetch_by_url(url: str) -> Dict[str, Any]:
    """
    Busca nota fiscal por URL.
    
    Args:
        url: URL da nota fiscal
        
    Returns:
        dict com os dados da nota
        
    Raises:
        ProviderError: Se houver erro ao buscar ou processar a nota
    """
    logger.info(f"Fetching note from URL: {url}")
    
    try:
        response = requests.get(
            url,
            timeout=5,
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
        
        # Tentar parsear como JSON de qualquer forma
        try:
            logger.info("provider_fetch_ok: URL (JSON fallback)")
            return response.json()
        except:
            # Se não for JSON, retornar como texto
            logger.warning("Response is not JSON or XML, returning as text")
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
    """
    # Se não houver provider configurado, retornar stub fake
    if not settings.PROVIDER_API_URL or not settings.PROVIDER_API_KEY:
        logger.info("Provider não configurado, retornando dados fake para desenvolvimento")
        return _get_fake_note(key)
    
    logger.info(f"Fetching note by key: {key[:10]}...")
    
    max_retries = 2
    backoff = 1
    
    for attempt in range(max_retries + 1):
        try:
            response = requests.get(
                f"{settings.PROVIDER_API_URL}/nfe/{key}",
                headers={
                    "Authorization": f"Bearer {settings.PROVIDER_API_KEY}",
                    "Content-Type": "application/json"
                },
                timeout=5
            )
            response.raise_for_status()
            
            content_type = response.headers.get("Content-Type", "").lower()
            
            # Se for XML, converter para dict
            if "xml" in content_type or response.text.strip().startswith("<?xml"):
                logger.info("provider_fetch_ok: Key (XML)")
                data = xmltodict.parse(response.text)
                return data
            
            # Se for JSON, retornar parseado
            logger.info("provider_fetch_ok: Key (JSON)")
            return response.json()
            
        except requests.exceptions.Timeout:
            if attempt < max_retries:
                logger.warning(f"Timeout, retrying in {backoff}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(backoff)
                backoff *= 2
                continue
            logger.error("provider_fetch_fail: Timeout after retries")
            raise ProviderError("Timeout ao buscar nota fiscal após tentativas")
            
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                logger.warning(f"Request error, retrying in {backoff}s (attempt {attempt + 1}/{max_retries}): {str(e)}")
                time.sleep(backoff)
                backoff *= 2
                continue
            logger.error(f"provider_fetch_fail: {str(e)}")
            raise ProviderError(f"Erro ao buscar nota fiscal: {str(e)}")
    
    raise ProviderError("Erro ao buscar nota fiscal após todas as tentativas")


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
