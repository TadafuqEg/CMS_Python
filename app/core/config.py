"""
Configuration settings for the OCPP Central Management System
"""

import os
import ssl
from typing import List, Optional, Tuple, Dict, Any
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
    OCPP_WEBSOCKET_PORT: int = 1025
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

def create_ssl_context() -> Optional[ssl.SSLContext]:
    """
    Create SSL context with cipher suites matching central_system.py
    Includes TLS-ECDHE-RSA-WITH-AES-128-CBC-SHA and other modern cipher suites
    
    Cipher suites: ECDHE-RSA-AES128-SHA:ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS
    Minimum TLS version: TLSv1_2
    
    Note: This is used for WebSocket connections
    """
    import os
    import logging
    
    logger = logging.getLogger(__name__)
    
    if not settings.SSL_CERTFILE or not settings.SSL_KEYFILE:
        logger.info("SSL not enabled - certificate files not configured")
        return None
    
    # Check if certificate files exist
    if not os.path.exists(settings.SSL_KEYFILE):
        logger.warning(f"SSL private key file not found: {settings.SSL_KEYFILE}")
        return None
    
    if not os.path.exists(settings.SSL_CERTFILE):
        logger.warning(f"SSL certificate file not found: {settings.SSL_CERTFILE}")
        return None
    
    try:
        # Create SSL context
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        
        # Load certificate and private key
        context.load_cert_chain(
            certfile=settings.SSL_CERTFILE,
            keyfile=settings.SSL_KEYFILE
        )
        
        # Configure cipher suites to support TLS-ECDHE-RSA-WITH-AES-128-CBC-SHA
        # Match exactly with central_system.py configuration
        context.set_ciphers('ECDHE-RSA-AES128-SHA:ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
        
        # Set minimum TLS version to ensure compatibility
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        
        # Optional: Adjust security settings for development
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        logger.info(f"SSL context created successfully with cipher suites matching central_system.py")
        logger.info(f"  Certificate: {settings.SSL_CERTFILE}")
        logger.info(f"  Private Key: {settings.SSL_KEYFILE}")
        logger.info(f"  Configured ciphers: {context.get_ciphers()}")
        logger.info(f"  Minimum TLS version: {context.minimum_version}")
        
        return context
    except ssl.SSLError as e:
        logger.error(f"SSL error creating context: {e}")
        return None
    except Exception as e:
        logger.error(f"Error creating SSL context: {e}")
        return None

def get_ssl_cert_files() -> Tuple[Optional[str], Optional[str]]:
    """
    Get SSL certificate file paths for uvicorn
    Returns (certfile, keyfile) or (None, None) if not available
    """
    import os
    
    if not settings.SSL_CERTFILE or not settings.SSL_KEYFILE:
        return None, None
    
    # Check if certificate files exist
    if not os.path.exists(settings.SSL_KEYFILE) or not os.path.exists(settings.SSL_CERTFILE):
        return None, None
    
    return settings.SSL_CERTFILE, settings.SSL_KEYFILE

def get_uvicorn_ssl_kwargs() -> Dict[str, Any]:
    """
    Get SSL keyword arguments for uvicorn.run()
    Returns a dictionary with ssl_keyfile and ssl_certfile
    """
    ssl_certfile, ssl_keyfile = get_ssl_cert_files()
    
    kwargs = {}
    if ssl_keyfile:
        kwargs['ssl_keyfile'] = ssl_keyfile
    if ssl_certfile:
        kwargs['ssl_certfile'] = ssl_certfile
    
    return kwargs
