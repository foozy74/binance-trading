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


class TestBacktestEndpoint:
    @pytest.fixture
    def candles(self, monkeypatch):
        """300 Stundenkerzen als Random Walk statt Hyperliquid-Abruf."""
        import numpy as np
        import pandas as pd
        from app.api import backtest_route
        rng = np.random.default_rng(3)
        close = 40000 * np.exp(np.cumsum(rng.normal(0, 0.01, 300)))
        df = pd.DataFrame({
            "timestamp": pd.date_range("2026-01-01", periods=300, freq="h"),
            "open": np.r_[close[0], close[:-1]], "high": close * 1.005, "low": close * 0.995,
            "close": close, "volume": rng.uniform(100, 1000, 300),
        })
        calls = []
        monkeypatch.setattr(backtest_route, "fetch_candles", lambda s, tf, n: calls.append(n) or df)
        return calls

    def test_requires_auth(self, client):
        assert client.post("/api/backtest", json={}).status_code == 401

    def test_single_strategy(self, client, auth_headers, candles):
        response = client.post("/api/backtest", json={"strategy": "macd_crossover", "candles": 300,
                                                      "stop_loss": 0.02, "take_profit": 0.05}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert candles == [300]
        assert [r["strategy"] for r in data["results"]] == ["macd_crossover"]
        assert {"total_return", "max_drawdown", "trades", "win_rate"} <= set(data["results"][0])
        assert "buy_hold" in data and data["candles"] == 300

    def test_all_strategies_by_default(self, client, auth_headers, candles):
        from app.bot.strategies import STRATEGIES
        data = client.post("/api/backtest", json={"candles": 300}, headers=auth_headers).json()
        assert [r["strategy"] for r in data["results"]] == list(STRATEGIES)

    @pytest.mark.parametrize("body", [{"candles": 5001}, {"candles": 100}, {"strategy": "gibt_es_nicht"},
                                      {"stop_loss": 1.5}, {"take_profit": -0.1}, {"unbekannt": 1}])
    def test_invalid_input_rejected(self, client, auth_headers, body):
        assert client.post("/api/backtest", json=body, headers=auth_headers).status_code == 422

    def test_only_one_backtest_at_a_time(self, client, auth_headers, candles):
        from app.api import backtest_route
        backtest_route._RUNNING.acquire()
        try:
            response = client.post("/api/backtest", json={"candles": 300}, headers=auth_headers)
        finally:
            backtest_route._RUNNING.release()
        assert response.status_code == 409

    def test_fetch_error_returns_502(self, client, auth_headers, monkeypatch):
        from app.api import backtest_route

        def fail(*args):
            raise RuntimeError("Netzwerk weg")
        monkeypatch.setattr(backtest_route, "fetch_candles", fail)
        response = client.post("/api/backtest", json={"candles": 300}, headers=auth_headers)
        assert response.status_code == 502
        assert not backtest_route._RUNNING.locked()
