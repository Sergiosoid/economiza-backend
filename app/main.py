from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import redis
from slowapi.errors import RateLimitExceeded
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from app.config import settings
from app.routers import receipts, user, ai, payments, analytics

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Inicializar limiter
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_URL,
    default_limits=[settings.RATE_LIMIT_PER_IP]
)

app = FastAPI(
    title="Economiza API",
    description="API backend do Economiza",
    version="1.0.0",
    debug=settings.DEBUG,
)

# Limpar qualquer schema OpenAPI customizado anterior
app.openapi_schema = None

# Adicionar limiter ao app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir routers
app.include_router(receipts.router, prefix=settings.API_V1_PREFIX, tags=["receipts"])
app.include_router(user.router, prefix=settings.API_V1_PREFIX, tags=["user"])
app.include_router(ai.router, prefix=settings.API_V1_PREFIX, tags=["ai"])
app.include_router(payments.router, prefix=settings.API_V1_PREFIX, tags=["payments"])
app.include_router(analytics.router, prefix=settings.API_V1_PREFIX, tags=["analytics"])




@app.get("/")
async def root():
    return {"message": "Economiza API está funcionando!"}


@app.get("/health")
async def health():
    """Health check básico"""
    return {"status": "healthy"}


@app.get("/health/detailed")
async def health_detailed():
    """Health check detalhado com status de dependências"""
    health_status = {
        "status": "healthy",
        "checks": {}
    }
    
    # Verificar Redis
    try:
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        health_status["checks"]["redis"] = "ok"
    except Exception as e:
        health_status["checks"]["redis"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    
    # Verificar banco de dados
    try:
        from app.database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        health_status["checks"]["database"] = "ok"
    except Exception as e:
        health_status["checks"]["database"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"
    
    # Verificar Celery
    try:
        from app.celery_app import celery_app
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        if stats:
            health_status["checks"]["celery"] = "ok"
        else:
            health_status["checks"]["celery"] = "no workers"
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["checks"]["celery"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    
    status_code = 200 if health_status["status"] == "healthy" else 503
    return JSONResponse(content=health_status, status_code=status_code)


@app.get("/health/ready")
async def health_ready():
    """Readiness check - verifica se a aplicação está pronta para receber tráfego"""
    try:
        # Verificar banco de dados
        from app.database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "error": str(e)}
        )


@app.get("/health/live")
async def health_live():
    """Liveness check - verifica se a aplicação está viva"""
    return {"status": "alive"}


@app.get("/health/db")
async def health_db():
    """
    Health check específico para banco de dados PostgreSQL.
    Verifica conexão e executa query simples.
    """
    try:
        from app.database import engine
        from sqlalchemy import text
        
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1 as health_check"))
            row = result.fetchone()
            
            if row and row[0] == 1:
                return {
                    "status": "healthy",
                    "service": "postgresql",
                    "message": "Database connection successful"
                }
            else:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "unhealthy",
                        "service": "postgresql",
                        "message": "Database query failed"
                    }
                )
    except Exception as e:
        logger.error(f"Database health check failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": "postgresql",
                "error": str(e)
            }
        )


@app.get("/health/provider")
async def health_provider():
    """
    Health check para provider de notas fiscais.
    Testa conectividade com provider usando chave fake ou ping.
    """
    try:
        from app.services.provider_client import ProviderClient
        from app.config import settings
        
        # Verificar se provider está configurado
        if not settings.PROVIDER_API_URL or not settings.PROVIDER_APP_KEY:
            return {
                "status": "not_configured",
                "service": "provider",
                "message": "Provider not configured (using fake data for development)"
            }
        
        # Tentar criar cliente (valida configuração)
        try:
            client = ProviderClient()
            
            # Verificar se tem credenciais
            if not client.app_key or not client.app_secret:
                return {
                    "status": "not_configured",
                    "service": "provider",
                    "message": "Provider credentials not set"
                }
            
            # Se provider estiver configurado, considerar healthy
            # (não fazer request real para não consumir quota)
            return {
                "status": "healthy",
                "service": "provider",
                "provider_name": settings.PROVIDER_NAME,
                "message": "Provider configured and ready"
            }
            
        except Exception as e:
            logger.warning(f"Provider health check warning: {e}")
            return {
                "status": "degraded",
                "service": "provider",
                "error": str(e)
            }
            
    except Exception as e:
        logger.error(f"Provider health check failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": "provider",
                "error": str(e)
            }
        )

