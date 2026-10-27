from app.bot.strategies.base import BaseStrategy
import pandas as pd
from typing import Tuple, Optional


class RSIDivergenceStrategy(BaseStrategy):
    """
    RSI Divergence Strategy
    Detects bullish/bearish divergences between price and RSI
    """
    
    @property
    def name(self) -> str:
        return "rsi_divergence"
    
    def generate_signal(self, df: pd.DataFrame) -> Tuple[str, Optional[float]]:
        if len(df) < 5:
            return "HOLD", None
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Bullish divergence: Price makes lower low, RSI makes higher low
        if self._detect_bullish_divergence(df):
            if last["RSI"] < 40:  # Still in oversold territory
                return "BUY", 0.7
        
        # Bearish divergence: Price makes higher high, RSI makes lower high
        if self._detect_bearish_divergence(df):
            if last["RSI"] > 60:  # Still in overbought territory
                return "SELL", 0.7
        
        # RSI reversal from extreme levels
        if prev["RSI"] < 30 and last["RSI"] >= 30:
            return "BUY", 0.6
        elif prev["RSI"] > 70 and last["RSI"] <= 70:
            return "SELL", 0.6
        
        return "HOLD", None
    
    def _detect_bullish_divergence(self, df: pd.DataFrame) -> bool:
        """Detect bullish divergence over last 5 candles"""
        if len(df) < 5:
            return False
        
        recent = df.tail(5)
        price_lows = recent['low'].values
        rsi_lows = recent['RSI'].values
        
        # Check if price made lower low while RSI made higher low
        if price_lows[-1] < price_lows[:-1].min():
            if rsi_lows[-1] > rsi_lows[:-1].min():
                return True
        return False
    
    def _detect_bearish_divergence(self, df: pd.DataFrame) -> bool:
        """Detect bearish divergence over last 5 candles"""
        if len(df) < 5:
            return False
        
        recent = df.tail(5)
        price_highs = recent['high'].values
        rsi_highs = recent['RSI'].values
        
        # Check if price made higher high while RSI made lower high
        if price_highs[-1] > price_highs[:-1].max():
            if rsi_highs[-1] < rsi_highs[:-1].max():
                return True
        return False
        
        recent = df.tail(5)
        price_lows = recent['low'].values
        rsi_lows = recent['RSI'].values
        
        # Check if price made lower low while RSI made higher low
        if price_lows[-1] < price_lows[:-1].min():
            if rsi_lows[-1] > rsi_lows[:-1].min():
                return True
        return False
    
    def _detect_bearish_divergence(self, df: pd.DataFrame) -> bool:
        """Detect bearish divergence over last 5 candles"""
        if len(df) < 5:
            return False
        
        recent = df.tail(5)
        price_highs = recent['high'].values
        rsi_highs = recent['RSI'].values
        
        # Check if price made higher high while RSI made lower high
        if price_highs[-1] > price_highs[:-1].max():
            if rsi_highs[-1] < rsi_highs[:-1].max():
                return True
        return False
