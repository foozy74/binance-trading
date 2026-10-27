from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple
import pandas as pd


class BaseStrategy(ABC):
    """Abstract base class for trading strategies"""
    
    @abstractmethod
    def generate_signal(self, df: pd.DataFrame) -> Tuple[str, Optional[float]]:
        """
        Generate trading signal based on indicators
        
        Returns:
            Tuple of (signal, confidence)
            signal: "BUY", "SELL", or "HOLD"
            confidence: 0.0 to 1.0 (optional)
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return strategy name"""
        pass
