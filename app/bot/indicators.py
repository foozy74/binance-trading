import pandas as pd
import numpy as np
import ta
from typing import Dict, Optional


def calculate_obv(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate On-Balance Volume"""
    df['price_change'] = df['close'].diff()
    df['direction'] = np.where(df['price_change'] > 0, 1, np.where(df['price_change'] < 0, -1, 0))
    df['OBV'] = (df['direction'] * df['volume']).cumsum()
    return df


def calculate_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate Volume Weighted Average Price"""
    df['cumulative_vol'] = df['volume'].cumsum()
    df['cumulative_vp'] = (df['close'] * df['volume']).cumsum()
    df['VWAP'] = df['cumulative_vp'] / df['cumulative_vol']
    return df


def calculate_rsi(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """Calculate RSI"""
    df["RSI"] = ta.momentum.RSIIndicator(df["close"], window=window).rsi()
    return df


def calculate_bollinger(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Calculate Bollinger Bands"""
    bollinger = ta.volatility.BollingerBands(df["close"], window=window)
    df["Bollinger_Upper"] = bollinger.bollinger_hband()
    df["Bollinger_Lower"] = bollinger.bollinger_lband()
    df["Bollinger_Middle"] = bollinger.bollinger_mavg()
    return df


def calculate_ema(df: pd.DataFrame, span: int = 20) -> pd.DataFrame:
    """Calculate Exponential Moving Average"""
    df["EMA_20"] = df["close"].ewm(span=span).mean()
    return df


def calculate_macd(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate MACD"""
    df["MACD"] = ta.trend.MACD(df["close"]).macd()
    df["MACD_Signal"] = ta.trend.MACD(df["close"]).macd_signal()
    df["MACD_Hist"] = ta.trend.MACD(df["close"]).macd_diff()
    return df


def calculate_stochastic(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """Calculate Stochastic Oscillator"""
    stoch = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"], window=window)
    df["Stoch_K"] = stoch.stoch()
    df["Stoch_D"] = stoch.stoch_signal()
    return df


def calculate_adx(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """Calculate Average Directional Index"""
    df["ADX"] = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=window).adx()
    return df


def calculate_mfi(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """Calculate Money Flow Index"""
    df["MFI"] = ta.volume.MFIIndicator(df["high"], df["low"], df["close"], df["volume"], window=window).money_flow_index()
    return df


def calculate_atr(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """Calculate Average True Range"""
    df["ATR"] = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=window).average_true_range()
    return df


def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all technical indicators"""
    df = calculate_obv(df)
    df = calculate_vwap(df)
    df = calculate_rsi(df)
    df = calculate_bollinger(df)
    df = calculate_ema(df)
    df = calculate_macd(df)
    df = calculate_stochastic(df)
    df = calculate_adx(df)
    df = calculate_mfi(df)
    df = calculate_atr(df)
    return df
