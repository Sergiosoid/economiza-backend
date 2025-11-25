"""
Cliente para buscar notas fiscais de providers externos (Webmania/Serpro/Oobj)
Integração real para consulta de NFC-e
"""
import requests
import xmltodict
import logging
import time
import re
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


class ProviderUnauthorized(ProviderError):
    """Exceção para erros de autenticação (401/403)"""
    pass


def _is_allowed_host(host: str) -> bool:
    """
    Verifica se o host está na lista de permitidos (anti-SSRF).
    Suporta wildcards como *.fazenda.gov.br e whitelist customizada.
    """
    # Verificar hosts padrão
    for allowed in ALLOWED_HOSTS:
        if host == allowed or host.endswith(f".{allowed}"):
            return True
    
    # Verificar whitelist customizada
    if settings.WHITELIST_DOMAINS:
        whitelist = [d.strip() for d in settings.WHITELIST_DOMAINS.split(",") if d.strip()]
        for domain in whitelist:
            if domain.startswith("*."):
                # Wildcard: *.example.com
                base_domain = domain[2:]
                if host.endswith(f".{base_domain}") or host == base_domain:
                    return True
            elif host == domain or host.endswith(f".{domain}"):
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


def _extract_key_from_url(url: str) -> Optional[str]:
    """
    Extrai chave de acesso (44 dígitos) de uma URL.
    """
    # Buscar padrão de chave de acesso (44 dígitos)
    match = re.search(r'\d{44}', url)
    if match:
        return match.group(0)
    return None


