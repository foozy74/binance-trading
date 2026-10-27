"""
Backtest der Strategien auf historischen Kerzen.

Bildet den Live-Bot nach: Signal beim Schluss von Kerze t (Indikatoren über die letzten
WINDOW abgeschlossenen Kerzen), Ausführung zum Open von Kerze t+1, Perps-Logik wie
adjust_for_position (gleiche Richtung -> nichts, Gegensignal -> drehen). Kein SL/TP,
optional SL/TP über High/Low der Kerze (--stop-loss/--take-profit).

Aufruf: python -m app.bot.backtest --symbol BTC/USDC:USDC --candles 5000
"""
import argparse
from typing import Dict, List, Optional

import ccxt
import pandas as pd

from app.config import settings
from app.bot.stops import AtrStop, StopLoss, trade_stops  # noqa: F401 (AtrStop re-exportiert)
from app.bot.indicators import calculate_all_indicators
from app.bot.strategies import STRATEGIES

WINDOW = 100  # wie fetch_market_data im Live-Bot
TAKER_FEE = 0.00045  # Hyperliquid Taker-Gebühr (Basisstufe)
DIRECTION = {"BUY": 1, "SELL": -1}


def fetch_candles(symbol: str, timeframe: str, count: int) -> pd.DataFrame:
    """Lädt historische Kerzen von Hyperliquid (öffentlich, keine Keys nötig)"""
    exchange = ccxt.hyperliquid({'enableRateLimit': True})
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=count + 1)
    # Letzte Kerze ist noch offen
    df = pd.DataFrame(ohlcv[:-1], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df


def generate_signals(candles: pd.DataFrame, names: List[str]) -> Dict[str, List[str]]:
    """Signal je Kerze und Strategie, berechnet wie live auf dem rollenden Fenster"""
    strategies = {name: STRATEGIES[name]() for name in names}
    signals = {name: ["HOLD"] * len(candles) for name in names}
    for t in range(WINDOW - 1, len(candles)):
        window = calculate_all_indicators(candles.iloc[t - WINDOW + 1:t + 1].reset_index(drop=True))
        for name, strategy in strategies.items():
            signals[name][t] = strategy.generate_signal(window)[0]
    return signals


def stop_exit_price(bar: Dict, position: int, entry: float,
                    stop_loss: Optional[float], take_profit: Optional[float]) -> Optional[float]:
    """Ausstiegspreis falls SL/TP in dieser Kerze greift; beide getroffen -> SL (konservativ), Gap -> Open"""
    worst, best = (bar['low'], bar['high']) if position > 0 else (bar['high'], bar['low'])
    if stop_loss is not None:
        level = entry * (1 - position * stop_loss)
        if position * (worst - level) <= 0:
            return min(bar['open'], level) if position > 0 else max(bar['open'], level)
    if take_profit is not None:
        level = entry * (1 + position * take_profit)
        if position * (best - level) >= 0:
            return max(bar['open'], level) if position > 0 else min(bar['open'], level)
    return None


def simulate(candles: pd.DataFrame, signals: List[str], fee: float = TAKER_FEE,
             stop_loss: StopLoss = None, take_profit: Optional[float] = None) -> Dict:
    """Simuliert 1x-Position (volles Kapital) mit optionalem SL/TP (fest in % oder AtrStop) und liefert Kennzahlen"""
    equity, position, entry = 1.0, 0, 0.0
    sl, tp = None, None
    trade_returns: List[float] = []
    peak, max_dd = 1.0, 0.0

    def close(price: float) -> None:
        nonlocal equity, position
        trade_returns.append(position * (price / entry - 1))
        equity *= (1 + trade_returns[-1]) * (1 - fee)
        position = 0

    bars = candles.to_dict('records')  # deutlich schneller als iloc je Kerze
    for t, bar in enumerate(bars):
        if t > 0 and DIRECTION.get(signals[t - 1], position) != position:
            if position:
                close(bar['open'])
            position, entry = DIRECTION[signals[t - 1]], bar['open']
            sl, tp = trade_stops(stop_loss, take_profit, bars[t - 1], entry)
            equity *= 1 - fee
        if position and (sl or tp):
            exit_price = stop_exit_price(bar, position, entry, sl, tp)
            if exit_price is not None:
                close(exit_price)
        marked = equity * (1 + position * (bar['close'] / entry - 1)) if position else equity
        peak = max(peak, marked)
        max_dd = min(max_dd, marked / peak - 1)
    if position:
        close(bars[-1]['close'])
    return {
        "trades": len(trade_returns),
        "wins": sum(r > 0 for r in trade_returns),
        "total_return": equity - 1,
        "max_drawdown": max_dd,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest aller Strategien auf Hyperliquid-Kerzen")
    parser.add_argument("--symbol", default="BTC/USDC:USDC")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--candles", type=int, default=5000)
    parser.add_argument("--fee", type=float, default=TAKER_FEE)
    parser.add_argument("--stop-loss", type=float, default=settings.TRAILING_STOP_PERCENT, help="z.B. 0.02 = 2 %%")
    parser.add_argument("--take-profit", type=float, default=settings.TAKE_PROFIT_PERCENT, help="z.B. 0.05 = 5 %%")
    args = parser.parse_args()

    candles = fetch_candles(args.symbol, args.timeframe, args.candles)
    print(f"📈 {len(candles)} Kerzen {args.symbol} {args.timeframe}: "
          f"{candles['timestamp'].iloc[0]} – {candles['timestamp'].iloc[-1]}")
    hold = candles['close'].iloc[-1] / candles['open'].iloc[WINDOW] - 1
    print(f"📌 Buy & Hold: {hold:+.2%}")
    variants = {
        "ohne SL/TP": (None, None),
        f"SL {args.stop_loss:.1%} / TP {args.take_profit:.1%}": (args.stop_loss, args.take_profit),
    }
    for name, signals in generate_signals(candles, list(STRATEGIES)).items():
        for label, (stop_loss, take_profit) in variants.items():
            r = simulate(candles, signals, args.fee, stop_loss, take_profit)
            win_rate = r["wins"] / r["trades"] if r["trades"] else 0
            print(f"{name:16} {label:18} Rendite {r['total_return']:+8.2%}  Max-DD {r['max_drawdown']:8.2%}  "
                  f"Trades {r['trades']:4}  Trefferquote {win_rate:.0%}")


if __name__ == "__main__":
    main()
