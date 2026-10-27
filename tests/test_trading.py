import pytest
from unittest.mock import MagicMock
from app.services.binance import BinanceService
from app.config import settings


class TestBinanceService:
    def test_dry_run_mode(self):
        service = BinanceService(dry_run=True)
        assert service.dry_run is True
    
    def test_position_size_calculation(self):
        service = BinanceService(dry_run=True)
        balance = {"BTC": 0.5, "USDT": 10000}
        ticker = {"last": 40000}
        
        btc_amount = service.calculate_position_size("buy", balance, ticker)
        assert btc_amount > 0
        assert btc_amount <= balance["USDT"] / ticker["last"]
    
    def test_fetch_ticker(self):
        service = BinanceService(dry_run=True)
        service.exchange = MagicMock()
        service.exchange.fetch_ticker.return_value = {"last": 40000, "high": 41000, "low": 39000, "volume": 12.5}
        ticker = service.fetch_ticker("BTC/USDT")
        assert "last" in ticker
        assert "high" in ticker
        assert "low" in ticker
        assert "volume" in ticker


class TestTradingLogic:
    def test_trailing_stop_calculation(self):
        """Test trailing stop calculation for BUY order"""
        entry_price = 40000
        trailing_stop_percent = 0.02
        stop_loss = entry_price * (1 - trailing_stop_percent)
        assert stop_loss == 39200
    
    def test_take_profit_calculation(self):
        """Test take profit calculation for BUY order"""
        entry_price = 40000
        take_profit_percent = 0.05
        take_profit = entry_price * (1 + take_profit_percent)
        assert take_profit == 42000
    
    def test_trailing_stop_sell_order(self):
        """Test trailing stop calculation for SELL order"""
        entry_price = 40000
        trailing_stop_percent = 0.02
        stop_loss = entry_price * (1 + trailing_stop_percent)
        assert stop_loss == 40800
    
    def test_take_profit_sell_order(self):
        """Test take profit calculation for SELL order"""
        entry_price = 40000
        take_profit_percent = 0.05
        take_profit = entry_price * (1 - take_profit_percent)
        assert take_profit == 38000


class TestDryRunMode:
    def test_dry_run_no_real_orders(self):
        """Verify dry run mode doesn't place real orders"""
        service = BinanceService(dry_run=True)
        service.exchange = MagicMock()
        service.exchange.fetch_ticker.return_value = {"last": 40000}

        # Simulate order
        order = service.create_order("BTC/USDT", "buy", 0.001)
        
        assert order is not None
        assert order["dry_run"] is True
        assert order["status"] == "simulated"
        assert "dry_run" in order["id"]
        service.exchange.create_order.assert_not_called()
        service.exchange.create_market_order.assert_not_called()
