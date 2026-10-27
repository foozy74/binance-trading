from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.sql import func
from app.db.database import Base


class Trade(Base):
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    side = Column(String)  # "buy" or "sell"
    amount = Column(Float)
    price = Column(Float)
    usdt_value = Column(Float)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    is_dry_run = Column(Boolean, default=False)
    status = Column(String, default="executed")  # executed, cancelled, failed
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Signal(Base):
    __tablename__ = "signals"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    signal = Column(String)  # BUY, SELL, HOLD
    strategy = Column(String)
    confidence = Column(Float, nullable=True)
    rsi = Column(Float, nullable=True)
    macd = Column(Float, nullable=True)
    obv = Column(Float, nullable=True)
    vwap = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class BotConfig(Base):
    __tablename__ = "bot_config"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)
    value = Column(String)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
