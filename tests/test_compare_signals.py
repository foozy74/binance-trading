from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from app.bot.backtest import WINDOW
from app.bot.compare_signals import compare, evaluated_candle, replay_signal


@pytest.fixture
def candles():
    """150 Stundenkerzen als Random Walk, ab 2026-01-01 00:00 UTC."""
    rng = np.random.default_rng(7)
    close = 40000 * np.exp(np.cumsum(rng.normal(0, 0.01, 150)))
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=150, freq="h"),
        "open": np.r_[close[0], close[:-1]],
        "high": close * 1.005,
        "low": close * 0.995,
        "close": close,
        "volume": rng.uniform(100, 1000, 150),
    })


def _row(created_at, signal, strategy="obv_vwap", rsi=None):
    return SimpleNamespace(created_at=created_at, signal=signal, strategy=strategy, rsi=rsi)


@pytest.mark.parametrize("created_at,expected", [
    (datetime(2026, 1, 5, 12, 0, 30), "2026-01-05 11:00"),
    (datetime(2026, 1, 5, 12, 59, 59), "2026-01-05 11:00"),
    (datetime(2026, 1, 5, 12, 0, 30, tzinfo=timezone.utc), "2026-01-05 11:00"),
])
def test_evaluated_candle_is_last_closed_hour(created_at, expected):
    assert evaluated_candle(created_at) == pd.Timestamp(expected)


def test_replay_needs_full_window(candles):
    assert replay_signal(candles, candles["timestamp"].iloc[WINDOW - 2], "obv_vwap", 0) is None
    assert replay_signal(candles, pd.Timestamp("2030-01-01"), "obv_vwap", 0) is None
    assert replay_signal(candles, candles["timestamp"].iloc[WINDOW - 1], "obv_vwap", 0) is not None


def test_compare_flags_match_and_mismatch(candles):
    t = 120
    signal, rsi = replay_signal(candles, candles["timestamp"].iloc[t], "rsi_divergence", 0)
    other = "BUY" if signal != "BUY" else "SELL"
    created = (candles["timestamp"].iloc[t] + pd.Timedelta(hours=1, minutes=1)).to_pydatetime()

    results = compare([_row(created, signal, "rsi_divergence", rsi), _row(created, other, "rsi_divergence")],
                      candles, volume_filter=0)

    assert [r["status"] for r in results] == ["match", "mismatch"]
    assert results[0]["backtest"] == signal and results[0]["rsi_diff"] == pytest.approx(0)
    assert results[1]["rsi_diff"] is None


def test_compare_skips_missing_candles_and_unknown_strategy(candles):
    early = (candles["timestamp"].iloc[10] + pd.Timedelta(hours=1)).to_pydatetime()
    late = (candles["timestamp"].iloc[120] + pd.Timedelta(hours=1)).to_pydatetime()

    results = compare([_row(early, "HOLD"), _row(late, "HOLD", strategy="alt")], candles, volume_filter=0)

    assert [r["status"] for r in results] == ["no_candles", "unknown_strategy"]


def test_volume_filter_turns_signal_into_hold(candles):
    t = next(i for i in range(WINDOW - 1, len(candles))
             if replay_signal(candles, candles["timestamp"].iloc[i], "macd_crossover", 0)[0] != "HOLD")
    # Faktor so hoch, dass jedes Volumen darunter liegt
    assert replay_signal(candles, candles["timestamp"].iloc[t], "macd_crossover", 100)[0] == "HOLD"
