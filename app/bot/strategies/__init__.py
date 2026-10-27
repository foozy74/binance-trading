from app.bot.strategies.base import BaseStrategy
from app.bot.strategies.obv_vwap import OBVVWAPStrategy
from app.bot.strategies.rsi_divergence import RSIDivergenceStrategy
from app.bot.strategies.macd_crossover import MACDCrossoverStrategy
from app.bot.strategies.multi_signal import MultiSignalStrategy
from typing import Dict, Type


STRATEGIES: Dict[str, Type[BaseStrategy]] = {
    "obv_vwap": OBVVWAPStrategy,
    "rsi_divergence": RSIDivergenceStrategy,
    "macd_crossover": MACDCrossoverStrategy,
    "multi_signal": MultiSignalStrategy,
}


def get_strategy(name: str) -> BaseStrategy:
    """Get strategy instance by name"""
    strategy_class = STRATEGIES.get(name)
    if not strategy_class:
        raise ValueError(f"Unknown strategy: {name}. Available: {list(STRATEGIES.keys())}")
    return strategy_class()


def list_strategies() -> list:
    """List available strategy names"""
    return list(STRATEGIES.keys())
