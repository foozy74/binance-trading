from app.bot.strategies.base import BaseStrategy
import pandas as pd
from typing import Tuple, Optional, List


class MultiSignalStrategy(BaseStrategy):
    """
    Multi-Signal Consensus Strategy
    Combines multiple strategies and requires consensus for signals
    """
    
    def __init__(self):
        from app.bot.strategies.obv_vwap import OBVVWAPStrategy
        from app.bot.strategies.rsi_divergence import RSIDivergenceStrategy
        from app.bot.strategies.macd_crossover import MACDCrossoverStrategy
        
        self.strategies = [
            OBVVWAPStrategy(),
            RSIDivergenceStrategy(),
            MACDCrossoverStrategy()
        ]
    
    @property
    def name(self) -> str:
        return "multi_signal"
    
    def generate_signal(self, df: pd.DataFrame) -> Tuple[str, Optional[float]]:
        if len(df) < 2:
            return "HOLD", None
        
        # Collect signals from all strategies
        signals: List[Tuple[str, Optional[float]]] = []
        for strategy in self.strategies:
            signal = strategy.generate_signal(df)
            signals.append(signal)
        
        # Count signal types
        buy_count = sum(1 for s, _ in signals if s == "BUY")
        sell_count = sum(1 for s, _ in signals if s == "SELL")
        hold_count = sum(1 for s, _ in signals if s == "HOLD")
        
        # Calculate average confidence for non-HOLD signals
        non_hold_signals = [(s, c) for s, c in signals if s != "HOLD" and c is not None]
        avg_confidence = sum(c for _, c in non_hold_signals) / len(non_hold_signals) if non_hold_signals else None
        
        # Require at least 2 out of 3 strategies to agree
        if buy_count >= 2:
            return "BUY", avg_confidence
        elif sell_count >= 2:
            return "SELL", avg_confidence
        
        # Strong signal from one strategy with high confidence
        for signal, confidence in signals:
            if signal != "HOLD" and confidence and confidence >= 0.8:
                return signal, confidence
        
        return "HOLD", None
