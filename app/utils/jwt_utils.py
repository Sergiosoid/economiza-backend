"""
Utilitários para JWT interno do backend
"""
import jwt
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from uuid import UUID
import logging
from app.config import settings

logger = logging.getLogger(__name__)


def create_internal_token(user_id: UUID, expires_min: Optional[int] = None) -> str:
    """
    Cria um token JWT interno para operações sensíveis.
    
    Args:
        user_id: ID do usuário
        expires_min: Tempo de expiração em minutos (padrão: JWT_EXPIRES_MIN)
        
    Returns:
        Token JWT assinado
    """
    if expires_min is None:
        expires_min = settings.JWT_EXPIRES_MIN
    
    # Secret para JWT interno (usa JWT_SECRET se configurado, senão SECRET_KEY)
    secret = settings.JWT_SECRET if settings.JWT_SECRET else settings.SECRET_KEY
    
    if not secret or secret == "change_this_later":
        logger.warning("JWT_SECRET not configured, using SECRET_KEY (not recommended for production)")
    
    # Payload
    now = datetime.utcnow()
    payload: Dict[str, Any] = {
        "user_id": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=expires_min),
        "type": "internal",  # Identificador de token interno
    }
    
    # Criar token
    token = jwt.encode(
        payload,
        secret,
        algorithm=settings.JWT_ALGORITHM
    )
    
    logger.debug(f"Internal JWT created for user: {user_id}, expires in {expires_min} minutes")
    return token


def verify_internal_token(token: str) -> Dict[str, Any]:
    """
    Verifica e decodifica um token JWT interno.
    
    Args:
        token: Token JWT interno
        
    Returns:
        Payload decodificado
        
    Raises:
        ValueError: Se o token for inválido, expirado ou não for um token interno
    """
    # Secret para JWT interno
    secret = settings.JWT_SECRET if settings.JWT_SECRET else settings.SECRET_KEY
    
    try:
        # Decodificar token
        payload = jwt.decode(
            token,
            secret,
            algorithms=[settings.JWT_ALGORITHM],
            options={
                "verify_signature": True,
                "verify_exp": True,
            }
        )
        
        # Verificar se é token interno
        if payload.get("type") != "internal":
            raise ValueError("Token is not an internal token")
        
        # Verificar se tem user_id
        if "user_id" not in payload:
            raise ValueError("Token missing 'user_id' claim")
        
        logger.debug(f"Internal JWT verified for user: {payload.get('user_id')}")
        return payload
        
    except jwt.ExpiredSignatureError:
        logger.warning("Internal token expired")
        raise ValueError("Token expired")
    except jwt.InvalidSignatureError:
        logger.warning("Invalid internal token signature")
        raise ValueError("Invalid signature")
    except jwt.DecodeError as e:
        logger.warning(f"Error decoding internal token: {e}")
        raise ValueError(f"Invalid token: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error verifying internal token: {e}")
        raise ValueError(f"Token verification failed: {str(e)}")

