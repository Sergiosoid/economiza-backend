from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import redis
from slowapi.errors import RateLimitExceeded
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from app.config import settings
from app.routers import example, receipts, user, ai, payments, analytics

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
app.include_router(example.router, prefix=settings.API_V1_PREFIX, tags=["example"])
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

