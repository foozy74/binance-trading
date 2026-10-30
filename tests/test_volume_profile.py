from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from app.bot.price_action import STOP_BUFFER
from app.bot.volume_profile import (
    BREAKOUT, POC_BOUNCE, VA_REVERSAL, Signal, build_signals, session_profile, simulate_signals, walk_forward_signals,
)

START = pd.Timestamp("2026-01-01")
# Vortag: dichter Kern 100,5–101,5, dünne Ränder 100–102, Schluss im Kern (innerhalb der VA)
DAY1 = [(101, 101.5, 100.5, 101, 10.0)] * 20 + [(101, 102, 100, 101, 1.0)] * 4


def _candles(bars, start=START):
    df = pd.DataFrame(bars, columns=["open", "high", "low", "close", "volume"])
    return df.assign(timestamp=pd.date_range(start, periods=len(bars), freq="h"))


def _mirror(bars):
    """Spiegelt den Kursverlauf an 100 – aus Long wird Short"""
    return [(200 - o, 200 - lo, 200 - h, 200 - c, v) for o, h, lo, c, v in bars]


def _flat(price, n):
    return [(price, price + 0.1, price - 0.1, price, 1.0)] * n


def _reversal_day(prof):
    """Schluss unter VAL, tieferes Tief, Schluss zurück in der VA (Signal bei Kerze 2), dann ruhig"""
    val = prof.val
    return [(val + 0.2, val + 0.3, val - 1.5, val - 1, 5.0), (val - 1, val - 0.5, val - 2, val - 0.5, 5.0),
            (val - 0.5, val + 0.4, val - 0.6, val + 0.2, 5.0)] + _flat(val + 0.2, 21)


def test_profile_value_area_holds_70_percent():
    day = _candles(DAY1)
    prof = session_profile(day, 0.001)
    assert 100.5 <= prof.poc <= 101.5
    assert prof.val <= prof.poc <= prof.vah
    assert 100.4 <= prof.val and prof.vah <= 101.6  # dünne Ränder liegen außerhalb


def test_profile_of_single_candle_spreads_volume_uniformly():
    prof = session_profile(_candles([(100, 110, 100, 105, 1.0)]), 0.01)
    assert prof.vah - prof.val == pytest.approx(7, abs=1.01)


def test_doji_volume_lands_in_its_price_bin():
    prof = session_profile(_candles([(100, 102, 100, 101, 1.0), (101.5, 101.5, 101.5, 101.5, 50.0)]), 0.001)
    assert prof.poc == pytest.approx(101.5, abs=0.11)


def test_va_reversal_long_after_close_back_inside():
    prof = session_profile(_candles(DAY1), 0.001)
    signals = build_signals(_candles(DAY1 + _reversal_day(prof)), 0.001, "va")
    hits = [(t, s) for t, s in enumerate(signals) if s]
    assert [t for t, _ in hits] == [26]
    s = hits[0][1]
    assert (s.setup, s.direction, s.target) == (VA_REVERSAL, 1, prof.vah)
    assert s.stop == pytest.approx((prof.val - 2) * (1 - STOP_BUFFER))


def test_va_reversal_short_mirrored():
    prof = session_profile(_candles(_mirror(DAY1)), 0.001)
    day2 = _mirror(_reversal_day(SimpleNamespace(val=200 - prof.vah)))
    s = build_signals(_candles(_mirror(DAY1) + day2), 0.001, "va")[26]
    assert (s.direction, s.target) == (-1, prof.val)
    assert s.stop > prof.vah


def test_rr_target():
    prof = session_profile(_candles(DAY1), 0.001)
    s = build_signals(_candles(DAY1 + _reversal_day(prof)), 0.001, 2.0)[26]
    entry = prof.val + 0.2
    assert s.target == pytest.approx(entry + 2 * (entry - s.stop))


