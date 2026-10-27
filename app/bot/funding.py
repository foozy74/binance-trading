"""
Hyperliquid-Funding als konträres Positionierungssignal (portiert aus AutoFund-AI lib/fundingSignal.ts).

Hyperliquid berechnet auch im ausgeglichenen Markt einen Basiszins von 0,00125 %/h (≈ 11 % p.a.),
"neutral" ist also dieser Satz, nicht null. Funding deutlich darüber = Longs zahlen viel,
Markt überfüllt -> negativer Wert (risk-off); negatives Funding -> positiver Wert (risk-on).
Die Richtung ist eine Hypothese – nur der Walk-Forward entscheidet, ob sie trägt.
"""
import math
from typing import List, Optional, Sequence

import ccxt
import pandas as pd

HOURS_PER_YEAR = 24 * 365
NEUTRAL_FUNDING_APR = 0.0000125 * HOURS_PER_YEAR
SATURATION_APR = 0.3  # Überschuss-APR, bei dem das Signal ~±0.76 erreicht (tanh(1))
PAGE_SIZE = 500  # Hyperliquid liefert max. 500 Funding-Einträge pro Abruf


def derive_funding(hourly_rates: Sequence[float]) -> float:
    """Signalwert in [-1, 1] aus stündlichen Funding-Raten"""
    if len(hourly_rates) == 0:
        return 0.0
    apr = sum(hourly_rates) / len(hourly_rates) * HOURS_PER_YEAR
    return max(-1.0, min(1.0, -math.tanh((apr - NEUTRAL_FUNDING_APR) / SATURATION_APR)))


def fetch_funding_history(symbol: str, since_ms: int, until_ms: int) -> pd.DataFrame:
    """Stündliche Funding-Raten von Hyperliquid (öffentlich), älteste zuerst"""
    exchange = ccxt.hyperliquid({'enableRateLimit': True})
    rows, cursor = [], since_ms
    while cursor <= until_ms:
        page = exchange.fetch_funding_rate_history(symbol, since=cursor, limit=PAGE_SIZE)
        rows += [(r['timestamp'], r['fundingRate']) for r in page]
        if len(page) < PAGE_SIZE:
            break
        cursor = page[-1]['timestamp'] + 1
    return pd.DataFrame(rows, columns=['timestamp', 'rate'])


def funding_values(candles: pd.DataFrame, rates: pd.DataFrame, window: int = 24) -> List[float]:
    """Signalwert je Kerze aus den letzten window Raten bis zur Schlusszeit der Kerze (kein Blick in die Zukunft)"""
    close_ms = (candles['timestamp'].astype('datetime64[ms]').astype('int64') + 3_600_000).tolist()
    times, values = rates['timestamp'].tolist(), rates['rate'].tolist()
    result, end = [], 0
    for close in close_ms:
        while end < len(times) and times[end] <= close:
            end += 1
        result.append(derive_funding(values[max(0, end - window):end]))
    return result


def apply_funding_filter(candles: pd.DataFrame, signals: List[str], threshold: Optional[float]) -> List[str]:
    """Kein BUY in überfüllte Longs (Wert < -threshold), kein SELL in überfüllte Shorts (Wert > threshold)"""
    if threshold is None:
        return list(signals)
    funding = candles['funding'].tolist()
    return [
        "HOLD" if (s == "BUY" and funding[i] < -threshold) or (s == "SELL" and funding[i] > threshold) else s
        for i, s in enumerate(signals)
    ]


def funding_signals(candles: pd.DataFrame, threshold: float) -> List[str]:
    """Eigenständige Strategie: konträr zur Positionierung handeln"""
    return ["BUY" if f > threshold else "SELL" if f < -threshold else "HOLD" for f in candles['funding']]
