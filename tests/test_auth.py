import pytest
from fastapi import HTTPException

from app.api.auth import verify_api_key
from app.config import settings


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
