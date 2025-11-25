"""
Cliente para buscar notas fiscais de providers externos (Webmania/Serpro/Oobj)
"""
import requests
import xmltodict
import logging
import time
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)


def fetch_note_by_url(url: str) -> Dict[str, Any]:
    """
    Busca nota fiscal por URL.
    Faz request HTTP e tenta converter XML para dict se necessário.
    
    Args:
        url: URL da nota fiscal
        
    Returns:
        dict com os dados da nota
        
    Raises:
        Exception: Se houver erro ao buscar ou processar a nota
    """
    logger.info(f"Fetching note from URL: {url}")
    
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
            logger.info("Converting XML response to dict")
            data = xmltodict.parse(response.text)
            logger.info("provider_fetch_ok: URL")
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
        raise Exception("Timeout ao buscar nota fiscal")
    except requests.exceptions.RequestException as e:
        logger.error(f"provider_fetch_fail: {str(e)}")
        raise Exception(f"Erro ao buscar nota fiscal: {str(e)}")


def fetch_note_by_key(key: str) -> Dict[str, Any]:
    """
    Busca nota fiscal por chave de acesso usando API do provider.
    
    Args:
        key: Chave de acesso da nota fiscal (44 dígitos)
        
    Returns:
        dict com os dados da nota
        
    Raises:
        Exception: Se houver erro ao buscar a nota
    """
    if not settings.PROVIDER_API_URL or not settings.PROVIDER_API_KEY:
        raise Exception("PROVIDER_API_URL e PROVIDER_API_KEY devem estar configurados no .env")
    
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
                timeout=settings.PROVIDER_TIMEOUT
            )
            response.raise_for_status()
            
            content_type = response.headers.get("Content-Type", "").lower()
            
            # Se for XML, converter para dict
            if "xml" in content_type or response.text.strip().startswith("<?xml"):
                logger.info("Converting XML response to dict")
                data = xmltodict.parse(response.text)
                logger.info("provider_fetch_ok: Key")
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
            raise Exception("Timeout ao buscar nota fiscal após tentativas")
            
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                logger.warning(f"Request error, retrying in {backoff}s (attempt {attempt + 1}/{max_retries}): {str(e)}")
                time.sleep(backoff)
                backoff *= 2
                continue
            logger.error(f"provider_fetch_fail: {str(e)}")
            raise Exception(f"Erro ao buscar nota fiscal: {str(e)}")
    
    raise Exception("Erro ao buscar nota fiscal após todas as tentativas")

