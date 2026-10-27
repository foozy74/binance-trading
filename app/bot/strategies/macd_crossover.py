from app.bot.strategies.base import BaseStrategy
import pandas as pd
from typing import Tuple, Optional


class MACDCrossoverStrategy(BaseStrategy):
    """
    MACD Crossover Strategy
    Generates signals on MACD line crossing signal line
    """
    
    @property
    def name(self) -> str:
        return "macd_crossover"
    
    def generate_signal(self, df: pd.DataFrame) -> Tuple[str, Optional[float]]:
        if len(df) < 2:
            return "HOLD", None
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Bullish crossover: MACD crosses above signal line
        if prev["MACD"] <= prev["MACD_Signal"] and last["MACD"] > last["MACD_Signal"]:
            confidence = self._calculate_confidence(df, "BUY")
            return "BUY", confidence
        
        # Bearish crossover: MACD crosses below signal line
        if prev["MACD"] >= prev["MACD_Signal"] and last["MACD"] < last["MACD_Signal"]:
            confidence = self._calculate_confidence(df, "SELL")
            return "SELL", confidence
        
        # Check for zero line crossover
        if prev["MACD"] <= 0 and last["MACD"] > 0:
            return "BUY", 0.8
        elif prev["MACD"] >= 0 and last["MACD"] < 0:
            return "SELL", 0.8
        
        return "HOLD", None
    
    def _calculate_confidence(self, df: pd.DataFrame, signal: str) -> float:
        """Calculate confidence based on MACD histogram and trend"""
        confidence = 0.5
        last = df.iloc[-1]
        
        # Higher confidence with stronger histogram
        hist_strength = abs(last["MACD_Hist"]) / abs(last["MACD"]) if last["MACD"] != 0 else 0
        confidence += min(hist_strength * 0.2, 0.2)
        
        # ADX filter for trend strength
        if last.get("ADX", 0) > 25:
            confidence += 0.15
        elif last.get("ADX", 0) > 20:
            confidence += 0.1
        
        # Volume confirmation
        if last.get("OBV", 0) > df['OBV'].iloc[-5:].mean():
            confidence += 0.1 if signal == "BUY" else 0
        
        return min(confidence, 1.0)
