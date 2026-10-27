import pytest

from app.bot.stops import AtrStop, configured_stop, stop_prices
from app.config import settings


@pytest.fixture
def atr_mode(monkeypatch):
    monkeypatch.setattr(settings, "STOP_ATR_MULTIPLE", 3.0)
    monkeypatch.setattr(settings, "TAKE_PROFIT_R", 0.0)


def test_configured_stop_atr_without_take_profit(atr_mode):
    assert configured_stop() == (AtrStop(3.0, None), None)


def test_configured_stop_falls_back_to_percent(monkeypatch):
    monkeypatch.setattr(settings, "STOP_ATR_MULTIPLE", 0.0)
    assert configured_stop() == (settings.TRAILING_STOP_PERCENT, settings.TAKE_PROFIT_PERCENT)


def test_stop_prices_long_atr(atr_mode):
    # ATR 500 x 3 = 1500 unter Einstieg 50000, kein TP
    assert stop_prices("BUY", 50000, {"ATR": 500}) == {"stopLossPrice": pytest.approx(48500)}


def test_stop_prices_short_with_take_profit_r(atr_mode, monkeypatch):
    monkeypatch.setattr(settings, "TAKE_PROFIT_R", 2.0)
    prices = stop_prices("SELL", 50000, {"ATR": 500})
    assert prices == {"stopLossPrice": pytest.approx(51500), "takeProfitPrice": pytest.approx(47000)}


def test_stop_prices_without_atr_has_no_stop(atr_mode):
    assert stop_prices("BUY", 50000, {"ATR": 0}) == {}
