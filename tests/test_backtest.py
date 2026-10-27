import pandas as pd
import pytest

from app.bot.backtest import simulate


def _candles(opens, closes):
    return pd.DataFrame({"open": opens, "close": closes})


def test_entry_at_next_open_and_flip():
    # Signal BUY bei Schluss Kerze 0 -> Einstieg Open Kerze 1 (100); SELL bei Kerze 1 -> Drehen bei Open Kerze 2 (110)
    candles = _candles([99, 100, 110, 99], [100, 109, 100, 99])
    result = simulate(candles, ["BUY", "SELL", "HOLD", "HOLD"], fee=0.0)

    assert result["trades"] == 2
    assert result["wins"] == 2  # Long +10 %, Short 110 -> 99 = +10 %
    assert result["total_return"] == pytest.approx(1.1 * 1.1 - 1)


def test_same_direction_signal_does_not_add():
    candles = _candles([100, 100, 100, 100], [100, 100, 100, 100])
    result = simulate(candles, ["BUY", "BUY", "BUY", "HOLD"], fee=0.001)

    # Nur ein Einstieg + Schließen am Ende -> genau zwei Gebühren
    assert result["trades"] == 1
    assert result["total_return"] == pytest.approx(0.999 ** 2 - 1)


def test_drawdown_measured_mark_to_market():
    candles = _candles([100, 100, 80, 100], [100, 80, 100, 100])
    result = simulate(candles, ["BUY", "HOLD", "HOLD", "HOLD"], fee=0.0)
    assert result["max_drawdown"] == pytest.approx(-0.2)


def _bars(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


def test_stop_loss_exits_long_at_stop_price():
    candles = _bars([[100, 100, 100, 100], [100, 101, 90, 95], [95, 96, 94, 95]])
    result = simulate(candles, ["BUY", "HOLD", "HOLD"], fee=0.0, stop_loss=0.02)
    assert result["trades"] == 1
    assert result["total_return"] == pytest.approx(-0.02)


def test_take_profit_exits_short():
    candles = _bars([[100, 100, 100, 100], [100, 101, 94, 96], [96, 97, 90, 90]])
    result = simulate(candles, ["SELL", "HOLD", "HOLD"], fee=0.0, take_profit=0.05)
    assert result["total_return"] == pytest.approx(0.05)


def test_stop_loss_wins_when_both_hit_in_same_candle():
    candles = _bars([[100, 100, 100, 100], [100, 110, 90, 100], [100, 100, 100, 100]])
    result = simulate(candles, ["BUY", "HOLD", "HOLD"], fee=0.0, stop_loss=0.02, take_profit=0.05)
    assert result["total_return"] == pytest.approx(-0.02)


def test_gap_through_stop_fills_at_open():
    candles = _bars([[100, 100, 100, 100], [100, 100, 100, 100], [90, 91, 89, 90]])
    result = simulate(candles, ["BUY", "HOLD", "HOLD"], fee=0.0, stop_loss=0.02)
    assert result["total_return"] == pytest.approx(-0.10)


def _atr_bars(rows, atr):
    candles = _bars(rows)
    candles["ATR"] = atr
    return candles


def test_atr_stop_distance_uses_atr_of_signal_candle():
    from app.bot.backtest import AtrStop
    # ATR 5 bei Signal-Kerze, 2x ATR -> Stop 10 unter Einstieg 100 -> Ausstieg 90
    candles = _atr_bars([[100, 100, 100, 100], [100, 101, 85, 88], [88, 88, 88, 88]], [5, 50, 50])
    result = simulate(candles, ["BUY", "HOLD", "HOLD"], fee=0.0, stop_loss=AtrStop(2.0))
    assert result["total_return"] == pytest.approx(-0.10)


def test_atr_take_profit_is_multiple_of_stop_distance():
    from app.bot.backtest import AtrStop
    # Stop-Abstand 10, TP 2R = 20 -> Short von 100 auf 80
    candles = _atr_bars([[100, 100, 100, 100], [100, 101, 79, 80], [80, 80, 80, 80]], [5, 5, 5])
    result = simulate(candles, ["SELL", "HOLD", "HOLD"], fee=0.0, stop_loss=AtrStop(2.0, take_profit_r=2.0))
    assert result["total_return"] == pytest.approx(0.20)


def test_atr_stop_without_atr_value_keeps_position_unprotected():
    from app.bot.backtest import AtrStop
    candles = _atr_bars([[100, 100, 100, 100], [100, 100, 50, 90]], [0, 0])
    result = simulate(candles, ["BUY", "HOLD"], fee=0.0, stop_loss=AtrStop(2.0))
    assert result["total_return"] == pytest.approx(-0.10)  # Schließen am Ende zum Close 90
