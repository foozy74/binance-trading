import pytest
from unittest.mock import MagicMock

import pandas as pd

import app.bot.signals as signals
import app.bot.trader as trader
from app.services.binance import BinanceService


def _ohlcv(n: int) -> list:
    """Erzeugt n stündliche OHLCV-Kerzen"""
    return [[i * 3_600_000, 100.0, 101.0, 99.0, 100.0, 1.0] for i in range(n)]


def test_buy_signal_uppercase_uses_usdt_balance():
    service = BinanceService(dry_run=True)
    amount = service.calculate_position_size("BUY", {"BTC": 0.5, "USDT": 10000}, {"last": 40000})
    assert amount == 10000 * 0.10 / 40000


def test_fetch_market_data_drops_unfinished_candle(monkeypatch):
    exchange = MagicMock()
    exchange.fetch_ohlcv.return_value = _ohlcv(101)
    monkeypatch.setattr(signals, "create_exchange", lambda: exchange)
    monkeypatch.setattr(signals, "calculate_all_indicators", lambda df: df)

    df = signals.fetch_market_data()

    assert len(df) == 100
    assert df.iloc[-1]["timestamp"] == pd.to_datetime(99 * 3_600_000, unit="ms")


def test_trades_only_once_per_closed_candle(monkeypatch):
    frames = iter([
        pd.DataFrame({"timestamp": [1, 2]}),
        pd.DataFrame({"timestamp": [1, 2]}),
        pd.DataFrame({"timestamp": [2, 3]}),
    ])
    monkeypatch.setattr(trader, "fetch_market_data", lambda: next(frames))
    monkeypatch.setattr(trader, "SessionLocal", MagicMock())
    monkeypatch.setattr(trader, "SignalRepository", MagicMock())
    bot = trader.TradingBot()
    bot.strategy = MagicMock(name="strategy")
    bot.strategy.generate_signal.return_value = ("BUY", 0.7)
    bot._execute_trade = MagicMock()

    for _ in range(3):
        bot._execute_loop()

    assert bot._execute_trade.call_count == 2


def test_hyperliquid_trade_cancels_then_orders_then_protects(monkeypatch):
    monkeypatch.setattr(trader.settings, "EXCHANGE", "hyperliquid")
    monkeypatch.setattr(trader, "TradeRepository", MagicMock())
    bot = trader.TradingBot()
    bot.telegram = MagicMock()
    bot.binance = MagicMock()
    bot.binance.fetch_ticker.return_value = {"last": 50000}
    bot.binance.calculate_position_size.return_value = 0.1
    bot.binance.adjust_for_position.return_value = 0.3  # Short 0.2 wird gedreht
    bot.binance.create_order.return_value = {"price": None, "average": 50010}

    df = pd.DataFrame({"ATR": [500.0]})
    bot._execute_trade("BUY", df, MagicMock())

    names = [c[0] for c in bot.binance.method_calls]
    assert names.index("cancel_open_orders") < names.index("create_order") < names.index("place_protection")
    bot.binance.create_order.assert_called_once_with(trader.settings.SYMBOL, "buy", 0.3)
    bot.binance.place_protection.assert_called_once_with(trader.settings.SYMBOL, "BUY", 0.1, 50010, {"ATR": 500.0})


@pytest.mark.parametrize("last_volume, trades", [(1.0, 0), (3.0, 1)])
def test_volume_filter_blocks_low_volume_signal(monkeypatch, last_volume, trades):
    monkeypatch.setattr(trader.settings, "VOLUME_FILTER", 2.0)
    df = pd.DataFrame({"timestamp": range(25), "volume": [1.0] * 24 + [last_volume]})
    monkeypatch.setattr(trader, "fetch_market_data", lambda: df)
    monkeypatch.setattr(trader, "SessionLocal", MagicMock())
    monkeypatch.setattr(trader, "SignalRepository", MagicMock())
    bot = trader.TradingBot()
    bot.strategy = MagicMock()
    bot.strategy.generate_signal.return_value = ("BUY", 0.7)
    bot._execute_trade = MagicMock()

    bot._execute_loop()

    assert bot._execute_trade.call_count == trades
