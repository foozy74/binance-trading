import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.database import Base, get_db
from app.db.models import Trade, Signal
from app.main import app
import time
from unittest.mock import MagicMock

from app.bot.trader import TradingBot


SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def bot_start(monkeypatch):
    """Bot-Loop in Tests nie starten: er würde Kerzen von der Börse holen und in data/trading.db schreiben"""
    start = MagicMock()
    monkeypatch.setattr(TradingBot, "start", start)
    return start


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database for each test"""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    """Create test client with database override"""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    from httpx import Client
    with Client(app=app, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
