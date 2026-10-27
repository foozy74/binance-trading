"""
Walk-Forward-Bewertung von Filtern und Parametern.

Je Fold: Parameter (Volumen-Filter, SL/TP, Funding-Filter) – und bei Stufe 2 auch die Strategie – auf dem
Trainingsfenster wählen, dann unverändert
auf dem direkt folgenden Testfenster anwenden. Nur die Testfenster zählen (Out-of-Sample).
"fest" = Wahl aus Fold 1 für alle Testfenster beibehalten – zeigt, ob das Neu-Wählen überhaupt hilft.

Aufruf: python -m app.bot.walk_forward --symbol BTC/USDC:USDC --train 2000 --test 500
"""
import argparse
from itertools import product
from typing import Dict, List, Optional, Tuple

import pandas as pd

from app.bot.funding import apply_funding_filter, fetch_funding_history, funding_signals, funding_values
from app.bot.signals import apply_volume_filter
from app.bot.backtest import TAKER_FEE, WINDOW, AtrStop, fetch_candles, generate_signals, simulate
from app.bot.indicators import calculate_atr
from app.bot.strategies import STRATEGIES

Params = Tuple[float, Optional[float], Optional[float], Optional[float]]  # (Volumen-Faktor, SL, TP, Funding-Filter)

VOLUME_FACTORS = [0, 1.0, 1.5, 2.0]
STOPS = [(None, None), (0.02, 0.05), (0.03, 0.06), (0.05, 0.10)]
FUNDING_FILTERS = [None, 0.0, 0.3]
GRID: List[Params] = [(k, sl, tp, f) for k, (sl, tp), f in product(VOLUME_FACTORS, STOPS, FUNDING_FILTERS)]
GRID_NO_FUNDING: List[Params] = [p for p in GRID if p[3] is None]
BASELINE: Params = (0, None, None, None)
PCT_STOPS = STOPS[1:]
ATR_STOPS = [(AtrStop(k, r), None) for k, r in product([1.5, 2.0, 3.0], [None, 2.0])]
FUNDING_STRATEGIES = {"funding_0.3": 0.3, "funding_0.0": 0.0}  # Funding als eigenständiges Signal


def make_folds(total: int, start: int, train: int, test: int) -> List[Tuple[int, int, int]]:
    """(Train-Start, Test-Start, Test-Ende) – Testfenster lückenlos und überlappungsfrei"""
    return [(s, s + train, s + train + test) for s in range(start, total - train - test + 1, test)]


def _run(candles: pd.DataFrame, signals: List[str], params: Params, a: int, b: int, fee: float) -> Dict:
    factor, stop_loss, take_profit, funding = params
    filtered = apply_funding_filter(candles, apply_volume_filter(candles, signals, factor), funding)
    return simulate(candles.iloc[a:b].reset_index(drop=True), filtered[a:b], fee, stop_loss, take_profit)


Candidate = Tuple[str, Params]  # (Strategie, Parameter)


def _select_and_test(candles: pd.DataFrame, signals: Dict[str, List[str]], candidates: List[Candidate],
                     start: int, train: int, test: int, fee: float) -> Dict:
    """Je Fold besten Kandidaten im Training wählen und im Test anwenden.
    oos_return = rollende Neu-Auswahl (Stufe 1/2), fixed_return = Wahl aus Fold 1 bleibt fest."""
    oos, fixed, chosen = 1.0, 1.0, []

    def score(candidate: Candidate, a: int, b: int) -> float:
        name, params = candidate
        return _run(candles, signals[name], params, a, b, fee)["total_return"]

    for train_start, test_start, test_end in make_folds(len(candles), start, train, test):
        chosen.append(max(candidates, key=lambda c: score(c, train_start, test_start)))
        oos *= 1 + score(chosen[-1], test_start, test_end)
        fixed *= 1 + score(chosen[0], test_start, test_end)
    return {"oos_return": oos - 1, "fixed_return": fixed - 1, "chosen": chosen}


def walk_forward(candles: pd.DataFrame, signals: List[str], grid: List[Params],
                 start: int, train: int, test: int, fee: float) -> Dict:
    """Stufe 1: Parameter einer Strategie je Fold neu wählen; Basis = ohne Filter/SL"""
    result = _select_and_test(candles, {"s": signals}, [("s", p) for p in grid], start, train, test, fee)
    baseline = _select_and_test(candles, {"s": signals}, [("s", BASELINE)], start, train, test, fee)
    return {**result, "chosen": [p for _, p in result["chosen"]], "baseline_return": baseline["oos_return"]}


def select_strategy(candles: pd.DataFrame, signals: Dict[str, List[str]], grid: List[Params],
                    start: int, train: int, test: int, fee: float) -> Dict:
    """Stufe 2: Strategie und Parameter je Fold gemeinsam neu wählen"""
    candidates = [(name, params) for name in signals for params in grid]
    return _select_and_test(candles, signals, candidates, start, train, test, fee)


