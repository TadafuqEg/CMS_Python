"""
Security utilities for JWT authentication and authorization
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
from jwt import PyJWTError
from fastapi import HTTPException, status
from app.core.config import settings

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Dict[str, Any]:
    """Verify JWT token and return payload"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

def check_permission(user_roles: list, required_permission: str) -> bool:
    """Check if user has required permission"""
    # Define role-based permissions
    role_permissions = {
        "admin": [
            "chargers:read", "chargers:write", "chargers:delete",
            "ocpp:control", "ocpp:config", "ocpp:reboot",
            "sessions:read", "sessions:write", "sessions:delete",
            "logs:read", "system:admin"
        ],
        "operator": [
            "chargers:read", "chargers:write",
            "ocpp:control", "sessions:read", "sessions:write",
            "logs:read"
        ],
        "maintenance": [
            "chargers:read", "ocpp:control", "ocpp:reboot",
            "logs:read"
        ],
        "viewer": [
            "chargers:read", "sessions:read", "logs:read"
        ],
        "partner": [
            "chargers:read", "sessions:read"
        ]
    }
    
    for role in user_roles:
        if role in role_permissions and required_permission in role_permissions[role]:
            return True
    return False

def require_permission(permission: str):
    """Decorator to require specific permission"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # This would be used with dependency injection in FastAPI
            # For now, it's a placeholder for permission checking
            return func(*args, **kwargs)
        return wrapper
    return decorator
