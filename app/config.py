from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    
    # Security
    SECRET_KEY: str = "change_this_later"
    ALGORITHM: str = "HS256"
    ENVIRONMENT: str = "development"
    DEV_MODE: bool = True  # Modo desenvolvimento (permite token "test")
    
    # JWT Interno
    JWT_SECRET: str = ""  # Secret para JWT interno (se vazio, usa SECRET_KEY)
    JWT_ALGORITHM: str = "HS256"  # Algoritmo para JWT interno
    JWT_EXPIRES_MIN: int = 60  # Tempo de expiração do JWT interno em minutos
    
    # API
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True
    
    # CORS
    CORS_ORIGINS: list[str] = ["*"]
    
    # Provider API (Webmania/Serpro/Oobj/Fake)
    PROVIDER_NAME: str = "fake"  # fake | webmania | oobj | serpro
    PROVIDER_API_URL: Optional[str] = None
    PROVIDER_APP_KEY: Optional[str] = None
    PROVIDER_APP_SECRET: Optional[str] = None
    PROVIDER_TIMEOUT: int = 10
    WHITELIST_DOMAINS: str = ""  # Domínios permitidos separados por vírgula
    
    # Vector DB (Supabase) - Opcional
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    
    # Supabase Auth
    SUPABASE_JWKS_URL: str = ""  # endpoint para pegar chaves públicas (/.well-known/jwks.json)
    SUPABASE_AUDIENCE: str = ""  # Audience esperado no JWT
    
    # Redis (para Celery e rate limiting)
    REDIS_URL: str = "redis://localhost:6379/0"
    RATE_LIMIT_PREFIX: str = "economiza:"  # Prefixo para chaves Redis de rate limiting
    
    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    
    # Rate Limiting
    RATE_LIMIT_PER_IP: str = "30/minute"
    RATE_LIMIT_PER_USER: str = "30/minute"  # Limite para endpoint /scan
    
    # Encryption (Fernet key - 32 bytes base64 encoded)
    # TODO: Migrate to KMS (AWS KMS, Azure Key Vault, etc.)
    ENCRYPTION_KEY: str = ""
    
    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_ID_PRO: str = ""  # Price ID do plano PRO no Stripe
    FRONTEND_URL: str = "http://localhost:3000"  # URL do frontend para redirects
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


settings = Settings()

