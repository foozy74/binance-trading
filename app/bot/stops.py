"""
Stop-Loss/Take-Profit-Berechnung, gemeinsam für Backtest und Live-Bot.

Fest in Prozent (TRAILING_STOP_PERCENT/TAKE_PROFIT_PERCENT) oder ATR-basiert:
Abstand = STOP_ATR_MULTIPLE x ATR der Signal-Kerze, TP optional als Vielfaches davon (TAKE_PROFIT_R).
"""
from typing import Dict, NamedTuple, Optional, Tuple, Union

from app.config import settings


class AtrStop(NamedTuple):
    """Stop im Abstand multiple x ATR der Signal-Kerze; TP optional als Vielfaches dieses Abstands (R)"""
    multiple: float
    take_profit_r: Optional[float] = None


StopLoss = Union[None, float, AtrStop]


def trade_stops(stop_loss: StopLoss, take_profit: Optional[float], signal_bar: Dict,
                entry: float) -> Tuple[Optional[float], Optional[float]]:
    """SL/TP als Anteil vom Einstieg; ATR-Stops werden beim Einstieg aus der Signal-Kerze umgerechnet"""
    if not isinstance(stop_loss, AtrStop):
        return stop_loss, take_profit
    atr = signal_bar.get('ATR') or 0
    if not atr > 0:  # ATR noch nicht berechenbar (Anlaufphase) -> Trade ohne Stop
        return None, None
    distance = stop_loss.multiple * atr / entry
    return distance, distance * stop_loss.take_profit_r if stop_loss.take_profit_r else None


def configured_stop() -> Tuple[StopLoss, Optional[float]]:
    """Stop-Konfiguration aus den Settings; STOP_ATR_MULTIPLE 0 = feste Prozent-Stops, TP 0 = aus"""
    if settings.STOP_ATR_MULTIPLE > 0:
        return AtrStop(settings.STOP_ATR_MULTIPLE, settings.TAKE_PROFIT_R or None), None
    return settings.TRAILING_STOP_PERCENT, settings.TAKE_PROFIT_PERCENT or None


def stop_prices(side: str, entry: float, signal_bar: Dict) -> Dict[str, float]:
    """Trigger-Preise für eine neue Position; nur gesetzte Stops sind enthalten"""
    direction = 1 if side.lower() == 'buy' else -1
    sl, tp = trade_stops(*configured_stop(), signal_bar, entry)
    prices = {}
    if sl:
        prices['stopLossPrice'] = entry * (1 - direction * sl)
    if tp:
        prices['takeProfitPrice'] = entry * (1 + direction * tp)
    return prices
