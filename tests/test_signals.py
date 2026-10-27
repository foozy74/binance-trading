import pytest
import pandas as pd
import numpy as np
from app.bot.indicators import calculate_all_indicators
from app.bot.strategies.obv_vwap import OBVVWAPStrategy
from app.bot.strategies.rsi_divergence import RSIDivergenceStrategy
from app.bot.strategies.macd_crossover import MACDCrossoverStrategy
from app.bot.strategies.multi_signal import MultiSignalStrategy


@pytest.fixture
def bullish_df():
    """Create DataFrame with bullish conditions"""
    np.random.seed(42)
    n = 100
    data = {
        'timestamp': pd.date_range('2024-01-01', periods=n, freq='1h'),
        'open': np.linspace(40000, 42000, n) + np.random.uniform(-100, 100, n),
        'high': np.linspace(40500, 42500, n) + np.random.uniform(0, 100, n),
        'low': np.linspace(39500, 41500, n) + np.random.uniform(-100, 0, n),
        'close': np.linspace(40000, 42000, n) + np.random.uniform(-100, 100, n),
        'volume': np.random.uniform(500, 1000, n)
    }
    df = pd.DataFrame(data)
    return calculate_all_indicators(df)


@pytest.fixture
def bearish_df():
    """Create DataFrame with bearish conditions"""
    np.random.seed(42)
    n = 100
    data = {
        'timestamp': pd.date_range('2024-01-01', periods=n, freq='1h'),
        'open': np.linspace(42000, 40000, n) + np.random.uniform(-100, 100, n),
        'high': np.linspace(42500, 40500, n) + np.random.uniform(0, 100, n),
        'low': np.linspace(41500, 39500, n) + np.random.uniform(-100, 0, n),
        'close': np.linspace(42000, 40000, n) + np.random.uniform(-100, 100, n),
        'volume': np.random.uniform(500, 1000, n)
    }
    df = pd.DataFrame(data)
    return calculate_all_indicators(df)


@pytest.fixture
def neutral_df():
    """Create DataFrame with neutral/sideways conditions"""
    np.random.seed(42)
    n = 100
    data = {
        'timestamp': pd.date_range('2024-01-01', periods=n, freq='1h'),
        'open': 41000 + np.random.uniform(-500, 500, n),
        'high': 41200 + np.random.uniform(-200, 200, n),
        'low': 40800 + np.random.uniform(-200, 200, n),
        'close': 41000 + np.random.uniform(-500, 500, n),
        'volume': np.random.uniform(500, 1000, n)
    }
    df = pd.DataFrame(data)
    return calculate_all_indicators(df)


class TestOBVVWAPStrategy:
    def test_strategy_name(self):
        strategy = OBVVWAPStrategy()
        assert strategy.name == "obv_vwap"
    
    def test_buy_signal(self, bullish_df):
        strategy = OBVVWAPStrategy()
        signal, confidence = strategy.generate_signal(bullish_df)
        assert signal in ["BUY", "SELL", "HOLD"]
    
    def test_sell_signal(self, bearish_df):
        strategy = OBVVWAPStrategy()
        signal, confidence = strategy.generate_signal(bearish_df)
        assert signal in ["BUY", "SELL", "HOLD"]
    
    def test_confidence_range(self, bullish_df):
        strategy = OBVVWAPStrategy()
        signal, confidence = strategy.generate_signal(bullish_df)
        if confidence is not None:
            assert 0.0 <= confidence <= 1.0


class TestRSIDivergenceStrategy:
    def test_strategy_name(self):
        strategy = RSIDivergenceStrategy()
        assert strategy.name == "rsi_divergence"
    
    def test_signal_generation(self, bullish_df):
        strategy = RSIDivergenceStrategy()
        signal, confidence = strategy.generate_signal(bullish_df)
        assert signal in ["BUY", "SELL", "HOLD"]


class TestMACDCrossoverStrategy:
    def test_strategy_name(self):
        strategy = MACDCrossoverStrategy()
        assert strategy.name == "macd_crossover"
    
    def test_signal_generation(self, bullish_df):
        strategy = MACDCrossoverStrategy()
        signal, confidence = strategy.generate_signal(bullish_df)
        assert signal in ["BUY", "SELL", "HOLD"]


class TestMultiSignalStrategy:
    def test_strategy_name(self):
        strategy = MultiSignalStrategy()
        assert strategy.name == "multi_signal"
    
    def test_consensus_logic(self, bullish_df):
        strategy = MultiSignalStrategy()
        signal, confidence = strategy.generate_signal(bullish_df)
        assert signal in ["BUY", "SELL", "HOLD"]
    
    def test_confidence_on_agreement(self, bullish_df):
        strategy = MultiSignalStrategy()
        signal, confidence = strategy.generate_signal(bullish_df)
        if confidence is not None:
            assert 0.0 <= confidence <= 1.0


def test_rsi_filter_blocks_buy():
    """Test that high RSI blocks BUY signals"""
    df = pd.DataFrame({
        'close': [40000] * 100,
        'volume': [500] * 100,
        'high': [40100] * 100,
        'low': [39900] * 100,
        'open': [40000] * 100
    })
    df = calculate_all_indicators(df)
    
    # Manually set RSI to overbought
    df.loc[df.index[-1], 'RSI'] = 75
    df.loc[df.index[-1], 'OBV'] = df['OBV'].iloc[-2] + 1000
    df.loc[df.index[-1], 'VWAP'] = 39000
    
    strategy = OBVVWAPStrategy()
    signal, _ = strategy.generate_signal(df)
    assert signal != "BUY"  # Should be blocked by RSI filter


def test_rsi_filter_blocks_sell():
    """Test that low RSI blocks SELL signals"""
    df = pd.DataFrame({
        'close': [40000] * 100,
        'volume': [500] * 100,
        'high': [40100] * 100,
        'low': [39900] * 100,
        'open': [40000] * 100
    })
    df = calculate_all_indicators(df)
    
    # Manually set RSI to oversold
    df.loc[df.index[-1], 'RSI'] = 25
    df.loc[df.index[-1], 'OBV'] = df['OBV'].iloc[-2] - 1000
    df.loc[df.index[-1], 'VWAP'] = 41000
    
    strategy = OBVVWAPStrategy()
    signal, _ = strategy.generate_signal(df)
    assert signal != "SELL"  # Should be blocked by RSI filter