def test_no_signal_when_previous_session_closed_outside_va():
    day1 = DAY1[:-1] + [(101, 103, 101, 102.8, 1.0)]
    prof = session_profile(_candles(day1), 0.001)
    assert not any(build_signals(_candles(day1 + _reversal_day(prof)), 0.001, "va"))


def test_cut_first_session_is_not_used_as_profile():
    prof = session_profile(_candles(DAY1), 0.001)
    candles = _candles(DAY1 + _reversal_day(prof), start=START + pd.Timedelta(hours=1))
    assert not any(build_signals(candles, 0.001, "va")[:47])


def test_signals_do_not_use_future_candles():
    rng = np.random.default_rng(3)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.006, 24 * 30)))
    opens = np.r_[close[0], close[:-1]]
    spread = np.abs(rng.normal(0, 0.003, len(close))) * close
    bars = list(zip(opens, np.maximum(opens, close) + spread, np.minimum(opens, close) - spread, close,
                    rng.uniform(1, 10, len(close))))
    candles = _candles(bars)
    full = build_signals(candles, 0.001, "va")
    assert any(full)
    for n in (100, 333, 719):
        assert build_signals(candles.iloc[:n].reset_index(drop=True), 0.001, "va") == full[:n]


def _sim(day2, risk=0.01, max_leverage=3.0, fee=0.0):
    candles = _candles(_flat(100, 24) + day2)
    signal = Signal(VA_REVERSAL, 1, 99.0, 102.0, START + pd.Timedelta(days=1))
    signals = [None] * len(candles)
    signals[24] = signal
    return simulate_signals(candles, signals, fee, risk, max_leverage)


def test_target_hit_with_risk_sizing():
    r = _sim(_flat(100, 1) + [(100, 102.5, 99.8, 102.2, 1.0)] + _flat(102, 22), risk=0.01)
    assert (r["trades"], r["wins"]) == (1, 1)
    assert r["total_return"] == pytest.approx(0.02)  # 1 % Risiko, 2R
    assert r["setups"][VA_REVERSAL] == {"trades": 1, "wins": 1, "avg_r": pytest.approx(2), "total_r": pytest.approx(2)}


def test_stop_loses_one_r():
    r = _sim(_flat(100, 1) + [(100, 100.2, 98.5, 98.8, 1.0)] + _flat(99, 22), risk=0.01)
    assert r["total_return"] == pytest.approx(-0.01)
    assert r["setups"][VA_REVERSAL]["avg_r"] == pytest.approx(-1)


def test_time_stop_closes_at_session_end():
    r = _sim(_flat(100, 23) + [(100, 100.6, 99.9, 100.5, 1.0)] + _flat(100, 5))
    assert r["setups"][VA_REVERSAL]["total_r"] == pytest.approx(0.5)


def test_leverage_cap_limits_size():
    r = _sim(_flat(100, 1) + [(100, 102.5, 99.8, 102.2, 1.0)] + _flat(102, 22), risk=0.1, max_leverage=3.0)
    assert r["total_return"] == pytest.approx(3 * 0.02)


def test_fees_scale_with_position_size():
    r = _sim(_flat(100, 1) + [(100, 102.5, 99.8, 102.2, 1.0)] + _flat(102, 22), fee=0.001)
    assert r["total_return"] == pytest.approx((1 - 0.001) * (1 + 0.02) * (1 - 0.001) - 1)


def test_open_beyond_stop_skips_trade():
    candles = _candles(_flat(100, 24) + [(98, 98.2, 97.8, 98, 1.0)] + _flat(98, 23))
    signals = [None] * len(candles)
    signals[23] = Signal(VA_REVERSAL, 1, 99.0, 102.0, START + pd.Timedelta(days=1))
    assert simulate_signals(candles, signals, 0.0)["trades"] == 0


