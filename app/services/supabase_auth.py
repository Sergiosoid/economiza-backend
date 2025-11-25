"""
Serviço para validação de tokens JWT do Supabase
"""
import logging
import time
import requests
import jwt
from typing import Dict, Any, Optional
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from app.config import settings

logger = logging.getLogger(__name__)

# Cache de JWKS (TTL de 1 hora)
_jwks_cache: Optional[Dict[str, Any]] = None
_jwks_cache_time: float = 0
JWKS_CACHE_TTL = 3600  # 1 hora em segundos


def fetch_jwks() -> Dict[str, Any]:
    """
    Baixa e cacheia as chaves públicas (JWKS) do Supabase.
    Retorna o JWKS com cache de 1 hora.
    """
    global _jwks_cache, _jwks_cache_time
    
    # Verificar se cache ainda é válido
    current_time = time.time()
    if _jwks_cache and (current_time - _jwks_cache_time) < JWKS_CACHE_TTL:
        logger.debug("Using cached JWKS")
        return _jwks_cache
    
    if not settings.SUPABASE_JWKS_URL:
        raise ValueError("SUPABASE_JWKS_URL não configurado")
    
    try:
        logger.info(f"Fetching JWKS from {settings.SUPABASE_JWKS_URL}")
        response = requests.get(settings.SUPABASE_JWKS_URL, timeout=10)
        response.raise_for_status()
        
        jwks = response.json()
        
        # Atualizar cache
        _jwks_cache = jwks
        _jwks_cache_time = current_time
        
        logger.info(f"JWKS fetched successfully, {len(jwks.get('keys', []))} keys")
        return jwks
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching JWKS: {e}")
        # Se houver cache antigo, usar ele mesmo expirado
        if _jwks_cache:
            logger.warning("Using expired JWKS cache due to fetch error")
            return _jwks_cache
        raise


def get_public_key(jwks: Dict[str, Any], kid: str) -> Optional[Any]:
    """
    Extrai a chave pública do JWKS baseado no kid (key ID).
    """
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            try:
                # Converter JWK para chave RSA
                # JWK usa base64url encoding
                import base64
                
                def base64url_decode(value: str) -> bytes:
                    # Adicionar padding se necessário
                    padding = 4 - len(value) % 4
                    if padding != 4:
                        value += "=" * padding
                    return base64.urlsafe_b64decode(value)
                
                # Decodificar n e e
                n_bytes = base64url_decode(key["n"])
                e_bytes = base64url_decode(key["e"])
                
                n = int.from_bytes(n_bytes, byteorder="big")
                e = int.from_bytes(e_bytes, byteorder="big")
                
                # Construir chave pública RSA
                public_key = rsa.RSAPublicNumbers(e, n).public_key(default_backend())
                
                return public_key
            except Exception as e:
                logger.error(f"Error parsing public key: {e}")
                return None
    
    return None


def verify_supabase_token(token: str) -> Dict[str, Any]:
    """
    Valida o token JWT do Supabase.
    
    Args:
        token: Token JWT do Supabase
        
    Returns:
        Payload decodificado do token
        
    Raises:
        ValueError: Se o token for inválido
    """
    try:
        # Decodificar header sem validação para pegar kid
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        
        if not kid:
            raise ValueError("Token header missing 'kid'")
        
        # Buscar JWKS
        jwks = fetch_jwks()
        
        # Buscar chave pública
        public_key = get_public_key(jwks, kid)
        if not public_key:
            raise ValueError(f"Public key not found for kid: {kid}")
        
        # Decodificar e validar token
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=settings.SUPABASE_AUDIENCE if settings.SUPABASE_AUDIENCE else None,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": bool(settings.SUPABASE_AUDIENCE),
            },
        )
        
        logger.debug(f"Token validated successfully for user: {payload.get('sub')}")
        return payload
        
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        raise ValueError("Token expired")
    except jwt.InvalidAudienceError:
        logger.warning("Invalid audience")
        raise ValueError("Invalid audience")
    except jwt.InvalidSignatureError:
        logger.warning("Invalid signature")
        raise ValueError("Invalid signature")
    except Exception as e:
        logger.error(f"Error verifying token: {e}")
        raise ValueError(f"Invalid token: {str(e)}")

