from sqlalchemy.orm import Session
from app.db.models import Trade, Signal, BotConfig
from datetime import datetime
from typing import List, Optional, Dict


class TradeRepository:
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, trade_data: dict) -> Trade:
        trade = Trade(**trade_data)
        self.db.add(trade)
        self.db.commit()
        self.db.refresh(trade)
        return trade
    
    def get_all(self, limit: int = 100) -> List[Trade]:
        return self.db.query(Trade).order_by(Trade.created_at.desc()).limit(limit).all()
    
    def get_by_symbol(self, symbol: str, limit: int = 50) -> List[Trade]:
        return self.db.query(Trade).filter(Trade.symbol == symbol).order_by(Trade.created_at.desc()).limit(limit).all()
    
    def get_total_pnl(self) -> float:
        trades = self.db.query(Trade).all()
        buys = [t for t in trades if t.side == "buy"]
        sells = [t for t in trades if t.side == "sell"]
        
        total_bought = sum(t.usdt_value for t in buys)
        total_sold = sum(t.usdt_value for t in sells)
        
        return total_sold - total_bought


class SignalRepository:
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, signal_data: dict) -> Signal:
        signal = Signal(**signal_data)
        self.db.add(signal)
        self.db.commit()
        self.db.refresh(signal)
        return signal
    
    def get_all(self, limit: int = 100) -> List[Signal]:
        return self.db.query(Signal).order_by(Signal.created_at.desc()).limit(limit).all()
    
    def get_latest(self) -> Optional[Signal]:
        return self.db.query(Signal).order_by(Signal.created_at.desc()).first()


class ConfigRepository:
    def __init__(self, db: Session):
        self.db = db
    
    def get(self, key: str) -> Optional[str]:
        config = self.db.query(BotConfig).filter(BotConfig.key == key).first()
        return config.value if config else None
    
    def set(self, key: str, value: str) -> BotConfig:
        config = self.db.query(BotConfig).filter(BotConfig.key == key).first()
        if config:
            config.value = value
            config.updated_at = datetime.now()
        else:
            config = BotConfig(key=key, value=value)
            self.db.add(config)
        self.db.commit()
        self.db.refresh(config)
        return config
    
    def get_all(self) -> Dict[str, str]:
        configs = self.db.query(BotConfig).all()
        return {c.key: c.value for c in configs}