def test_walk_forward_scores_only_test_windows():
    rng = np.random.default_rng(5)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.006, 24 * 40)))
    opens = np.r_[close[0], close[:-1]]
    bars = list(zip(opens, np.maximum(opens, close) * 1.003, np.minimum(opens, close) * 0.997, close,
                    rng.uniform(1, 10, len(close))))
    grid = [(0.001, "va", 0.0), (0.002, 2.0, 0.005)]
    r = walk_forward_signals(_candles(bars), grid, start=100, train=400, test=200, fee=0.0)
    assert len(r["chosen"]) == 2 and set(r["chosen"]) <= set(grid)
    assert set(r["fixed"]) == set(grid)


def test_min_stop_drops_signals_with_tight_stop():
    prof = session_profile(_candles(DAY1), 0.001)
    candles = _candles(DAY1 + _reversal_day(prof))
    entry, s = prof.val + 0.2, build_signals(candles, 0.001, "va")[26]
    dist = (entry - s.stop) / entry  # ≈ 2,2 %
    assert build_signals(candles, 0.001, "va", dist * 0.99)[26] == s
    assert build_signals(candles, 0.001, "va", dist * 1.01)[26] is None


# --- Setup 1: POC-Bounce ---
DAY1_ABOVE = DAY1[:-1] + [(101, 103, 101, 102.8, 1.0)]  # Vortag schließt über VAH


def _bounce_day(prof, touch_open_offset=0.3):
    """Zwei Kerzen über dem POC, dann erste Berührung: Docht durch den POC, grüner Schluss darüber, mehr Volumen"""
    poc = prof.poc
    return (_flat(poc + 1, 2) + [(poc + touch_open_offset, poc + 0.6, poc - 0.2, poc + 0.5, 3.0)]
            + _flat(poc + 0.5, 21))


def test_poc_bounce_long_on_first_touch():
    prof = session_profile(_candles(DAY1_ABOVE), 0.001)
    signals = build_signals(_candles(DAY1_ABOVE + _bounce_day(prof)), 0.001, "va", setups=(POC_BOUNCE,))
    hits = [(t, s) for t, s in enumerate(signals) if s]
    assert [t for t, _ in hits] == [26]
    s = hits[0][1]
    assert (s.setup, s.direction, s.target) == (POC_BOUNCE, 1, prof.vah)
    assert s.stop == pytest.approx(min(prof.poc - 0.2, prof.node_low) * (1 - STOP_BUFFER))


def test_poc_bounce_short_mirrored():
    prof = session_profile(_candles(_mirror(DAY1_ABOVE)), 0.001)
    day2 = _mirror(_bounce_day(SimpleNamespace(poc=200 - prof.poc)))
    s = build_signals(_candles(_mirror(DAY1_ABOVE) + day2), 0.001, "va", setups=(POC_BOUNCE,))[26]
    assert (s.direction, s.target) == (-1, prof.val)
    assert s.stop > prof.poc


def _late_confirmation(prof, at):
    """Erste Berührung (Index 2) schließt rot, gültige Bestätigungskerze bei Index at des Tages"""
    day2 = _bounce_day(prof, touch_open_offset=0.55)
    return day2[:at] + [(prof.poc + 0.1, prof.poc + 0.7, prof.poc - 0.1, prof.poc + 0.6, 9.0)] + day2[at + 1:]


def test_poc_bounce_confirms_within_three_candles_after_touch():
    prof = session_profile(_candles(DAY1_ABOVE), 0.001)
    signals = build_signals(_candles(DAY1_ABOVE + _late_confirmation(prof, 5)), 0.001, "va", setups=(POC_BOUNCE,))
    assert [t for t, s in enumerate(signals) if s] == [29]
    assert signals[29].stop == pytest.approx(min(prof.poc - 0.2, prof.node_low) * (1 - STOP_BUFFER))


def test_poc_bounce_confirmation_window_ends():
    prof = session_profile(_candles(DAY1_ABOVE), 0.001)
    assert not any(build_signals(_candles(DAY1_ABOVE + _late_confirmation(prof, 6)), 0.001, "va",
                                 setups=(POC_BOUNCE,)))


