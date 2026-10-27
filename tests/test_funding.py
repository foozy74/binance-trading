import math

import pandas as pd
import pytest

from app.bot.funding import (
    NEUTRAL_FUNDING_APR, apply_funding_filter, derive_funding, funding_signals, funding_values,
)

HOUR_MS = 3_600_000


def test_derive_funding_neutral_rate_is_zero():
    assert derive_funding([NEUTRAL_FUNDING_APR / (24 * 365)] * 24) == pytest.approx(0)


def test_derive_funding_crowded_longs_is_risk_off():
    # 0.01 %/h ≈ 87.6 % APR -> stark negativ
    assert derive_funding([0.0001] * 24) == pytest.approx(-math.tanh((0.876 - NEUTRAL_FUNDING_APR) / 0.3))


def test_derive_funding_empty_is_zero():
    assert derive_funding([]) == 0


def test_funding_values_use_only_past_rates():
    t0 = 1_774_792_800_000  # realistischer Zeitpunkt, deckt Einheitenfehler (ns/us/ms) auf
    candles = pd.DataFrame({"timestamp": pd.to_datetime([t0, t0 + HOUR_MS, t0 + 2 * HOUR_MS], unit="ms")})
    # Rate zur Schlusszeit von Kerze 0 ist bekannt, Rate bei +4h ist Zukunft für alle Kerzen
    rates = pd.DataFrame({"timestamp": [t0 + HOUR_MS, t0 + 4 * HOUR_MS], "rate": [0.0001, -0.0001]})
    values = funding_values(candles, rates, window=24)
    assert values[0] == pytest.approx(derive_funding([0.0001]))
    assert values[2] == pytest.approx(derive_funding([0.0001]))


def test_filter_blocks_buy_into_crowded_longs_and_sell_into_crowded_shorts():
    candles = pd.DataFrame({"funding": [-0.5, 0.5, -0.5, 0.5]})
    signals = ["BUY", "SELL", "SELL", "BUY"]
    assert apply_funding_filter(candles, signals, 0.3) == ["HOLD", "HOLD", "SELL", "BUY"]
    assert apply_funding_filter(candles, signals, None) == signals


def test_funding_signals_are_contrarian():
    candles = pd.DataFrame({"funding": [0.5, -0.5, 0.1]})
    assert funding_signals(candles, 0.3) == ["BUY", "SELL", "HOLD"]
