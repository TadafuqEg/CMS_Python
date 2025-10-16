"""
Configuration settings for the OCPP Central Management System
"""

import os
from typing import List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings"""
    
    # Server configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    
    # SSL/TLS configuration
    SSL_KEYFILE: str = "key.pem"
    SSL_CERTFILE: str = "cert.pem"
    
    # CORS configuration
    ALLOWED_ORIGINS: List[str] = ["*"]
    
    # Database configuration
    DATABASE_URL: str = "sqlite:///./ocpp_cms.db"
    
    # Redis configuration (for message queue and caching)
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # JWT configuration
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # OCPP configuration
    OCPP_WEBSOCKET_HOST: str = "0.0.0.0"
    OCPP_WEBSOCKET_PORT: int = 1010
    OCPP_SUBPROTOCOLS: List[str] = ["ocpp1.6", "ocpp2.0.1"]
    
    # Message queue configuration
    MQ_BROKER_URL: str = "redis://localhost:6379/1"
    MQ_EXCHANGE: str = "ocpp_events"
    
    # Logging configuration
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "ocpp_cms.log"
    
    # Laravel CMS integration
    LARAVEL_API_URL: str = "http://localhost:8080/api"
    LARAVEL_API_KEY: str = "your-laravel-api-key"
    
    # Charger configuration
    HEARTBEAT_INTERVAL: int = 60
    METER_VALUE_INTERVAL: int = 60
    CONNECTION_TIMEOUT: int = 30
    
    # Session configuration
    SESSION_TIMEOUT: int = 3600  # 1 hour
    MAX_CONCURRENT_SESSIONS: int = 1000
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Create settings instance
settings = Settings()
