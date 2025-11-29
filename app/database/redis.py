"""
Conexão Redis para rate limiting e cache
"""
import logging
import redis.asyncio as redis
from app.config import settings

logger = logging.getLogger(__name__)

redis_client = None


async def get_redis():
    """
    Retorna cliente Redis singleton.
    Cria conexão se não existir.
    """
    global redis_client
    
    if redis_client is None:
        try:
            redis_client = redis.from_url(
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
    
    return redis_client


async def close_redis():
    """Fecha conexão Redis."""
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None
        logger.info("Redis connection closed")