def _fmt(params: Params) -> str:
    factor, stop_loss, take_profit, funding = params
    if isinstance(stop_loss, AtrStop):
        stops = f"ATR{stop_loss.multiple:g}" + (f"/TP{stop_loss.take_profit_r:g}R" if stop_loss.take_profit_r else "")
    else:
        stops = f"SL{stop_loss:.0%}/TP{take_profit:.0%}" if stop_loss else "ohneSL"
    return f"V{factor:g}x {stops}" + (f" F{funding:g}" if funding is not None else "")


def compare_stops(candles: pd.DataFrame, all_signals: Dict[str, List[str]],
                  train: int, test: int, fee: float) -> None:
    """Feste Prozent-Stops gegen ATR-Stops: einzeln fest (ohne Auswahl) und per Walk-Forward gewählt"""
    variants = [(None, None)] + PCT_STOPS + ATR_STOPS
    grids = {
        "WF Prozent": [(k, sl, tp, None) for k, (sl, tp) in product(VOLUME_FACTORS, [(None, None)] + PCT_STOPS)],
        "WF ATR": [(k, sl, tp, None) for k, (sl, tp) in product(VOLUME_FACTORS, [(None, None)] + ATR_STOPS)],
    }
    for name, signals in all_signals.items():
        fixed = {
            _fmt((0, sl, tp, None))[4:]: _select_and_test(candles, {"s": signals}, [("s", (0, sl, tp, None))],
                                                         WINDOW, train, test, fee)["oos_return"]
            for sl, tp in variants
        }
        chosen = {label: walk_forward(candles, signals, grid, WINDOW, train, test, fee)["oos_return"]
                  for label, grid in grids.items()}
        print(f"  {name}")
        print("    fest:  " + "  ".join(f"{label} {ret:+.1%}" for label, ret in fixed.items()))
        print("    WF:    " + "  ".join(f"{label} {ret:+.1%}" for label, ret in chosen.items()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-Forward-Test aller Strategien auf Hyperliquid-Kerzen")
    parser.add_argument("--symbol", default="BTC/USDC:USDC")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--candles", type=int, default=5000)
    parser.add_argument("--train", type=int, default=2000)
    parser.add_argument("--test", type=int, default=500)
    parser.add_argument("--fee", type=float, default=TAKER_FEE)
    parser.add_argument("--compare-stops", action="store_true", help="Prozent- gegen ATR-Stops vergleichen")
    args = parser.parse_args()

    candles = fetch_candles(args.symbol, args.timeframe, args.candles)
    folds = make_folds(len(candles), WINDOW, args.train, args.test)
    if not folds:
        raise SystemExit("⛔ Zu wenige Kerzen für Train + Test")
    test_start, test_end = folds[0][1], folds[-1][2]
    hold = candles['close'].iloc[test_end - 1] / candles['open'].iloc[test_start] - 1
    print(f"📈 {args.symbol} {args.timeframe}: {len(folds)} Folds, Out-of-Sample "
          f"{candles['timestamp'].iloc[test_start]} – {candles['timestamp'].iloc[test_end - 1]}")
    print(f"📌 Buy & Hold im Testzeitraum: {hold:+.2%}")
    # shortcut: Funding-Zeitachse setzt 1h-Kerzen voraus, bei anderen Timeframes funding_values anpassen
    first_ms = int(candles['timestamp'].iloc[0].value // 1_000_000)
    rates = fetch_funding_history(args.symbol, first_ms - 24 * 3_600_000, first_ms + len(candles) * 3_600_000)
    candles = calculate_atr(candles.assign(funding=funding_values(candles, rates)))
    print(f"📌 {len(rates)} Funding-Raten geladen")
    all_signals = generate_signals(candles, list(STRATEGIES))
    all_signals.update({name: funding_signals(candles, th) for name, th in FUNDING_STRATEGIES.items()})
    if args.compare_stops:
        compare_stops(candles, all_signals, args.train, args.test, args.fee)
        return
    print("Stufe 1 – Parameter je Strategie neu wählen:")
    for name, signals in all_signals.items():
        r = walk_forward(candles, signals, GRID, WINDOW, args.train, args.test, args.fee)
        no_funding = walk_forward(candles, signals, GRID_NO_FUNDING, WINDOW, args.train, args.test, args.fee)
        print(f"  {name:16} rollend {r['oos_return']:+8.2%}  ohne Funding-Filter {no_funding['oos_return']:+8.2%}  "
              f"fest {r['fixed_return']:+8.2%}  "
              f"Basis {r['baseline_return']:+8.2%}  Gewählt: {', '.join(_fmt(p) for p in r['chosen'])}")
    r = select_strategy(candles, all_signals, GRID, WINDOW, args.train, args.test, args.fee)
    print("Stufe 2 – Strategie + Parameter je Fold neu wählen:")
    print(f"  {'auto':16} rollend {r['oos_return']:+8.2%}  fest {r['fixed_return']:+8.2%}  "
          f"Gewählt: {', '.join(f'{n} {_fmt(p)}' for n, p in r['chosen'])}")


if __name__ == "__main__":
    main()