def test_poc_bounce_aborts_on_close_through_node():
    prof = session_profile(_candles(DAY1_ABOVE), 0.001)
    day2 = _late_confirmation(prof, 4)
    day2[3] = (prof.poc, prof.poc + 0.05, prof.node_low - 0.5, prof.node_low - 0.3, 1.0)
    assert not any(build_signals(_candles(DAY1_ABOVE + day2), 0.001, "va", setups=(POC_BOUNCE,)))


def test_poc_bounce_needs_previous_close_outside_va():
    prof = session_profile(_candles(DAY1), 0.001)
    assert not any(build_signals(_candles(DAY1 + _bounce_day(prof)), 0.001, "va", setups=(POC_BOUNCE,)))


# --- Setup 3: Breakout mit Pullback ---
def _breakout_day(vah, pullback_close_offset=0.3, volume=30.0):
    """Starke Ausbruchskerze über VAH, flacher Pullback an die Kante, Strukturbruch bei Kerze 3"""
    return [(vah - 0.1, vah + 2.5, vah - 0.2, vah + 2.3, volume),
            (vah + 2.3, vah + 2.4, vah + 0.1, vah + pullback_close_offset, 5.0),
            (vah + 0.3, vah + 1.5, vah + 0.2, vah + 1.4, 5.0),
            (vah + 1.4, vah + 3.0, vah + 1.3, vah + 2.8, 5.0)] + _flat(vah + 2.8, 20)


def test_breakout_long_after_pullback_and_bos():
    prof = session_profile(_candles(DAY1), 0.001)
    signals = build_signals(_candles(DAY1 + _breakout_day(prof.vah)), 0.001, 2.0, setups=(BREAKOUT,))
    hits = [(t, s) for t, s in enumerate(signals) if s]
    assert [t for t, _ in hits] == [27]
    s, entry = hits[0][1], prof.vah + 2.8
    assert (s.setup, s.direction) == (BREAKOUT, 1)
    assert s.stop == pytest.approx((prof.vah + 0.1) * (1 - STOP_BUFFER))
    assert s.target == pytest.approx(entry + 2 * (entry - s.stop))


def test_breakout_short_mirrored():
    prof = session_profile(_candles(_mirror(DAY1)), 0.001)
    day2 = _mirror(_breakout_day(200 - prof.val))
    s = build_signals(_candles(_mirror(DAY1) + day2), 0.001, 2.0, setups=(BREAKOUT,))[27]
    assert s.direction == -1 and s.stop == pytest.approx((prof.val - 0.1) * (1 + STOP_BUFFER))


def test_breakout_fails_when_pullback_closes_back_inside_va():
    prof = session_profile(_candles(DAY1), 0.001)
    day2 = _breakout_day(prof.vah, pullback_close_offset=-0.1)
    assert not any(build_signals(_candles(DAY1 + day2), 0.001, 2.0, setups=(BREAKOUT,)))


def test_breakout_needs_high_volume():
    prof = session_profile(_candles(DAY1), 0.001)
    day2 = _breakout_day(prof.vah, volume=5.0)
    assert not any(build_signals(_candles(DAY1 + day2), 0.001, 2.0, setups=(BREAKOUT,)))


def test_breakout_targets_nearest_naked_poc():
    day_a = _flat(110, 24)  # POC bei 110, danach nie wieder berührt
    prof_a, prof = session_profile(_candles(day_a), 0.001), session_profile(_candles(DAY1), 0.001)
    candles = _candles(day_a + DAY1 + _breakout_day(prof.vah))
    s = build_signals(candles, 0.001, "va", setups=(BREAKOUT,))[51]
    assert s.target == pytest.approx(prof_a.poc)


def test_setups_are_combined_first_one_wins():
    prof = session_profile(_candles(DAY1), 0.001)
    candles = _candles(DAY1 + _breakout_day(prof.vah))
    assert build_signals(candles, 0.001, 2.0)[27].setup == BREAKOUT
    assert not any(build_signals(candles, 0.001, 2.0, setups=(VA_REVERSAL, POC_BOUNCE)))
