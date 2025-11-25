from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.config import settings
from app.routers import example, receipts

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(
    title="Economiza API",
    description="API backend do Economiza",
    version="1.0.0",
    debug=settings.DEBUG,
)

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


@app.get("/")
async def root():
    return {"message": "Economiza API está funcionando!"}


@app.get("/health")
async def health():
    return {"status": "healthy"}

