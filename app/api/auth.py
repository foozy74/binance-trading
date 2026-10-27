from fastapi import HTTPException, Header, Depends
from jose import jwt, JWTError
from app.config import settings
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import hashlib
import hmac
import time

# Fehlversuche pro Client; nach MAX_FAILED_LOGINS ist der Login LOCKOUT_SECONDS gesperrt
MAX_FAILED_LOGINS = 10
TOKEN_LIFETIME = timedelta(hours=8)
LOCKOUT_SECONDS = 15 * 60
_FAILED_LOGINS: Dict[str, List[float]] = {}


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
    expire = datetime.now(timezone.utc) + (expires_delta or TOKEN_LIFETIME)
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
    
    # Nach Umbenennen des Admins sind alte Tokens ungültig
    if not payload or payload.get("sub") != settings.ADMIN_USERNAME:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return payload["sub"]


def require_auth(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
) -> str:
    """JWT aus dem Dashboard-Login oder X-API-Key (Skripte) – eins von beiden muss gültig sein."""
    if authorization:
        return get_current_user(authorization)
    return verify_api_key(x_api_key)


def _same_secret(given: str, expected: str) -> bool:
    """Konstante Laufzeit auch bei unterschiedlicher Länge (Hashes sind immer gleich lang)."""
    return hmac.compare_digest(hashlib.sha256(given.encode()).digest(), hashlib.sha256(expected.encode()).digest())


def _recent_failures(client: str, now: float) -> List[float]:
    """Fehlversuche des Clients innerhalb des Sperrfensters."""
    return [t for t in _FAILED_LOGINS.get(client, []) if now - t < LOCKOUT_SECONDS]


def authenticate(username: str, password: str, client: str) -> str:
    """Prüft Admin-Zugangsdaten und liefert ein JWT.

    shortcut: Sperre in-memory und pro Client-IP; hinter nginx teilen sich alle Clients eine IP,
    die Sperre wirkt dann global (Login-DoS möglich, Brute-Force nicht). Upgrade: Trusted-Proxy-Header.
    """
    now = time.time()
    failures = _recent_failures(client, now)
    if len(failures) >= MAX_FAILED_LOGINS:
        raise HTTPException(status_code=429, detail="Too many failed logins, try again later")
    if not settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Login not configured (ADMIN_PASSWORD)")

    # Beide Vergleiche immer ausführen, damit die Laufzeit nichts über den Benutzernamen verrät
    user_ok = _same_secret(username, settings.ADMIN_USERNAME)
    password_ok = _same_secret(password, settings.ADMIN_PASSWORD)
    if not (user_ok and password_ok):
        _FAILED_LOGINS[client] = failures + [now]
        raise HTTPException(status_code=401, detail="Invalid username or password")

    _FAILED_LOGINS.pop(client, None)
    return create_access_token({"sub": username})
