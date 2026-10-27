import time

import pytest
from fastapi import HTTPException

from app.api import auth
from app.api.auth import verify_api_key
from app.config import Settings, settings


@pytest.fixture(autouse=True)
def api_keys(monkeypatch):
    monkeypatch.setattr(settings, "API_KEYS", "admin:geheim-123,service:anderer-key")


def test_valid_key_returns_name():
    assert verify_api_key("anderer-key") == "service"


@pytest.mark.parametrize("key", ["falsch", "geheim-12", "geheim-1234", "ümlaut"])
def test_invalid_key_rejected(key):
    with pytest.raises(HTTPException) as exc:
        verify_api_key(key)
    assert exc.value.status_code == 401


def test_missing_key_rejected():
    with pytest.raises(HTTPException) as exc:
        verify_api_key(None)
    assert exc.value.status_code == 401


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "sehr-geheimes-pw")
    auth._FAILED_LOGINS.clear()
    yield
    auth._FAILED_LOGINS.clear()


def test_login_returns_valid_token(admin):
    token = auth.authenticate("admin", "sehr-geheimes-pw", "1.2.3.4")
    assert auth.verify_token(token)["sub"] == "admin"


@pytest.mark.parametrize("user,pw", [("admin", "falsch"), ("root", "sehr-geheimes-pw"), ("", "")])
def test_login_wrong_credentials_rejected(admin, user, pw):
    with pytest.raises(HTTPException) as exc:
        auth.authenticate(user, pw, "1.2.3.4")
    assert exc.value.status_code == 401


def test_login_locked_after_too_many_failures(admin):
    for _ in range(auth.MAX_FAILED_LOGINS):
        with pytest.raises(HTTPException):
            auth.authenticate("admin", "falsch", "1.2.3.4")
    # Auch das richtige Passwort wird während der Sperre abgewiesen
    with pytest.raises(HTTPException) as exc:
        auth.authenticate("admin", "sehr-geheimes-pw", "1.2.3.4")
    assert exc.value.status_code == 429
    # Andere Clients sind nicht betroffen
    assert auth.authenticate("admin", "sehr-geheimes-pw", "5.6.7.8")


def test_lockout_expires(admin, monkeypatch):
    for _ in range(auth.MAX_FAILED_LOGINS):
        with pytest.raises(HTTPException):
            auth.authenticate("admin", "falsch", "1.2.3.4")
    later = time.time() + auth.LOCKOUT_SECONDS + 1
    monkeypatch.setattr(auth.time, "time", lambda: later)
    assert auth.authenticate("admin", "sehr-geheimes-pw", "1.2.3.4")


def test_login_disabled_without_password(admin, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "")
    with pytest.raises(HTTPException) as exc:
        auth.authenticate("admin", "", "1.2.3.4")
    assert exc.value.status_code == 503


def test_require_auth_accepts_token_or_api_key(admin):
    token = auth.authenticate("admin", "sehr-geheimes-pw", "1.2.3.4")
    assert auth.require_auth(f"Bearer {token}", None) == "admin"
    assert auth.require_auth(None, "geheim-123") == "admin"


@pytest.mark.parametrize("header", ["Bearer kaputt", "Basic abc", "Bearer "])
def test_require_auth_rejects_bad_token(header):
    with pytest.raises(HTTPException) as exc:
        auth.require_auth(header, None)
    assert exc.value.status_code == 401


def test_require_auth_rejects_missing_credentials():
    with pytest.raises(HTTPException) as exc:
        auth.require_auth(None, None)
    assert exc.value.status_code == 401


def test_short_jwt_secret_rejected():
    with pytest.raises(ValueError):
        Settings(JWT_SECRET="change-this-in-production")


def test_short_admin_password_rejected():
    with pytest.raises(ValueError):
        Settings(ADMIN_PASSWORD="kurz")


def test_token_invalid_after_admin_rename(admin, monkeypatch):
    token = auth.authenticate("admin", "sehr-geheimes-pw", "1.2.3.4")
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "neuer-admin")
    with pytest.raises(HTTPException) as exc:
        auth.require_auth(f"Bearer {token}", None)
    assert exc.value.status_code == 401


@pytest.mark.parametrize("keys", ["admin:kurz", "admin:" + "x" * 20 + ",svc:abc"])
def test_short_api_key_rejected(keys):
    with pytest.raises(ValueError):
        Settings(API_KEYS=keys)


def test_valid_api_keys_accepted():
    assert Settings(API_KEYS="admin:" + "x" * 16 + ", svc:" + "y" * 32).parsed_api_keys["svc"] == "y" * 32
