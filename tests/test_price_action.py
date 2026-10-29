import numpy as np
import pandas as pd
import pytest

from app.bot.price_action import STOP_BUFFER, build_orders, simulate_orders, walk_forward_orders

# (open, high, low, close): Swing-Hoch 106 bei 2, Korrekturtief 98 bei 5 (Zonen-Kerze), Ausbruch bei 7
BASE = [(100, 101, 99, 100), (100, 103, 99.5, 102), (102, 106, 101, 105), (105, 105.5, 102, 103),
        (103, 103.5, 100, 101), (101, 101.5, 98, 99), (99, 104, 99, 103.5)]
BREAKOUT = (103.5, 112, 103, 111)


def _candles(bars):
    return pd.DataFrame(bars, columns=["open", "high", "low", "close"]).assign(volume=1.0)


def _mirror(bars):
    """Spiegelt den Kursverlauf an 100 – aus Aufwärts- wird Abwärtstrend"""
    return [(200 - o, 200 - lo, 200 - h, 200 - c) for o, h, lo, c in bars]


def test_breakout_creates_long_order_at_demand_zone():
    orders = build_orders(_candles(BASE + [BREAKOUT]))
    assert orders[:7] == [None] * 7
    o = orders[7]
    assert (o.direction, o.entry, o.target, o.zone) == (1, 101.5, 112, 5)
    assert o.stop == pytest.approx(98 * (1 - STOP_BUFFER))


def test_short_order_at_supply_zone_in_downtrend():
    o = build_orders(_candles(_mirror(BASE + [BREAKOUT])))[7]
    assert (o.direction, o.entry, o.target, o.zone) == (-1, 98.5, 88, 5)
    assert o.stop == pytest.approx(102 * (1 + STOP_BUFFER))


def test_crv_filter_rejects_close_target():
    # Ziel 108: (108 - 101.5) / (101.5 - 97.95) ≈ 1.8 < 2.5
    assert build_orders(_candles(BASE + [(103.5, 108, 103, 107.5)]))[7] is None
    assert build_orders(_candles(BASE + [(103.5, 108, 103, 107.5)]), min_crv=1.5)[7] is not None


def test_close_below_valid_low_ends_uptrend():
    orders = build_orders(_candles(BASE + [BREAKOUT, (111, 111, 96, 96.5)]))
    assert orders[8] is None or orders[8].direction == -1


def test_orders_do_not_use_future_candles():
    rng = np.random.default_rng(11)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 600)))
    opens = np.r_[close[0], close[:-1]]
    spread = np.abs(rng.normal(0, 0.004, 600)) * close
    candles = _candles(list(zip(opens, np.maximum(opens, close) + spread, np.minimum(opens, close) - spread, close)))
    full = build_orders(candles)
    assert any(full)
    for n in (150, 333, 599):
        assert build_orders(candles.iloc[:n].reset_index(drop=True)) == full[:n]


def _trade(*bars, fee=0.0):
    candles = _candles(BASE + [BREAKOUT, *bars])
    return simulate_orders(candles, build_orders(candles), fee)


def test_limit_fill_then_take_profit():
    r = _trade((111, 111.5, 101, 102), (102, 113, 101.8, 112.5))
    assert (r["trades"], r["wins"]) == (1, 1)
    assert r["total_return"] == pytest.approx(112 / 101.5 - 1)


def test_fees_charged_on_entry_and_exit():
    r = _trade((111, 111.5, 101, 102), (102, 113, 101.8, 112.5), fee=0.001)
    assert r["total_return"] == pytest.approx((112 / 101.5) * 0.999 ** 2 - 1)


def test_stop_on_fill_candle_counts_as_loss():
    r = _trade((111, 111.5, 97, 98))
    assert (r["trades"], r["wins"]) == (1, 0)
    assert r["total_return"] == pytest.approx(98 * (1 - STOP_BUFFER) / 101.5 - 1)


def test_gap_below_entry_fills_at_open():
    r = _trade((100, 100.5, 99.5, 100.2), (100.2, 113, 100, 112.5))
    assert r["total_return"] == pytest.approx(112 / 100 - 1)


def test_zone_is_traded_only_once():
    r = _trade((111, 111.5, 97, 98), (98.5, 102, 98.2, 101), (101, 101.4, 100, 101))
    assert r["trades"] == 1


def test_walk_forward_scores_only_test_windows():
    rng = np.random.default_rng(5)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 900)))
    opens = np.r_[close[0], close[:-1]]
    candles = _candles(list(zip(opens, np.maximum(opens, close) * 1.003, np.minimum(opens, close) * 0.997, close)))
    grid = [(2, 2.5), (3, 3.0)]
    r = walk_forward_orders(candles, grid, start=100, train=400, test=200, fee=0.0)
    assert len(r["chosen"]) == 2 and set(r["chosen"]) <= set(grid)
    assert set(r["fixed"]) == set(grid)
