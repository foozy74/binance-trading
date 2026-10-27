import pytest
import pandas as pd
import numpy as np
from app.bot.indicators import (
    calculate_obv, calculate_vwap, calculate_rsi,
    calculate_bollinger, calculate_macd, calculate_stochastic
)


@pytest.fixture
def sample_df():
    """Create sample OHLCV DataFrame for testing"""
    np.random.seed(42)
    n = 100
    data = {
        'timestamp': pd.date_range('2024-01-01', periods=n, freq='1h'),
        'open': np.random.uniform(40000, 45000, n),
        'high': np.random.uniform(45000, 46000, n),
        'low': np.random.uniform(39000, 40000, n),
        'close': np.random.uniform(40000, 45000, n),
        'volume': np.random.uniform(100, 1000, n)
    }
    return pd.DataFrame(data)


def test_obv_calculation(sample_df):
    """Test OBV calculation"""
    df = calculate_obv(sample_df.copy())
    
    assert 'OBV' in df.columns
    assert len(df) == len(sample_df)
    assert not df['OBV'].isna().any()
    assert df['OBV'].iloc[-1] != 0


def test_vwap_calculation(sample_df):
    """Test VWAP calculation"""
    df = calculate_vwap(sample_df.copy())
    
    assert 'VWAP' in df.columns
    assert len(df) == len(sample_df)
    assert not df['VWAP'].isna().any()
    assert (df['VWAP'] > 0).all()


def test_rsi_calculation(sample_df):
    """Test RSI calculation"""
    df = calculate_rsi(sample_df.copy())
    
    assert 'RSI' in df.columns
    assert len(df) == len(sample_df)
    assert df['RSI'].iloc[:13].isna().all()  # First 13 should be NaN (window=14)
    assert not df['RSI'].iloc[14:].isna().any()
    assert (df['RSI'].iloc[14:] >= 0).all()
    assert (df['RSI'].iloc[14:] <= 100).all()


def test_rsi_overbought_oversold():
    """Test RSI overbought/oversold detection"""
    df = pd.DataFrame({
        'close': [40000] * 20 + [41000] * 5 + [42000] * 5  # Rising prices
    })
    df = calculate_rsi(df)
    
    rsi_values = df['RSI'].iloc[14:]
    assert rsi_values.max() > 50  # Should have some high RSI values


def test_bollinger_bands_calculation(sample_df):
    """Test Bollinger Bands calculation"""
    df = calculate_bollinger(sample_df.copy())
    
    assert 'Bollinger_Upper' in df.columns
    assert 'Bollinger_Lower' in df.columns
    assert 'Bollinger_Middle' in df.columns
    # Check non-NaN values (first 19 rows have NaN due to window=20)
    valid = df.iloc[20:]
    assert (valid['Bollinger_Upper'] >= valid['Bollinger_Middle']).all()
    assert (valid['Bollinger_Lower'] <= valid['Bollinger_Middle']).all()


def test_macd_calculation(sample_df):
    """Test MACD calculation"""
    df = calculate_macd(sample_df.copy())
    
    assert 'MACD' in df.columns
    assert 'MACD_Signal' in df.columns
    assert 'MACD_Hist' in df.columns


def test_stochastic_calculation(sample_df):
    """Test Stochastic Oscillator calculation"""
    df = calculate_stochastic(sample_df.copy())
    
    assert 'Stoch_K' in df.columns
    assert 'Stoch_D' in df.columns
    # Check non-NaN values (first 13 rows have NaN due to window=14)
    valid = df.iloc[14:]
    assert (valid['Stoch_K'] >= 0).all()
    assert (valid['Stoch_K'] <= 100).all()
