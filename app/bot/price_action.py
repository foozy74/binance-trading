"""
Indikatorfreie Price-Action-Methode (strategy/Strategiepapier_ ... Price-Action-Handelsmethode.md) – nur Backtest.

1. Marktstruktur: Ausbruch per Schlusskurs über das letzte Swing-Hoch -> Uptrend, das tiefste Tief der Korrektur
   davor wird valides Tief (Abwärtstrend gespiegelt). Schluss unter dem validen Tief dreht den Trend.
2. Zone: die Kerze mit dem Korrekturextrem (direkt vor dem Impuls), High bis Low. Limit-Einstieg am Zonenrand,
   Stop knapp jenseits der Zone, Ziel am jüngsten Extrem seit der Zone.
3. Filter: nur wenn CRV = Ziel / Risiko streng größer als min_crv (Papier: 2,5).

Mechanisierung (im Papier offen gelassen): Swing-Hoch/-Tief = Extrem über k Kerzen links und rechts, erst nach
k weiteren Kerzen bekannt; jede Zone wird höchstens einmal gehandelt; Ausstieg nur über Stop oder Ziel.

Aufruf: python -m app.bot.price_action --symbol BTC/USDC:USDC --timeframe 1h --candles 5000
"""
import argparse
from itertools import product
from typing import Dict, List, NamedTuple, Optional, Tuple

import pandas as pd

from app.bot.backtest import TAKER_FEE, WINDOW, buy_and_hold, fetch_candles, stop_exit_price
from app.bot.walk_forward import make_folds

STOP_BUFFER = 0.0005  # "knapp außerhalb" der Zone
Params = Tuple[int, float]  # (k, min_crv)
GRID: List[Params] = list(product([2, 3, 5], [2.5, 3.0, 4.0]))


class Order(NamedTuple):
    """Limit-Order für die nächste Kerze"""
    direction: int  # 1 = Long, -1 = Short
    entry: float
    stop: float
    target: float
    zone: int  # Index der Zonen-Kerze


class _Structure:
    """Marktstruktur Kerze für Kerze; nutzt in update(t) nur Kerzen bis t"""

    def __init__(self, candles: pd.DataFrame, k: int):
        self.high, self.low, self.close = (candles[c].to_numpy(float) for c in ("high", "low", "close"))
        self.k = k
        self.trend = 0
        self.swing_high: Optional[Tuple[int, float]] = None  # noch nicht durchbrochen
        self.swing_low: Optional[Tuple[int, float]] = None
        self.valid: Optional[Tuple[int, float]] = None  # valides Tief (Uptrend) bzw. Hoch (Downtrend)
        self.zone: Optional[int] = None

    def _register_pivots(self, t: int) -> None:
        """Pivot bei i = t - k ist erst jetzt bestätigt (k Kerzen rechts davon bekannt)"""
        i, k, h, lo = t - self.k, self.k, self.high, self.low
        if i < k:
            return
        if h[i] > h[i - k:i].max() and h[i] >= h[i + 1:t + 1].max():
            self.swing_high = (i, h[i])
        if lo[i] < lo[i - k:i].min() and lo[i] <= lo[i + 1:t + 1].min():
            self.swing_low = (i, lo[i])

    def _impulse(self, t: int, direction: int, since: int) -> None:
        """Ausbruch: Korrekturextrem seit since wird valider Punkt und Zone; alte Swings sind verbraucht"""
        seg = self.low[since:t + 1] if direction > 0 else -self.high[since:t + 1]
        self.zone = since + int(seg.argmin())
        self.valid = (self.zone, abs(seg.min()))
        self.trend, self.swing_high, self.swing_low = direction, None, None

    def update(self, t: int) -> None:
        self._register_pivots(t)
        close = self.close[t]
        if self.trend == 1 and close < self.valid[1]:
            self._impulse(t, -1, self.valid[0])
        elif self.trend == -1 and close > self.valid[1]:
            self._impulse(t, 1, self.valid[0])
        elif self.trend >= 0 and self.swing_high and close > self.swing_high[1]:
            self._impulse(t, 1, self.swing_high[0])
        elif self.trend <= 0 and self.swing_low and close < self.swing_low[1]:
            self._impulse(t, -1, self.swing_low[0])

    def order(self, t: int, min_crv: float) -> Optional[Order]:
        """Order an der aktuellen Zone, falls CRV > min_crv"""
        if not self.trend:
            return None
        z, d = self.zone, self.trend
        if d > 0:
            entry, stop, target = self.high[z], self.low[z] * (1 - STOP_BUFFER), self.high[z:t + 1].max()
        else:
            entry, stop, target = self.low[z], self.high[z] * (1 + STOP_BUFFER), self.low[z:t + 1].min()
        risk, reward = d * (entry - stop), d * (target - entry)
        if risk <= 0 or reward <= min_crv * risk:
            return None
        return Order(d, float(entry), float(stop), float(target), z)


def build_orders(candles: pd.DataFrame, k: int = 2, min_crv: float = 2.5) -> List[Optional[Order]]:
    """Je Kerze t die Order, die ab Kerze t+1 im Markt liegt (None = keine)"""
    structure = _Structure(candles, k)
    orders = []
    for t in range(len(candles)):
        structure.update(t)
        orders.append(structure.order(t, min_crv))
    return orders


def _fill_price(bar: Dict, order: Order) -> Optional[float]:
    """Limit am Zonenrand gefüllt, wenn die Kerze ihn erreicht; öffnet sie schon jenseits -> Open (besserer Preis)"""
    if order.direction > 0:
        return min(bar['open'], order.entry) if bar['low'] <= order.entry else None
    return max(bar['open'], order.entry) if bar['high'] >= order.entry else None


