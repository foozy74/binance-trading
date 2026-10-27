from fastapi import HTTPException, Header, Depends
from jose import jwt, JWTError
from app.config import settings
from datetime import datetime, timedelta
from typing import Optional
import hashlib
import hmac


def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """Verify API key from header"""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    
    api_keys = settings.parsed_api_keys
    for name, secret in api_keys.items():
        # Konstante Laufzeit, damit der Key nicht über die Antwortzeit erraten werden kann
        if hmac.compare_digest(x_api_key.encode(), secret.encode()):
            return name
    
    raise HTTPException(status_code=401, detail="Invalid API key")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=24))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm="HS256")


def verify_token(token: str) -> Optional[dict]:
    """Verify JWT token"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return payload
    except JWTError:
        return None


def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Get current user from JWT token"""
    if not authorization:
        return None
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    
    token = authorization.split(" ")[1]
    payload = verify_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return payload.get("sub")
