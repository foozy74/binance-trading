import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import Base, get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


SQLALCHEMY_DATABASE_URL = "sqlite:///./test_api.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestHealthEndpoint:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "dry_run" in data
    
    def test_health_dry_run_mode(self, client):
        response = client.get("/health")
        data = response.json()
        assert data["dry_run"] in [True, False]


@pytest.fixture
def auth_headers(client, monkeypatch):
    from app.api import auth
    from app.config import settings
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "sehr-geheimes-pw")
    auth._FAILED_LOGINS.clear()
    response = client.post("/api/auth/login", json={"username": "admin", "password": "sehr-geheimes-pw"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


class TestLoginEndpoint:
    def test_login_wrong_password(self, client, auth_headers):
        response = client.post("/api/auth/login", json={"username": "admin", "password": "falsch"})
        assert response.status_code == 401

    def test_login_rejects_invalid_body(self, client):
        response = client.post("/api/auth/login", json={"username": "admin"})
        assert response.status_code == 422

    def test_token_grants_access(self, client, auth_headers):
        response = client.get("/api/signals", headers=auth_headers)
        assert response.status_code == 200


class TestStatusEndpoint:
    def test_status_requires_auth(self, client):
        response = client.get("/api/status")
        assert response.status_code == 401

    def test_status_endpoint(self, client, auth_headers):
        response = client.get("/api/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "dry_run" in data
        assert "active_strategy" in data
    
    def test_status_running(self, client, auth_headers):
        response = client.get("/api/status", headers=auth_headers)
        data = response.json()
        assert data["status"] == "running"


class TestMetricsEndpoint:
    def test_metrics_prometheus_format(self, client):
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "bot_trades_total" in response.text or "bot_signals_total" in response.text


class TestRootEndpoint:
    def test_root_endpoint(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Binance Trading Bot"
        assert "version" in data
        assert "endpoints" in data


class TestProtectedEndpoints:
    def test_signals_requires_api_key(self, client):
        response = client.get("/api/signals")
        assert response.status_code == 401
    
    def test_trades_requires_api_key(self, client):
        response = client.get("/api/trades")
        assert response.status_code == 401
    
    def test_portfolio_requires_api_key(self, client):
        response = client.get("/api/portfolio")
        assert response.status_code == 401
    
    def test_config_requires_api_key(self, client):
        response = client.get("/api/config")
        assert response.status_code == 401


class TestConfigUpdate:
    @pytest.fixture(autouse=True)
    def restore_settings(self, monkeypatch):
        from app.config import settings
        for field in ("ACTIVE_STRATEGY", "TRADE_PERCENTAGE", "TRAILING_STOP_PERCENT", "TAKE_PROFIT_PERCENT"):
            monkeypatch.setattr(settings, field, getattr(settings, field))

    def test_strategy_change_visible_in_status_and_config(self, client, auth_headers):
        response = client.put("/api/config", json={"active_strategy": "macd_crossover"}, headers=auth_headers)
        assert response.status_code == 200
        assert client.get("/api/status", headers=auth_headers).json()["active_strategy"] == "macd_crossover"
        config = client.get("/api/config", headers=auth_headers).json()
        assert config["active_strategy"] == "macd_crossover"
        assert config["db_overrides"]["active_strategy"] == "macd_crossover"

    @pytest.mark.parametrize("body", [{"active_strategy": "gibt_es_nicht"}, {"trade_percentage": 5}])
    def test_invalid_value_rejected(self, client, auth_headers, body):
        response = client.put("/api/config", json=body, headers=auth_headers)
        assert response.status_code == 422
        assert client.get("/api/config", headers=auth_headers).json()["db_overrides"] == {}
