"""
Abgleich: vom Live-Bot gespeicherte Signale gegen den Backtest für dieselben Kerzen.

Für jedes Signal aus der DB wird die Kerze bestimmt, die der Bot ausgewertet hat, und das
Signal mit derselben Strategie auf denselben WINDOW Kerzen nachgerechnet (wie generate_signals).
Abweichungen heißen: Backtest-Ergebnisse bilden den Live-Bot nicht ab (Timing, Datenlücken, Bug).
Der gespeicherte RSI dient als Kontrolle, ob die Kerzen-Zuordnung stimmt.

Aufruf auf dem Server im Bot-Container (nutzt DATABASE_URL und SYMBOL):
    python -m app.bot.compare_signals --limit 500
"""
import argparse
import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from app.bot.backtest import WINDOW, fetch_candles
from app.bot.indicators import calculate_all_indicators
from app.bot.signals import volume_ratio
from app.bot.strategies import STRATEGIES
from app.config import settings
from app.db.database import SessionLocal
from app.db.repository import SignalRepository

MAX_CANDLES = 5000  # mehr liefert Hyperliquid pro Abruf nicht
RSI_TOLERANCE = 0.01


def evaluated_candle(created_at: datetime) -> pd.Timestamp:
    """Open-Zeit der Kerze, die der Bot zu created_at ausgewertet hat: die zuletzt abgeschlossene 1h-Kerze.

    shortcut: Die DB speichert keine Kerzenzeit, nur created_at; wird ein Signal in den ersten Sekunden
    nach Stundenwechsel gespeichert, bevor die Börse die neue Kerze liefert, ist die Zuordnung eine Stunde
    daneben (RSI-Abweichung zeigt das). Upgrade: Kerzenzeit in der Signal-Tabelle mitspeichern.
    """
    ts = pd.Timestamp(created_at)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)  # Kerzen sind naive UTC
    return ts.floor("h") - pd.Timedelta(hours=1)


def replay_signal(candles: pd.DataFrame, candle_ts: pd.Timestamp, strategy: str,
                  volume_filter: float) -> Optional[Tuple[str, float]]:
    """Signal und RSI wie live auf den WINDOW Kerzen bis candle_ts; None wenn Kerzen fehlen."""
    positions = candles.index[candles["timestamp"] == candle_ts]
    if len(positions) == 0 or positions[0] < WINDOW - 1:
        return None
    t = positions[0]
    window = calculate_all_indicators(candles.iloc[t - WINDOW + 1:t + 1].reset_index(drop=True))
    signal = STRATEGIES[strategy]().generate_signal(window)[0]
    if signal != "HOLD" and volume_filter and volume_ratio(window).iloc[-1] < volume_filter:
        signal = "HOLD"
    return signal, float(window["RSI"].iloc[-1])


def compare(rows: List, candles: pd.DataFrame, volume_filter: float) -> List[Dict]:
    """Je gespeichertem Signal: Kerze, Live- vs. Backtest-Signal, RSI-Abweichung und Status."""
    results = []
    for row in rows:
        candle_ts = evaluated_candle(row.created_at)
        result = {"created_at": row.created_at, "candle": candle_ts, "strategy": row.strategy,
                  "live": row.signal, "backtest": None, "rsi_diff": None}
        replay = replay_signal(candles, candle_ts, row.strategy, volume_filter) if row.strategy in STRATEGIES else None
        if replay is None:
            result["status"] = "unknown_strategy" if row.strategy not in STRATEGIES else "no_candles"
        else:
            result["backtest"], rsi = replay
            if row.rsi is not None and not math.isnan(row.rsi):
                result["rsi_diff"] = rsi - row.rsi
            result["status"] = "match" if row.signal == result["backtest"] else "mismatch"
        results.append(result)
    return results


def print_report(results: List[Dict]) -> None:
    """Abweichungen einzeln, danach Zusammenfassung."""
    for r in results:
        rsi_off = r["rsi_diff"] is not None and abs(r["rsi_diff"]) > RSI_TOLERANCE
        if r["status"] == "mismatch" or rsi_off:
            rsi = f"RSI-Diff {r['rsi_diff']:+.2f}" if r["rsi_diff"] is not None else "RSI -"
            print(f"❌ {r['candle']:%Y-%m-%d %H:%M} {r['strategy']:15} live {r['live']:4} "
                  f"backtest {r['backtest'] or '-':4} {rsi}")
    statuses = ("match", "mismatch", "no_candles", "unknown_strategy")
    counts = {s: sum(r["status"] == s for r in results) for s in statuses}
    compared = counts["match"] + counts["mismatch"]
    rate = counts["match"] / compared if compared else 0
    rsi_off = sum(r["rsi_diff"] is not None and abs(r["rsi_diff"]) > RSI_TOLERANCE for r in results)
    print(f"📊 {compared} verglichen: {counts['match']} gleich ({rate:.0%}), {counts['mismatch']} abweichend, "
          f"{rsi_off} mit RSI-Abweichung > {RSI_TOLERANCE}")
    if counts["no_candles"] or counts["unknown_strategy"]:
        print(f"⚠️ Übersprungen: {counts['no_candles']} ohne Kerzen, "
              f"{counts['unknown_strategy']} unbekannte Strategie")


def main() -> None:
    parser = argparse.ArgumentParser(description="Live-Signale aus der DB gegen den Backtest abgleichen")
    parser.add_argument("--symbol", default=settings.SYMBOL)
    parser.add_argument("--limit", type=int, default=500, help="Anzahl der jüngsten Signale")
    parser.add_argument("--volume-filter", type=float, default=settings.VOLUME_FILTER)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = [r for r in reversed(SignalRepository(db).get_all(limit=args.limit)) if r.symbol == args.symbol]
    finally:
        db.close()
    if not rows:
        print(f"⚠️ Keine gespeicherten Signale für {args.symbol}")
        return

    hours = (pd.Timestamp.now("UTC").tz_localize(None) - evaluated_candle(rows[0].created_at)) / pd.Timedelta(hours=1)
    count = min(math.ceil(hours) + WINDOW + 2, MAX_CANDLES)
    candles = fetch_candles(args.symbol, "1h", count)
    print(f"📈 {len(rows)} Signale ab {rows[0].created_at:%Y-%m-%d %H:%M}, {len(candles)} Kerzen {args.symbol}")
    print_report(compare(rows, candles, args.volume_filter))


if __name__ == "__main__":
    main()
