from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.database import get_db
from app.db.repository import TradeRepository, SignalRepository, ConfigRepository
from app.db.models import Trade, Signal
from app.api.auth import authenticate, require_auth
from app.bot.runtime_config import ConfigUpdate, apply_config
from app.config import settings
from app.services.exchange import create_exchange, symbol_assets

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint for Coolify monitoring"""
    return {"status": "healthy", "dry_run": settings.DRY_RUN}


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


@router.post("/api/auth/login")
async def login(credentials: LoginRequest, request: Request):
    """Dashboard-Login: liefert ein JWT für den Authorization-Header"""
    client = request.client.host if request.client else "unknown"
    token = authenticate(credentials.username, credentials.password, client)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/api/status")
async def get_status(db: Session = Depends(get_db), user: str = Depends(require_auth)):
    """Get current bot status"""
    from app.api.metrics import bot_uptime_seconds, bot_last_signal_age
    import time
    
    signal_repo = SignalRepository(db)
    latest_signal = signal_repo.get_latest()
    
    last_signal_age = None
    if latest_signal:
        last_signal_age = (time.time() - latest_signal.created_at.timestamp())
    
    return {
        "status": "running",
        "dry_run": settings.DRY_RUN,
        "exchange": settings.EXCHANGE,
        "active_strategy": settings.ACTIVE_STRATEGY,
        "symbol": settings.SYMBOL,
        "uptime_seconds": bot_uptime_seconds._value.get() if hasattr(bot_uptime_seconds._value, 'get') else 0,
        "last_signal_age": last_signal_age,
        "last_signal": latest_signal.signal if latest_signal else None
    }


@router.get("/api/signals")
async def get_signals(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    user: str = Depends(require_auth)
):
    """Get historical signals"""
    repo = SignalRepository(db)
    signals = repo.get_all(limit=limit)
    return [
        {
            "id": s.id,
            "symbol": s.symbol,
            "signal": s.signal,
            "strategy": s.strategy,
            "confidence": s.confidence,
            "rsi": s.rsi,
            "created_at": s.created_at.isoformat()
        }
        for s in signals
    ]


@router.get("/api/trades")
async def get_trades(
    limit: int = Query(100, ge=1, le=1000),
    symbol: Optional[str] = None,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth)
):
    """Get historical trades"""
    repo = TradeRepository(db)
    if symbol:
        trades = repo.get_by_symbol(symbol, limit=limit)
    else:
        trades = repo.get_all(limit=limit)
    
    return [
        {
            "id": t.id,
            "symbol": t.symbol,
            "side": t.side,
            "amount": t.amount,
            "price": t.price,
            "usdt_value": t.usdt_value,
            "stop_loss": t.stop_loss,
            "take_profit": t.take_profit,
            "is_dry_run": t.is_dry_run,
            "status": t.status,
            "created_at": t.created_at.isoformat()
        }
        for t in trades
    ]


@router.get("/api/portfolio")
async def get_portfolio(db: Session = Depends(get_db), user: str = Depends(require_auth)):
    """Get current portfolio value and P&L"""
    try:
        exchange = create_exchange()
        base, quote = symbol_assets(settings.SYMBOL)

        # Feldnamen btc_/usdt_ bleiben fürs Frontend; Werte sind Base/Quote von SYMBOL
        balance = exchange.fetch_balance()
        btc_balance = balance['total'].get(base, 0)
        usdt_balance = balance['total'].get(quote, 0)
        
        ticker = exchange.fetch_ticker(settings.SYMBOL)
        btc_price = ticker['last']
        
        total_value = (btc_balance * btc_price) + usdt_balance
        
        trade_repo = TradeRepository(db)
        pnl = trade_repo.get_total_pnl()
        
        return {
            "btc_balance": btc_balance,
            "usdt_balance": usdt_balance,
            "btc_price": btc_price,
            "total_value_usdt": total_value,
            "total_pnl_usdt": pnl
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch portfolio: {str(e)}")


@router.get("/api/config")
async def get_config(db: Session = Depends(get_db), user: str = Depends(require_auth)):
    """Get current bot configuration"""
    config_repo = ConfigRepository(db)
    db_config = config_repo.get_all()
    
    return {
        "dry_run": settings.DRY_RUN,
        "active_strategy": settings.ACTIVE_STRATEGY,
        "symbol": settings.SYMBOL,
        "trade_percentage": settings.TRADE_PERCENTAGE,
        "trailing_stop_percent": settings.TRAILING_STOP_PERCENT,
        "take_profit_percent": settings.TAKE_PROFIT_PERCENT,
        "stop_atr_multiple": settings.STOP_ATR_MULTIPLE,
        "take_profit_r": settings.TAKE_PROFIT_R,
        "db_overrides": db_config
    }


@router.put("/api/config")
async def update_config(
    update: ConfigUpdate,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth)
):
    """Bot-Konfiguration ändern; wirkt ab dem nächsten Bot-Durchlauf und überlebt Neustarts"""
    config_repo = ConfigRepository(db)
    # Erst speichern, dann übernehmen: schlägt das Speichern fehl, bleibt der laufende Stand unverändert
    for key, value in update.model_dump(exclude_none=True).items():
        config_repo.set(key, str(value))
    updated = apply_config(update)
    return {"updated": updated, "message": "Config updated"}
