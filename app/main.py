from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import threading
import time

from app.config import settings
from app.db.database import init_db, get_db, SessionLocal
from app.api.routes import router
from app.api.backtest_route import router as backtest_router
from app.api.metrics import get_metrics
from app.bot.trader import TradingBot
from app.bot.runtime_config import load_saved_config


trading_bot = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global trading_bot
    
    # Startup
    init_db()
    db = SessionLocal()
    try:
        load_saved_config(db)
    finally:
        db.close()
    trading_bot = TradingBot()
    trading_thread = threading.Thread(target=trading_bot.run, daemon=True)
    trading_thread.start()
    
    yield
    
    # Shutdown
    if trading_bot:
        trading_bot.stop()


app = FastAPI(
    title="Binance Trading Bot",
    description="Trading bot with multiple strategies and REST API",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(backtest_router)


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return get_metrics()


@app.get("/")
async def root():
    """Root endpoint with API info"""
    return {
        "name": "Binance Trading Bot",
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "status": "/api/status",
            "signals": "/api/signals",
            "trades": "/api/trades",
            "portfolio": "/api/portfolio",
            "config": "/api/config"
        }
    }