class ProviderClient:
    """
    Cliente para integração com providers de notas fiscais.
    """
    
    def __init__(self):
        self.provider_name = settings.PROVIDER_NAME.lower()
        self.api_url = settings.PROVIDER_API_URL
        self.app_key = settings.PROVIDER_APP_KEY
        self.app_secret = settings.PROVIDER_APP_SECRET
        self.timeout = settings.PROVIDER_TIMEOUT
    
    def _get_headers(self) -> Dict[str, str]:
        """
        Retorna os headers corretos para cada provider.
        """
        if self.provider_name == "webmania":
            return {
                "app_key": self.app_key,
                "app_secret": self.app_secret,
                "Content-Type": "application/json",
            }
        elif self.provider_name == "oobj":
            return {
                "app_key": self.app_key,
                "app_secret": self.app_secret,
                "Content-Type": "application/json",
            }
        elif self.provider_name == "serpro":
            return {
                "Authorization": f"Bearer {self.app_key}",
                "Content-Type": "application/json",
            }
        else:
            # Default
            return {
                "app_key": self.app_key,
                "app_secret": self.app_secret,
                "Content-Type": "application/json",
            }
    
    def _make_request(
        self,
        method: str,
        url: str,
        data: Optional[Dict] = None,
        max_retries: int = 3
    ) -> requests.Response:
        """
        Faz requisição ao provider com retries exponenciais.
        """
        headers = self._get_headers()
        backoff = 1
        
        for attempt in range(max_retries):
            try:
                if method.upper() == "GET":
                    response = requests.get(url, headers=headers, timeout=self.timeout)
                elif method.upper() == "POST":
                    response = requests.post(url, headers=headers, json=data, timeout=self.timeout)
                else:
                    raise ValueError(f"Método HTTP não suportado: {method}")
                
                # Tratamento de status codes específicos
                if response.status_code == 401 or response.status_code == 403:
                    logger.error(f"provider_fetch_fail: Unauthorized ({response.status_code})")
                    raise ProviderUnauthorized("Erro de autenticação com o provider")
                
                if response.status_code == 404:
                    logger.error("provider_fetch_fail: Not found (404)")
                    raise ProviderNotFound("Nota fiscal não encontrada")
                
                if response.status_code == 429:
                    logger.error("provider_fetch_fail: Rate limit (429)")
                    raise ProviderRateLimit("Rate limit excedido. Tente novamente mais tarde.")
                
                if response.status_code >= 500:
                    # Erro do servidor - pode tentar novamente
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
                
            except (ProviderNotFound, ProviderRateLimit, ProviderUnauthorized):
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
    
    def fetch_by_key(self, key: str) -> Dict[str, Any]:
        """
        Busca nota fiscal por chave de acesso usando API do provider.
        
        Args:
            key: Chave de acesso da nota fiscal (44 dígitos)
            
        Returns:
            dict com os dados da nota
            
        Raises:
            ProviderError: Se houver erro ao buscar a nota
            ProviderNotFound: Se a nota não for encontrada (404)
            ProviderRateLimit: Se exceder rate limit (429)
            ProviderUnauthorized: Se houver erro de autenticação (401/403)
        """
        if not self.api_url or not self.app_key or not self.app_secret:
            raise ProviderError("Provider não configurado. Configure PROVIDER_API_URL, PROVIDER_APP_KEY e PROVIDER_APP_SECRET")
        
        logger.info(f"Fetching note by key: {key[:10]}... (provider: {self.provider_name})")
        
        # Validar chave (44 dígitos)
        if not re.match(r'^\d{44}$', key):
            raise ProviderError(f"Chave de acesso inválida: deve ter 44 dígitos")
        
        # Construir URL do endpoint
        endpoint = f"{self.api_url.rstrip('/')}/{key}"
        
        try:
            response = self._make_request("GET", endpoint)
            
            # Processar resposta
            content_type = response.headers.get("Content-Type", "").lower()
            
            # Se for XML, converter para dict
            if "xml" in content_type or response.text.strip().startswith("<?xml"):
                logger.info("provider_fetch_ok: Key (XML)")
                data = xmltodict.parse(response.text)
                return data
            
            # Se for JSON, processar
            try:
                json_data = response.json()
                
                # Verificar formato de resposta do Webmania/Oobj
                if isinstance(json_data, dict):
                    # Verificar se há campo "erro" ou "sucesso"
                    if "erro" in json_data:
                        error_msg = json_data.get("erro", {}).get("mensagem", "Erro desconhecido")
                        if "não encontrada" in error_msg.lower() or "inexistente" in error_msg.lower():
                            raise ProviderNotFound(f"Nota fiscal não encontrada: {error_msg}")
                        raise ProviderError(f"Erro do provider: {error_msg}")
                    
                    if "retorno" in json_data:
                        # Formato Webmania/Oobj
                        logger.info("provider_fetch_ok: Key (JSON - formato provider)")
                        return json_data
                    
                    # Formato genérico
                    logger.info("provider_fetch_ok: Key (JSON)")
                    return json_data
                
                return json_data
                
            except ValueError:
                # Não é JSON válido
                logger.warning("Response não é JSON válido, retornando como texto")
                return {"raw": response.text}
                
        except (ProviderNotFound, ProviderRateLimit, ProviderUnauthorized):
            raise
        except ProviderError:
            raise
        except Exception as e:
            logger.error(f"provider_fetch_fail: {str(e)}", exc_info=True)
            raise ProviderError(f"Erro ao buscar nota fiscal: {str(e)}")
    
    def fetch_by_url(self, url: str) -> Dict[str, Any]:
        """
        Busca nota fiscal por URL.
        NÃO acessa qualquer URL direto para evitar SSRF.
        Valida host e extrai chave da URL para chamar fetch_by_key.
        
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
        
        # Extrair chave de acesso da URL
        access_key = _extract_key_from_url(url)
        
        if not access_key:
            raise ProviderError("Não foi possível extrair chave de acesso da URL")
        
        # Usar fetch_by_key com a chave extraída
        logger.info(f"Extracted access key from URL: {access_key[:10]}...")
        return self.fetch_by_key(access_key)


# Instância global do cliente
_client_instance: Optional[ProviderClient] = None


def get_provider_client() -> ProviderClient:
    """
    Retorna instância singleton do ProviderClient.
    """
    global _client_instance
    if _client_instance is None:
        _client_instance = ProviderClient()
    return _client_instance


# Funções de compatibilidade (mantidas para não quebrar código existente)
def fetch_by_key(key: str) -> Dict[str, Any]:
    """Wrapper para compatibilidade"""
    return get_provider_client().fetch_by_key(key)


def fetch_by_url(url: str) -> Dict[str, Any]:
    """Wrapper para compatibilidade"""
    return get_provider_client().fetch_by_url(url)
