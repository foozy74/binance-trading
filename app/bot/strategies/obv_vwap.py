from app.bot.strategies.base import BaseStrategy
import pandas as pd
from typing import Tuple, Optional


class OBVVWAPStrategy(BaseStrategy):
    """
    Original strategy: OBV + VWAP with RSI and Bollinger filters
    """
    
    @property
    def name(self) -> str:
        return "obv_vwap"
    
    def generate_signal(self, df: pd.DataFrame) -> Tuple[str, Optional[float]]:
        if len(df) < 2:
            return "HOLD", None
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # OBV & VWAP as main strategy
        if last['OBV'] > prev['OBV'] and last['close'] > last['VWAP']:
            signal = "BUY"
        elif last['OBV'] < prev['OBV'] and last['close'] < last['VWAP']:
            signal = "SELL"
        else:
            return "HOLD", None
        
        # RSI filter
        if last["RSI"] > 70 and signal == "BUY":
            return "HOLD", None
        elif last["RSI"] < 30 and signal == "SELL":
            return "HOLD", None
        
        # Bollinger Bands filter
        if last["close"] >= last["Bollinger_Upper"] and signal == "BUY":
            return "HOLD", None
        elif last["close"] <= last["Bollinger_Lower"] and signal == "SELL":
            return "HOLD", None
        
        # Calculate confidence based on indicator strength
        confidence = self._calculate_confidence(df, signal)
        return signal, confidence
    
    def _calculate_confidence(self, df: pd.DataFrame, signal: str) -> float:
        """Calculate confidence score based on multiple indicators"""
        confidence = 0.5
        last = df.iloc[-1]
        
        if signal == "BUY":
            if last['OBV'] > df['OBV'].iloc[-3:].mean():
                confidence += 0.1
            if last['close'] > last['VWAP'] * 1.001:
                confidence += 0.1
            if last['RSI'] < 50:
                confidence += 0.1
            if last['MACD_Hist'] > 0:
                confidence += 0.1
        else:  # SELL
            if last['OBV'] < df['OBV'].iloc[-3:].mean():
                confidence += 0.1
            if last['close'] < last['VWAP'] * 0.999:
                confidence += 0.1
            if last['RSI'] > 50:
                confidence += 0.1
            if last['MACD_Hist'] < 0:
                confidence += 0.1
        
        return min(confidence, 1.0)
