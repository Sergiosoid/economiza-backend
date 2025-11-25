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
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()

