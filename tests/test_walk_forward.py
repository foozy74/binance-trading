import pandas as pd
import pytest

import app.bot.walk_forward as wf


def _candles(n: int, volume=None) -> pd.DataFrame:
    return pd.DataFrame({
        "open": [100.0] * n, "high": [100.0] * n, "low": [100.0] * n, "close": [100.0] * n,
        "volume": volume or [1.0] * n,
    })


def test_volume_filter_drops_signals_on_low_volume():
    candles = _candles(4, volume=[1, 1, 3, 1])
    signals = ["BUY", "SELL", "BUY", "HOLD"]
    assert wf.apply_volume_filter(candles, signals, 1.5, window=2) == ["HOLD", "HOLD", "BUY", "HOLD"]


def test_volume_filter_zero_keeps_everything():
    assert wf.apply_volume_filter(_candles(2), ["BUY", "SELL"], 0) == ["BUY", "SELL"]


def test_folds_never_overlap_train_and_test():
    folds = wf.make_folds(total=30, start=0, train=10, test=5)
    assert folds == [(0, 10, 15), (5, 15, 20), (10, 20, 25), (15, 25, 30)]


def test_params_chosen_on_train_only(monkeypatch):
    # Param "good" gewinnt nur im Training, im Test verliert er -> Ergebnis muss den Verlust zeigen
    seen = []

    def fake_simulate(candles, signals, fee, stop_loss=None, take_profit=None):
        seen.append((len(candles), stop_loss))
        in_train = len(candles) == 10
        good = stop_loss == 0.01
        return {"total_return": (0.5 if good else 0.0) if in_train else (-0.1 if good else 0.0), "trades": 1}

    monkeypatch.setattr(wf, "simulate", fake_simulate)
    grid = [(0, None, None, None), (0, 0.01, 0.02, None)]
    result = wf.walk_forward(_candles(15), ["HOLD"] * 15, grid, start=0, train=10, test=5, fee=0.0)

    assert result["chosen"] == [(0, 0.01, 0.02, None)]
    assert result["oos_return"] == pytest.approx(-0.1)
    assert all(length in (10, 5) for length, _ in seen)


def _fake_by_fold(returns):
    """simulate-Ersatz: Rendite je (Signal-Kennung, Fenster-Start-Kerze) aus returns"""
    def fake_simulate(candles, signals, fee, stop_loss=None, take_profit=None):
        return {"total_return": returns[(signals[0], int(candles["open"].iloc[0]))], "trades": 1}
    return fake_simulate


def _indexed_candles(n):
    candles = _candles(n)
    candles["open"] = range(n)  # Kerzen-Index im Open, damit der Fake das Fenster erkennt
    return candles


def test_select_strategy_picks_best_strategy_per_fold(monkeypatch):
    # Fold 1: Train 0-10, Test 10-15; Fold 2: Train 5-15, Test 15-20
    returns = {
        ("A", 0): 0.3, ("B", 0): 0.1, ("A", 10): 0.0, ("B", 10): 0.0,
        ("A", 5): 0.0, ("B", 5): 0.2, ("A", 15): -0.5, ("B", 15): 0.1,
    }
    monkeypatch.setattr(wf, "simulate", _fake_by_fold(returns))
    signals = {"A": ["A"] * 20, "B": ["B"] * 20}

    result = wf.select_strategy(_indexed_candles(20), signals, [(0, None, None, None)], start=0, train=10, test=5, fee=0.0)

    assert [name for name, _ in result["chosen"]] == ["A", "B"]
    assert result["oos_return"] == pytest.approx(1.0 * 1.1 - 1)
    # Feste Wahl aus Fold 1 (A) bleibt auch in Fold 2 -> -50 %
    assert result["fixed_return"] == pytest.approx(0.5 - 1)
