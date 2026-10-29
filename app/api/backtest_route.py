"""Backtest aus dem Dashboard: gleiche Rechnung wie `python -m app.bot.backtest`, Kerzen von Hyperliquid."""
import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth import require_auth
from app.bot.backtest import WINDOW, buy_and_hold, fetch_candles, generate_signals, simulate
from app.bot.strategies import STRATEGIES
from app.config import settings

router = APIRouter()
MAX_CANDLES = 5000  # mehr liefert Hyperliquid pro Abruf nicht; begrenzt auch die Rechenzeit
# Nur ein Lauf gleichzeitig, damit parallele Starts den Bot-Thread nicht ausbremsen
_RUNNING = threading.Lock()


class BacktestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: Optional[str] = None  # None = alle Strategien
    candles: int = Field(default=2000, ge=WINDOW + 100, le=MAX_CANDLES)
    stop_loss: Optional[float] = Field(default=None, gt=0, lt=1)
    take_profit: Optional[float] = Field(default=None, gt=0, lt=1)

    @field_validator("strategy")
    @classmethod
    def _known_strategy(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in STRATEGIES:
            raise ValueError(f"Unbekannte Strategie, erlaubt: {list(STRATEGIES)}")
        return value


@router.post("/api/backtest")
def run_backtest(params: BacktestRequest, user: str = Depends(require_auth)):
    """Sync-Route: läuft im Threadpool, blockiert also nicht den Event-Loop"""
    if not _RUNNING.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Es läuft bereits ein Backtest")
    try:
        try:
            candles = fetch_candles(settings.SYMBOL, "1h", params.candles)
        except Exception as e:
            print(f"❌ Backtest: Kerzen konnten nicht geladen werden: {type(e).__name__}")
            detail = f"Kerzen für {settings.SYMBOL} konnten nicht von Hyperliquid geladen werden"
            raise HTTPException(status_code=502, detail=detail)
        names = [params.strategy] if params.strategy else list(STRATEGIES)
        results = []
        for name, signals in generate_signals(candles, names).items():
            r = simulate(candles, signals, stop_loss=params.stop_loss, take_profit=params.take_profit)
            results.append({"strategy": name, "total_return": r["total_return"], "max_drawdown": r["max_drawdown"],
                            "trades": r["trades"], "win_rate": r["wins"] / r["trades"] if r["trades"] else 0})
        return {"symbol": settings.SYMBOL, "candles": len(candles),
                # Kerzen sind naive UTC; mit Offset, sonst liest der Browser sie als Ortszeit
                "start": candles["timestamp"].iloc[0].tz_localize("UTC").isoformat(),
                "end": candles["timestamp"].iloc[-1].tz_localize("UTC").isoformat(),
                "buy_hold": buy_and_hold(candles), "results": results}
    finally:
        _RUNNING.release()
