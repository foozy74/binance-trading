from unittest.mock import MagicMock

import ccxt
import pytest

from app.config import settings
from app.services.binance import BinanceService
from app.services.exchange import create_exchange, symbol_assets


@pytest.fixture
def hyperliquid(monkeypatch):
    monkeypatch.setattr(settings, "EXCHANGE", "hyperliquid")
    monkeypatch.setattr(settings, "SYMBOL", "BTC/USDC:USDC")


def test_create_exchange_hyperliquid(hyperliquid):
    assert isinstance(create_exchange(), ccxt.hyperliquid)


def test_create_exchange_default_binance():
    assert isinstance(create_exchange(), ccxt.binance)


def test_symbol_assets_perp():
    assert symbol_assets("BTC/USDC:USDC") == ("BTC", "USDC")
    assert symbol_assets("BTC/USDT") == ("BTC", "USDT")


def test_perp_sell_sizes_from_margin_balance(hyperliquid):
    service = BinanceService(dry_run=True)
    balance = {"BTC": 0, "USDC": 10000}
    amount = service.calculate_position_size("SELL", balance, {"last": 50000})
    assert amount == 10000 * settings.TRADE_PERCENTAGE / 50000


def test_hyperliquid_market_order_passes_price(hyperliquid, monkeypatch):
    service = BinanceService(dry_run=False)
    service.exchange = MagicMock()
    service.exchange.fetch_ticker.return_value = {"last": 50000}
    service.create_order("BTC/USDC:USDC", "buy", 0.01)
    service.exchange.create_order.assert_called_once_with("BTC/USDC:USDC", "market", "buy", 0.01, 50000)


def test_fetch_balance_uses_symbol_assets(hyperliquid):
    service = BinanceService(dry_run=True)
    service.exchange = MagicMock()
    service.exchange.fetch_balance.return_value = {"total": {"USDC": 500}}
    assert service.fetch_balance() == {"BTC": 0, "USDC": 500}


@pytest.mark.parametrize("net, side, expected", [
    (0, "buy", 0.1),       # keine Position -> normal eröffnen
    (0.2, "buy", None),    # Long offen -> nicht nachkaufen
    (-0.2, "sell", None),  # Short offen -> nicht nachverkaufen
    (-0.2, "buy", 0.3),    # Short offen + BUY -> schließen und Long eröffnen
    (0.2, "sell", 0.3),    # Long offen + SELL -> schließen und Short eröffnen
])
def test_adjust_for_position(hyperliquid, net, side, expected):
    service = BinanceService(dry_run=True)
    service.fetch_net_position = MagicMock(return_value=net)
    result = service.adjust_for_position(side, 0.1)
    assert result == (None if expected is None else pytest.approx(expected))


def test_fetch_net_position_live(hyperliquid):
    service = BinanceService(dry_run=False)
    service.exchange = MagicMock()
    service.exchange.fetch_positions.return_value = [{"side": "short", "contracts": 0.5}]
    assert service.fetch_net_position("BTC/USDC:USDC") == -0.5


def test_dry_run_tracks_simulated_position(hyperliquid):
    service = BinanceService(dry_run=True)
    service.exchange = MagicMock()
    service.exchange.fetch_ticker.return_value = {"last": 50000}
    service.create_order("BTC/USDC:USDC", "buy", 0.1)
    assert service.fetch_net_position("BTC/USDC:USDC") == pytest.approx(0.1)
    service.create_order("BTC/USDC:USDC", "sell", 0.3)
    assert service.fetch_net_position("BTC/USDC:USDC") == pytest.approx(-0.2)


def test_place_protection_creates_reduce_only_triggers(hyperliquid, monkeypatch):
    monkeypatch.setattr(settings, "STOP_ATR_MULTIPLE", 0.0)  # feste Prozent-Stops
    service = BinanceService(dry_run=False)
    service.exchange = MagicMock()
    service.place_protection("BTC/USDC:USDC", "buy", 0.1, 50000, {})
    calls = service.exchange.create_order.call_args_list
    assert calls[0].args == ("BTC/USDC:USDC", "market", "sell", 0.1, pytest.approx(50000 * (1 - settings.TRAILING_STOP_PERCENT)))
    assert calls[0].kwargs["params"]["reduceOnly"] is True
    assert "stopLossPrice" in calls[0].kwargs["params"]
    assert "takeProfitPrice" in calls[1].kwargs["params"]


def test_cancel_open_orders(hyperliquid):
    service = BinanceService(dry_run=False)
    service.exchange = MagicMock()
    service.exchange.fetch_open_orders.return_value = [{"id": "1"}, {"id": "2"}]
    service.cancel_open_orders("BTC/USDC:USDC")
    service.exchange.cancel_orders.assert_called_once_with(["1", "2"], "BTC/USDC:USDC")


def test_place_protection_atr_stop_only(hyperliquid, monkeypatch):
    monkeypatch.setattr(settings, "STOP_ATR_MULTIPLE", 3.0)
    monkeypatch.setattr(settings, "TAKE_PROFIT_R", 0.0)
    service = BinanceService(dry_run=False)
    service.exchange = MagicMock()
    service.place_protection("BTC/USDC:USDC", "sell", 0.1, 50000, {"ATR": 500})
    service.exchange.create_order.assert_called_once()
    args, kwargs = service.exchange.create_order.call_args
    assert args[2] == "buy" and args[4] == pytest.approx(51500)
    assert kwargs["params"] == {"stopLossPrice": pytest.approx(51500), "reduceOnly": True}


def test_dry_run_simulated_stop_closes_position(hyperliquid, monkeypatch):
    monkeypatch.setattr(settings, "STOP_ATR_MULTIPLE", 0.0)
    service = BinanceService(dry_run=True)
    service.exchange = MagicMock()
    service.exchange.fetch_ticker.return_value = {"last": 50000}
    service.create_order("BTC/USDC:USDC", "buy", 0.1)
    service.place_protection("BTC/USDC:USDC", "buy", 0.1, 50000, {})

    service.exchange.fetch_ticker.return_value = {"last": 50000 * (1 - settings.TRAILING_STOP_PERCENT) - 1}
    assert service.check_simulated_stops("BTC/USDC:USDC") == "stop_loss"
    assert service.fetch_net_position("BTC/USDC:USDC") == pytest.approx(0)
    assert service.check_simulated_stops("BTC/USDC:USDC") is None
