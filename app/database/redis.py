"""
Conexão Redis para rate limiting e cache
"""
import logging
import aioredis
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)

_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    """
    Retorna cliente Redis singleton.
    Cria conexão se não existir.
    """
    global _redis_client
    
    if _redis_client is None:
        try:
            _redis_client = await aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info(f"Redis connection established: {settings.REDIS_URL}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            # Em modo DEV, pode funcionar sem Redis (fallback in-memory)
            if settings.DEV_MODE:
                logger.warning("Redis unavailable, rate limiting will use in-memory fallback")
            else:
                raise
    
    return _redis_client


async def close_redis():
    """Fecha conexão Redis."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis connection closed")