def simulate_orders(candles: pd.DataFrame, orders: List[Optional[Order]], fee: float = TAKER_FEE) -> Dict:
    """Simuliert Limit-Einstiege mit Stop/Ziel je Trade (1x, volles Kapital); Kennzahlen wie backtest.simulate.
    shortcut: Taker-Gebühr auch für Limit-Einstieg und Ziel (konservativ), Maker wäre 0.015 %."""
    equity, peak, max_dd = 1.0, 1.0, 0.0
    pos: Optional[Order] = None
    entry, used, returns = 0.0, set(), []

    def close(price: float) -> None:
        nonlocal equity, pos
        returns.append(pos.direction * (price / entry - 1))
        equity *= (1 + returns[-1]) * (1 - fee)
        pos = None

    bars = candles.to_dict('records')
    for t, bar in enumerate(bars):
        if pos is not None:
            # Stop/Ziel als Anteil vom tatsächlichen Füllpreis, wie stop_exit_price sie erwartet
            sl = pos.direction * (entry - pos.stop) / entry
            tp = pos.direction * (pos.target - entry) / entry
            exit_price = stop_exit_price(bar, pos.direction, entry, sl, tp)
            if exit_price is not None:
                close(exit_price)
        elif t > 0 and orders[t - 1] and orders[t - 1].zone not in used:
            fill = _fill_price(bar, orders[t - 1])
            if fill is not None:
                pos, entry = orders[t - 1], fill
                used.add(pos.zone)
                equity *= 1 - fee
                # Reihenfolge in der Füll-Kerze unbekannt -> nur der Stop zählt (konservativ)
                if pos.direction * ((bar['low'] if pos.direction > 0 else bar['high']) - pos.stop) <= 0:
                    close(min(fill, pos.stop) if pos.direction > 0 else max(fill, pos.stop))
        marked = equity * (1 + pos.direction * (bar['close'] / entry - 1)) if pos else equity
        peak = max(peak, marked)
        max_dd = min(max_dd, marked / peak - 1)
    if pos is not None:
        close(bars[-1]['close'])
    return {"trades": len(returns), "wins": sum(r > 0 for r in returns),
            "total_return": equity - 1, "max_drawdown": max_dd}


def walk_forward_orders(candles: pd.DataFrame, grid: List[Params], start: int, train: int, test: int,
                        fee: float) -> Dict:
    """Je Fold (k, min_crv) mit der besten Trainingsrendite wählen, nur Testfenster zählen.
    fixed = jede Parameterkombination unverändert über alle Testfenster (ohne Auswahl)."""
    orders = {p: build_orders(candles, *p) for p in grid}

    def score(p: Params, a: int, b: int) -> float:
        return simulate_orders(candles.iloc[a:b].reset_index(drop=True), orders[p][a:b], fee)["total_return"]

    oos, chosen, fixed = 1.0, [], {p: 1.0 for p in grid}
    for train_start, test_start, test_end in make_folds(len(candles), start, train, test):
        chosen.append(max(grid, key=lambda p: score(p, train_start, test_start)))
        oos *= 1 + score(chosen[-1], test_start, test_end)
        for p in grid:
            fixed[p] *= 1 + score(p, test_start, test_end)
    return {"oos_return": oos - 1, "chosen": chosen, "fixed": {p: r - 1 for p, r in fixed.items()}}


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest + Walk-Forward der Price-Action-Methode")
    parser.add_argument("--symbol", default="BTC/USDC:USDC")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--candles", type=int, default=5000)
    parser.add_argument("--train", type=int, default=2000)
    parser.add_argument("--test", type=int, default=500)
    parser.add_argument("--fee", type=float, default=TAKER_FEE)
    args = parser.parse_args()

    candles = fetch_candles(args.symbol, args.timeframe, args.candles)
    print(f"📈 {len(candles)} Kerzen {args.symbol} {args.timeframe}: {candles['timestamp'].iloc[0]} – "
          f"{candles['timestamp'].iloc[-1]}, Buy & Hold {buy_and_hold(candles):+.2%}")
    for k, min_crv in GRID:
        r = simulate_orders(candles, build_orders(candles, k, min_crv), args.fee)
        win_rate = r["wins"] / r["trades"] if r["trades"] else 0
        print(f"k={k} CRV>{min_crv:<4} Rendite {r['total_return']:+8.2%}  Max-DD {r['max_drawdown']:8.2%}  "
              f"Trades {r['trades']:4}  Trefferquote {win_rate:.0%}")
    folds = make_folds(len(candles), WINDOW, args.train, args.test)
    if not folds:
        raise SystemExit("⛔ Zu wenige Kerzen für Train + Test")
    hold = candles['close'].iloc[folds[-1][2] - 1] / candles['open'].iloc[folds[0][1]] - 1
    r = walk_forward_orders(candles, GRID, WINDOW, args.train, args.test, args.fee)
    print(f"📊 Walk-Forward {len(folds)} Folds, Out-of-Sample (Buy & Hold {hold:+.2%}):")
    fixed = "  ".join(f"k{k}/CRV{c:g} {ret:+.1%}" for (k, c), ret in r["fixed"].items())
    print(f"  fest:    {fixed}")
    print(f"  rollend: {r['oos_return']:+.2%}  Gewählt: {', '.join(f'k{k}/CRV{c:g}' for k, c in r['chosen'])}")


if __name__ == "__main__":
    main()
