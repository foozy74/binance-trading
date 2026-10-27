import pandas as pd
from typing import List

from app.config import settings
from app.bot.indicators import calculate_all_indicators
from app.services.exchange import create_exchange


def fetch_market_data() -> pd.DataFrame:
    """Fetch OHLCV data from Binance and calculate all indicators"""
    exchange = create_exchange()
    
    ohlcv = exchange.fetch_ohlcv(settings.SYMBOL, timeframe='1h', limit=101)
    # Letzte Kerze ist noch offen – nur abgeschlossene Kerzen auswerten
    df = pd.DataFrame(ohlcv[:-1], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    df = calculate_all_indicators(df)
    
    return df


def volume_ratio(candles: pd.DataFrame, window: int = 20) -> pd.Series:
    """Volumen je Kerze relativ zum Durchschnitt der letzten window Kerzen (0 solange zu wenig Daten)"""
    return (candles['volume'] / candles['volume'].rolling(window).mean()).fillna(0)


def apply_volume_filter(candles: pd.DataFrame, signals: List[str], factor: float, window: int = 20) -> List[str]:
    """Signale nur behalten, wenn Volumen >= factor x Durchschnitt (factor 0 = Filter aus)"""
    if not factor:
        return list(signals)
    ratio = volume_ratio(candles, window).tolist()
    return [s if s == "HOLD" or ratio[i] >= factor else "HOLD" for i, s in enumerate(signals)]
