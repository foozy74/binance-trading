from typing import Tuple

import ccxt

from app.config import settings


def create_exchange() -> ccxt.Exchange:
    """Erzeugt den ccxt-Client für die konfigurierte Börse (EXCHANGE)"""
    if settings.EXCHANGE == "hyperliquid":
        return ccxt.hyperliquid({
            'walletAddress': settings.HYPERLIQUID_WALLET_ADDRESS,
            'privateKey': settings.HYPERLIQUID_PRIVATE_KEY,
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })
    return ccxt.binance({
        'apiKey': settings.BINANCE_API_KEY,
        'secret': settings.BINANCE_API_SECRET,
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })


def symbol_assets(symbol: str) -> Tuple[str, str]:
    """Liefert (Base, Quote) aus einem ccxt-Symbol, z.B. 'BTC/USDC:USDC' -> ('BTC', 'USDC')"""
    base, rest = symbol.split("/")
    return base, rest.split(":")[0]
