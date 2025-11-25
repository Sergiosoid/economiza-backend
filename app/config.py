from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    
    # API
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True
    
    # CORS
    CORS_ORIGINS: list[str] = ["*"]
    
    # Provider API (Webmania/Serpro/Oobj)
    PROVIDER_NAME: str = "webmania"  # webmania | oobj | serpro
    PROVIDER_API_URL: str = ""
    PROVIDER_APP_KEY: str = ""
    PROVIDER_APP_SECRET: str = ""
    PROVIDER_TIMEOUT: int = 10
    WHITELIST_DOMAINS: str = ""  # Domínios permitidos separados por vírgula
    
    # Vector DB (Supabase) - Opcional
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    
    # Redis (para Celery e rate limiting)
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    
    # Rate Limiting
    RATE_LIMIT_PER_IP: str = "30/minute"
    RATE_LIMIT_PER_USER: str = "60/minute"
    
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
        case_sensitive=True,
    )


settings = Settings()

