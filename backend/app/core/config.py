import os
from pathlib import Path
from typing import List, Optional
try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # � $
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    backend_url: str = "http://127.0.0.1:8000"
    
    frontend_host: str = "localhost" 
    frontend_port: int = 5173
    frontend_url: str = "http://localhost:5173"
    
    # \UX $
    production_ip: Optional[str] = "220.69.200.55"
    production_backend_url: Optional[str] = "http://220.69.200.55:32375"
    production_frontend_url: Optional[str] = "http://220.69.200.55:32376"
    
    # X� $
    environment: str = "development"
    debug: bool = True
    log_level: str = "INFO"
    
    # CORS $
    allowed_origins: str = "http://localhost:3000,http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174,http://localhost:32376,http://localhost:32377,http://220.69.200.55:32376"
    
    @property
    def cors_origins(self) -> List[str]:
        """CORS origins as list"""
        return [origin.strip() for origin in self.allowed_origins.split(",")]
    
    # �H $
    secret_key: str = "your_secret_key_here_change_in_production"
    
    # pt0�t� $
    database_url: Optional[str] = "sqlite:///charging_data.db"
    redis_url: Optional[str] = "redis://localhost:6379"
    
    # �� $
    cache_ttl: int = 300  # seconds
    
    # pt0 �� $
    max_sessions_per_query: int = 10000
    default_days_lookback: int = 90
    
    # 1� $
    uvicorn_workers: int = 1
    uvicorn_max_workers: int = 4
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # X�� prefix pX� � �Q
        fields = {
            "backend_host": "BACKEND_HOST",
            "backend_port": "BACKEND_PORT", 
            "backend_url": "BACKEND_URL",
            "frontend_host": "FRONTEND_HOST",
            "frontend_port": "FRONTEND_PORT",
            "frontend_url": "FRONTEND_URL",
            "production_ip": "PRODUCTION_IP",
            "production_backend_url": "PRODUCTION_BACKEND_URL",
            "production_frontend_url": "PRODUCTION_FRONTEND_URL",
            "environment": "ENVIRONMENT",
            "debug": "DEBUG",
            "log_level": "LOG_LEVEL",
            "allowed_origins": "ALLOWED_ORIGINS",
            "secret_key": "SECRET_KEY",
            "database_url": "DATABASE_URL",
            "redis_url": "REDIS_URL",
            "cache_ttl": "CACHE_TTL",
            "max_sessions_per_query": "MAX_SESSIONS_PER_QUERY",
            "default_days_lookback": "DEFAULT_DAYS_LOOKBACK",
            "uvicorn_workers": "UVICORN_WORKERS",
            "uvicorn_max_workers": "UVICORN_MAX_WORKERS",
        }


# � $ x�4�
settings = Settings()