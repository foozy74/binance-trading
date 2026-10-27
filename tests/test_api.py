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


class TestStatusEndpoint:
    def test_status_endpoint(self, client):
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "dry_run" in data
        assert "active_strategy" in data
    
    def test_status_running(self, client):
        response = client.get("/api/status")
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
