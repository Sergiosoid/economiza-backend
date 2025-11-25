"""
Middleware de rate limiting usando Redis
"""
import logging
import time
from typing import Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from uuid import UUID
from app.database.redis import get_redis
from app.config import settings

logger = logging.getLogger(__name__)

# Fallback in-memory para quando Redis não estiver disponível
_in_memory_limits: dict = {}


async def check_rate_limit(
    key: str,
    limit: int,
    window_seconds: int,
    request: Request
) -> bool:
    """
    Verifica se a requisição excede o limite de taxa.
    
    Args:
        key: Chave única para identificar o limite (ex: "user:123" ou "ip:192.168.1.1")
        limit: Número máximo de requisições
        window_seconds: Janela de tempo em segundos
        request: Objeto Request do FastAPI
        
    Returns:
        True se dentro do limite, False se excedeu
    """
    try:
        redis = await get_redis()
        
        # Construir chave completa
        full_key = f"{settings.RATE_LIMIT_PREFIX}{key}"
        
        # Usar sliding window com Redis
        current_time = int(time.time())
        window_start = current_time - window_seconds
        
        # Contar requisições na janela
        count = await redis.zcount(full_key, window_start, current_time)
        
        if count >= limit:
            logger.warning(f"Rate limit exceeded for key: {key} ({count}/{limit})")
            return False
        
        # Adicionar requisição atual
        await redis.zadd(full_key, {str(current_time): current_time})
        
        # Expirar chaves antigas
        await redis.zremrangebyscore(full_key, 0, window_start - 1)
        
        # Definir TTL da chave
        await redis.expire(full_key, window_seconds)
        
        return True
        
    except Exception as e:
        logger.error(f"Error checking rate limit: {e}")
        
        # Fallback in-memory em modo DEV
        if settings.DEV_MODE:
            return _check_rate_limit_in_memory(key, limit, window_seconds)
        
        # Em produção, se Redis falhar, permitir requisição (fail open)
        # Mas logar o erro
        logger.error("Redis unavailable, allowing request (fail open)")
        return True


def _check_rate_limit_in_memory(
    key: str,
    limit: int,
    window_seconds: int
) -> bool:
    """
    Fallback in-memory para rate limiting quando Redis não está disponível.
    """
    current_time = time.time()
    
    if key not in _in_memory_limits:
        _in_memory_limits[key] = []
    
    # Limpar requisições antigas
    window_start = current_time - window_seconds
    _in_memory_limits[key] = [
        ts for ts in _in_memory_limits[key] if ts > window_start
    ]
    
    # Verificar limite
    if len(_in_memory_limits[key]) >= limit:
        return False
    
    # Adicionar requisição atual
    _in_memory_limits[key].append(current_time)
    
    return True


def get_rate_limit_key(request: Request, user_id: Optional[UUID] = None) -> str:
    """
    Gera chave para rate limiting baseada em IP ou user_id.
    
    Args:
        request: Objeto Request
        user_id: ID do usuário (opcional)
        
    Returns:
        Chave para rate limiting
    """
    if user_id:
        return f"user:{user_id}"
    
    # Extrair IP do cliente
    client_ip = request.client.host if request.client else "unknown"
    
    # Se estiver atrás de proxy, tentar pegar IP real
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    
    return f"ip:{client_ip}"


async def rate_limit_middleware(
    request: Request,
    call_next,
    user_id: Optional[UUID] = None,
    limit: int = 30,
    window_seconds: int = 60
):
    """
    Middleware de rate limiting.
    
    Args:
        request: Request
        call_next: Próxima função no pipeline
        user_id: ID do usuário (opcional)
        limit: Limite de requisições
        window_seconds: Janela de tempo em segundos
        
    Returns:
        Response
    """
    key = get_rate_limit_key(request, user_id)
    
    if not await check_rate_limit(key, limit, window_seconds, request):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "rate limit exceeded"}
        )
    
    response = await call_next(request)
    return response

