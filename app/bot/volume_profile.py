"""
Intraday-Strategie auf Basis des Volumenprofils (strategy/Systematisches Regelwerk_ ... Volumenprofils.md) – nur Backtest.

Profil: je Sitzung (UTC-Tag) aus der Vortagssitzung. Das Volumen jeder Kerze wird gleichmäßig auf ihre Spanne
High–Low verteilt (1h-Kerzen haben keine Intrabar-Daten), Preisstufen = bin_pct vom Tagestief. POC = Stufe mit
dem meisten Volumen, Value Area = vom POC aus jeweils die volumenstärkere Nachbarstufe, bis 70 % erreicht sind.

Setup 1 (POC-Bounce): Vortag schloss außerhalb der VA. Nur die erste Berührung des Vortags-POC zählt; sie oder eine
der CONFIRM_CANDLES Kerzen danach muss bestätigen: Schluss auf der Ausgangsseite, Kerze in Handelsrichtung, mehr
Volumen als die Vorkerze -> Signal. Schluss jenseits des Volumenknotens vorher bricht ab.
Stop hinter dem Volumenknoten um den POC (Nachbarstufen >= NODE_SHARE des POC-Volumens), "va"-Ziel = VA-Kante.

Setup 2 (VA-Reversal): Vortag schloss innerhalb der VA. Heute schließt eine Kerze außerhalb, später schließt eine
wieder innerhalb -> Signal (Einstieg zum Open der nächsten Kerze). Stop knapp hinter dem Extrem außerhalb der VA,
Ziel = gegenüberliegende VA-Kante ("va") oder festes Vielfaches des Risikos (float). Mehrfach je Sitzung möglich.

Setup 3 (Breakout mit Pullback): Schluss außerhalb der VA mit starker Kerze (Spanne und Volumen >= STRONG x Schnitt
der letzten LOOKBACK Kerzen, in Ausbruchsrichtung – schließt Absorption und dünnes Volumen aus). Danach flacher
Pullback bis PULLBACK_NEAR an die Kante ohne Schluss zurück in der VA, dann Strukturbruch (Schluss über dem
Ausbruchshoch) -> Signal. Stop hinter dem Pullback-Extrem, "va"-Ziel = nächster Naked POC (sonst 2R).

Setups kombiniert: je Kerze gewinnt das erste Setup in setups.

Ausführung: eine Position zur Zeit, Größe = risk / Stopabstand (max. max_leverage), Zeit-Stop zum Close der letzten
Kerze der Sitzung, Signale ohne Füllkerze in derselben Sitzung verfallen. Statistik zusätzlich je Setup in R
(nach Gebühren: enge Stops machen große Positionen, Gebühren kosten dann spürbar R).

Aufruf: python -m app.bot.volume_profile --symbol BTC/USDC:USDC --candles 5000
"""
import argparse
from functools import partial
from itertools import product
from typing import Dict, Iterator, List, NamedTuple, Optional, Tuple, Union

import numpy as np
import pandas as pd

from app.bot.backtest import TAKER_FEE, WINDOW, buy_and_hold, fetch_candles, stop_exit_price
from app.bot.price_action import STOP_BUFFER, walk_forward_orders
from app.bot.walk_forward import make_folds

BIN_PCT = 0.001  # Preisstufe 0,1 % – bei 1h-Kerzen genügt das; 400 Zeilen wie im Papier wären Scheinpräzision
VALUE_AREA = 0.7
RISK_PER_TRADE = 0.01  # 1 % des Kapitals bis zum Stop
MAX_LEVERAGE = 3.0
CONFIRM_CANDLES = 3  # Setup 1: Bestätigung bis 3 Kerzen nach der ersten POC-Berührung
NODE_SHARE = 0.5  # Volumenknoten um den POC: Stufen mit mindestens halbem POC-Volumen
LOOKBACK = 24  # Kerzen für Durchschnitts-Spanne/-Volumen (Setup 3)
STRONG = 1.5  # Ausbruchskerze: Spanne und Volumen mindestens 1,5x Durchschnitt
PULLBACK_NEAR = 0.002  # Pullback "nahe" der Kante: bis 0,2 % jenseits
NAKED_DAYS = 20  # Naked POCs verfallen nach 20 Sitzungen
FALLBACK_R = 2.0  # Ziel für Setup 3, wenn kein Naked POC voraus liegt
POC_BOUNCE, VA_REVERSAL, BREAKOUT = "poc_bounce", "va_reversal", "breakout"
Target = Union[str, float]  # "va" = strukturelles Ziel des Setups, sonst Vielfaches des Risikos
Params = Tuple[float, Target, float]  # (bin_pct, target, min_stop)
# min_stop: Mindest-Stopabstand – enge Stops ergeben große Positionen, deren Gebühren den Vorteil auffressen
GRID: List[Params] = list(product([0.0005, 0.001, 0.002], ["va", 1.0, 2.0], [0.0, 0.005, 0.01]))


class Profile(NamedTuple):
    poc: float
    val: float
    vah: float
    node_low: float  # Volumenknoten um den POC
    node_high: float


class Signal(NamedTuple):
    """Einstieg zum Open der nächsten Kerze, sofern sie noch in session liegt"""
    setup: str
    direction: int  # 1 = Long, -1 = Short
    stop: float
    target: float
    session: pd.Timestamp


class _Day(NamedTuple):
    """Eine Sitzung mit dem Profil des Vortags; c enthält alle Kerzen, Setups lesen nur bis zur aktuellen"""
    c: Dict[str, np.ndarray]
    s0: int
    s1: int
    prof: Profile
    prev_close: float
    session: pd.Timestamp
    target: Target
    naked: List[float]  # ungetestete POCs früherer Sitzungen (Stand Sitzungsbeginn)


class _Position(NamedTuple):
    signal: Signal
    entry: float
    risk: float  # Stopabstand als Anteil vom Einstieg
    size: float  # Positionsgröße als Vielfaches des Kapitals


def _value_area(volume: np.ndarray, edges: np.ndarray) -> Profile:
    """Vom POC aus die volumenstärkere Nachbarstufe aufnehmen, bis VALUE_AREA des Volumens erreicht ist"""
    poc = lo = hi = int(volume.argmax())
    inside, total = volume[poc], volume.sum()
    while inside < VALUE_AREA * total:
        down = volume[lo - 1] if lo > 0 else -1.0
        up = volume[hi + 1] if hi + 1 < len(volume) else -1.0
        if up >= down:
            hi, inside = hi + 1, inside + up
        else:
            lo, inside = lo - 1, inside + down
    node_lo, node_hi = _node(volume, poc)
    return Profile(float(edges[poc] + edges[poc + 1]) / 2, float(edges[lo]), float(edges[hi + 1]),
                   float(edges[node_lo]), float(edges[node_hi + 1]))


def _node(volume: np.ndarray, poc: int) -> Tuple[int, int]:
    """Zusammenhängende Stufen um den POC mit mindestens NODE_SHARE seines Volumens"""
    lo = hi = poc
    while lo > 0 and volume[lo - 1] >= NODE_SHARE * volume[poc]:
        lo -= 1
    while hi + 1 < len(volume) and volume[hi + 1] >= NODE_SHARE * volume[poc]:
        hi += 1
    return lo, hi


def session_profile(day: pd.DataFrame, bin_pct: float = BIN_PCT) -> Profile:
    """POC/VAL/VAH einer Sitzung; Kerzenvolumen gleichmäßig über High–Low verteilt"""
    low, high, vol = (day[c].to_numpy(float) for c in ("low", "high", "volume"))
    width = low.min() * bin_pct
    edges = low.min() + width * np.arange(int(np.ceil((high.max() - low.min()) / width)) + 2)
    span = high - low
    overlap = np.clip(np.minimum(high[:, None], edges[1:]) - np.maximum(low[:, None], edges[:-1]), 0, None)
    # Kerze ohne Spanne: ganzes Volumen in die Stufe ihres Preises
    own_bin = np.arange(len(edges) - 1) == np.searchsorted(edges, low, "right")[:, None] - 1
    share = np.where(span[:, None] > 0, overlap / np.where(span > 0, span, 1)[:, None], own_bin)
    return _value_area((share * vol[:, None]).sum(axis=0), edges)


def _target(target: Target, prof: Profile, direction: int, entry: float, stop: float) -> float:
    if target == "va":
        return prof.vah if direction > 0 else prof.val
    return entry + direction * float(target) * abs(entry - stop)


def _first_touch(day: _Day, d: int) -> Optional[int]:
    """Index der ersten Kerze, die den Vortags-POC aus Richtung d (1 = von oben) berührt"""
    side = day.c["low" if d > 0 else "high"][day.s0:day.s1]
    hits = np.flatnonzero(d * (side - day.prof.poc) <= 0)
    return day.s0 + int(hits[0]) if len(hits) else None


def _poc_bounce(day: _Day) -> Iterator[Tuple[int, Signal]]:
    """Setup 1: erste Rückkehr zum Vortags-POC nach Schluss außerhalb der VA, Abprall in Richtung Ausgangsseite.
    Bestätigung in der Berührungskerze oder bis CONFIRM_CANDLES danach; Schluss jenseits des Knotens bricht ab."""
    c, prof = day.c, day.prof
    d = 1 if day.prev_close > prof.vah else -1 if day.prev_close < prof.val else 0
    touch = _first_touch(day, d) if d else None
    if touch is None:
        return
    node_edge = prof.node_low if d > 0 else prof.node_high
    for t in range(touch, min(touch + CONFIRM_CANDLES + 1, day.s1)):
        close = c["close"][t]
        if d * (close - node_edge) < 0:
            return  # Knoten durchbrochen -> These ungültig
        if d * (close - prof.poc) > 0 and d * (close - c["open"][t]) > 0 and c["volume"][t] > c["volume"][t - 1]:
            extreme = c["low"][touch:t + 1].min() if d > 0 else c["high"][touch:t + 1].max()
            stop = (min(extreme, node_edge) if d > 0 else max(extreme, node_edge)) * (1 - d * STOP_BUFFER)
            yield t, Signal(POC_BOUNCE, d, float(stop), float(_target(day.target, prof, d, close, stop)), day.session)
            return


def _va_reversal(day: _Day) -> Iterator[Tuple[int, Signal]]:
    """Setup 2: Schluss außerhalb der VA, dann Schluss zurück innerhalb -> Signal gegen die Auslenkung"""
    c, prof, target, session = day.c, day.prof, day.target, day.session
    if not prof.val <= day.prev_close <= prof.vah:
        return
    side, extreme = 0, 0.0  # side: 1 = über VAH, -1 = unter VAL
    for t in range(day.s0, day.s1):
        close = c["close"][t]
        outside = 1 if close > prof.vah else -1 if close < prof.val else 0
        if outside and outside != side:
            side, extreme = outside, (c["high"][t] if outside > 0 else c["low"][t])
        if side:
            extreme = max(extreme, c["high"][t]) if side > 0 else min(extreme, c["low"][t])
        if side and not outside:
            direction, stop = -side, extreme * (1 + side * STOP_BUFFER)
            yield t, Signal(VA_REVERSAL, direction, float(stop),
                            float(_target(target, prof, direction, close, stop)), session)
            side = 0


def _strong(c: Dict[str, np.ndarray], t: int, d: int) -> bool:
    """Gesunde Ausbruchskerze: Spanne und Volumen über STRONG x Schnitt, Körper in Ausbruchsrichtung"""
    if t < LOOKBACK:
        return False
    span = c["high"][t - LOOKBACK:t + 1] - c["low"][t - LOOKBACK:t + 1]
    return (span[-1] >= STRONG * span[:-1].mean() and d * (c["close"][t] - c["open"][t]) > 0
            and c["volume"][t] >= STRONG * c["volume"][t - LOOKBACK:t].mean())


def _breakout_target(day: _Day, t: int, d: int, entry: float, stop: float) -> float:
    """Nächster Naked POC in Handelsrichtung, der heute bis t noch nicht berührt wurde; sonst FALLBACK_R"""
    if day.target != "va":
        return _target(day.target, day.prof, d, entry, stop)
    lo, hi = day.c["low"][day.s0:t + 1].min(), day.c["high"][day.s0:t + 1].max()
    ahead = [p for p in day.naked if d * (p - entry) > 0 and not lo <= p <= hi]
    return min(ahead, key=lambda p: abs(p - entry)) if ahead else entry + d * FALLBACK_R * abs(entry - stop)


def _breakout(day: _Day) -> Iterator[Tuple[int, Signal]]:
    """Setup 3: starker Ausbruch aus der VA, flacher Pullback an die Kante, Strukturbruch -> Signal"""
    c, prof = day.c, day.prof
    d, extreme, pullback = 0, 0.0, None  # pullback: Extrem gegen die Ausbruchsrichtung seit Pullback-Beginn
    for t in range(day.s0, day.s1):
        close, high, low = c["close"][t], c["high"][t], c["low"][t]
        outside = 1 if close > prof.vah else -1 if close < prof.val else 0
        if not d or outside != d:
            # kein Ausbruch aktiv oder Schluss zurück in der VA -> neu suchen
            d, extreme, pullback = (outside, high if outside > 0 else low, None) if outside and _strong(
                c, t, outside) else (0, 0.0, None)
            continue
        edge, against = (prof.vah, low) if d > 0 else (prof.val, high)
        if pullback is None:
            if d * (against - edge) <= PULLBACK_NEAR * edge:
                pullback = against
            else:
                extreme = max(extreme, high) if d > 0 else min(extreme, low)
        elif d * (close - extreme) > 0:
            stop = pullback * (1 - d * STOP_BUFFER)
            yield t, Signal(BREAKOUT, d, float(stop), float(_breakout_target(day, t, d, close, stop)), day.session)
            d, pullback = 0, None
        else:
            pullback = min(pullback, low) if d > 0 else max(pullback, high)


SETUPS = {POC_BOUNCE: _poc_bounce, VA_REVERSAL: _va_reversal, BREAKOUT: _breakout}
ALL_SETUPS = tuple(SETUPS)


def _naked(c: Dict[str, np.ndarray], pocs: List[Tuple[int, float]], s0: int) -> List[float]:
    """POCs (Sitzungsende, Preis), die zwischen Sitzungsende und s0 nie berührt wurden"""
    return [p for end, p in pocs if end >= s0 or not c["low"][end:s0].min() <= p <= c["high"][end:s0].max()]


def _days(candles: pd.DataFrame, bin_pct: float, target: Target) -> Iterator[_Day]:
    """Je Sitzung das Profil der Vortagssitzung; angeschnittene erste Sitzung (nicht ab 00:00 UTC) ergibt keins"""
    stamps = candles["timestamp"]
    sessions = stamps.dt.floor("D")
    starts = np.flatnonzero(sessions.ne(sessions.shift()).to_numpy())
    bounds = list(zip(starts, list(starts[1:]) + [len(candles)]))
    c = {k: candles[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume")}
    pocs: List[Tuple[int, float]] = []
    for (p0, p1), (s0, s1) in zip(bounds, bounds[1:]):
        if stamps.iloc[p0] != sessions.iloc[p0]:
            continue
        prof = session_profile(candles.iloc[p0:p1], bin_pct)
        pocs = pocs[-(NAKED_DAYS - 1):] + [(p1, prof.poc)]
        yield _Day(c, s0, s1, prof, c["close"][p1 - 1], sessions.iloc[s0], target, _naked(c, pocs, s0))


def build_signals(candles: pd.DataFrame, bin_pct: float = BIN_PCT, target: Target = "va",
                  min_stop: float = 0.0, setups: Tuple[str, ...] = ALL_SETUPS) -> List[Optional[Signal]]:
    """Je Kerze t das Signal aus Kerzen bis t (None = keins); Profil stets aus der abgeschlossenen Vortagssitzung.
    Signale mit Stopabstand (vom Signal-Close) unter min_stop entfallen; je Kerze gewinnt das erste Setup."""
    close = candles["close"].to_numpy(float)
    signals: List[Optional[Signal]] = [None] * len(candles)
    for day in _days(candles, bin_pct, target):
        for name in setups:
            for t, signal in SETUPS[name](day):
                if signals[t] is None and abs(close[t] - signal.stop) >= min_stop * close[t]:
                    signals[t] = signal
    return signals


def _open(signal: Signal, price: float, risk: float, max_leverage: float) -> Optional[_Position]:
    d = signal.direction
    dist = d * (price - signal.stop) / price
    if dist <= 0 or d * (signal.target - price) <= 0:
        return None  # Open liegt schon jenseits von Stop oder Ziel
    return _Position(signal, price, dist, min(risk / dist, max_leverage))


def _exit(bar: Dict, pos: _Position, session_end: bool) -> Optional[float]:
    """Stop/Ziel über High/Low (beide -> Stop), sonst Zeit-Stop zum Close der letzten Sitzungskerze"""
    d = pos.signal.direction
    price = stop_exit_price(bar, d, pos.entry, pos.risk, d * (pos.signal.target - pos.entry) / pos.entry)
    return bar["close"] if price is None and session_end else price


def _stats(trades: List[Tuple[str, float]], equity: float, max_dd: float) -> Dict:
    by_setup: Dict[str, List[float]] = {}
    for setup, r in trades:
        by_setup.setdefault(setup, []).append(r)
    setups = {s: {"trades": len(rs), "wins": sum(r > 0 for r in rs), "avg_r": sum(rs) / len(rs), "total_r": sum(rs)}
              for s, rs in by_setup.items()}
    return {"trades": len(trades), "wins": sum(r > 0 for _, r in trades), "total_return": equity - 1,
            "max_drawdown": max_dd, "setups": setups}


def simulate_signals(candles: pd.DataFrame, signals: List[Optional[Signal]], fee: float = TAKER_FEE,
                     risk: float = RISK_PER_TRADE, max_leverage: float = MAX_LEVERAGE) -> Dict:
    """Einstieg zum Open nach dem Signal, Größe nach Risiko; Kennzahlen wie simulate_orders plus R je Setup.
    shortcut: Gebühr auf die Einstiegsgröße auch beim Ausstieg, ohne Liquidation – bei max_leverage 3 vertretbar."""
    bars = candles.to_dict("records")
    sessions = candles["timestamp"].dt.floor("D").tolist()
    equity, peak, max_dd = 1.0, 1.0, 0.0
    pos: Optional[_Position] = None
    trades: List[Tuple[str, float]] = []  # (Setup, Ergebnis in R)
    for t, bar in enumerate(bars):
        signal = signals[t - 1] if t > 0 else None
        if pos is None and signal is not None and signal.session == sessions[t]:
            pos = _open(signal, bar["open"], risk, max_leverage)
            equity *= 1 - fee * (pos.size if pos else 0)
        if pos is not None:
            price = _exit(bar, pos, t + 1 == len(bars) or sessions[t + 1] != sessions[t])
            if price is not None:
                move = pos.signal.direction * (price / pos.entry - 1)
                equity *= (1 + pos.size * move) * (1 - fee * pos.size)
                trades.append((pos.signal.setup, (move - 2 * fee) / pos.risk))  # R nach Gebühren
                pos = None
        marked = equity * (1 + pos.size * pos.signal.direction * (bar["close"] / pos.entry - 1)) if pos else equity
        peak = max(peak, marked)
        max_dd = min(max_dd, marked / peak - 1)
    return _stats(trades, equity, max_dd)


def walk_forward_signals(candles: pd.DataFrame, grid: List[Params], start: int, train: int, test: int,
                         fee: float, setups: Tuple[str, ...] = ALL_SETUPS) -> Dict:
    """Walk-Forward wie bei der Price-Action-Methode, Parameter (bin_pct, target, min_stop)"""
    return walk_forward_orders(candles, grid, start, train, test, fee, partial(build_signals, setups=setups),
                               simulate_signals)


def _setup_line(r: Dict) -> str:
    return "  ".join(f"{s}: {v['trades']} Trades, {v['wins'] / v['trades']:.0%} Treffer, Ø {v['avg_r']:+.2f}R, "
                     f"Σ {v['total_r']:+.1f}R" for s, v in r["setups"].items()) or "keine Trades"


def _label(p: Params) -> str:
    return f"{p[0]:.2%}/{p[1]}/≥{p[2]:.1%}"


def _report(candles: pd.DataFrame, setups: Tuple[str, ...], args: argparse.Namespace) -> None:
    """Je Setup-Auswahl: ganzer Zeitraum je Parameter (nur --verbose) und Walk-Forward Out-of-Sample"""
    print(f"🔎 {' + '.join(setups)}")
    for p in GRID if args.verbose else []:
        r = simulate_signals(candles, build_signals(candles, *p, setups=setups), args.fee)
        print(f"  {_label(p):<18} Rendite {r['total_return']:+8.2%}  Max-DD {r['max_drawdown']:8.2%}  "
              f"{_setup_line(r)}")
    r = walk_forward_signals(candles, GRID, WINDOW, args.train, args.test, args.fee, setups)
    best = max(r["fixed"], key=r["fixed"].get)
    positive = sum(ret > 0 for ret in r["fixed"].values())
    print(f"  📊 OOS rollend {r['oos_return']:+.2%} | bestes festes {_label(best)} {r['fixed'][best]:+.1%} | "
          f"{positive}/{len(GRID)} feste positiv | Median {np.median(list(r['fixed'].values())):+.1%}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest + Walk-Forward der Volumenprofil-Strategie")
    parser.add_argument("--symbol", default="BTC/USDC:USDC")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--candles", type=int, default=5000)
    parser.add_argument("--train", type=int, default=2000)
    parser.add_argument("--test", type=int, default=500)
    parser.add_argument("--fee", type=float, default=TAKER_FEE)
    parser.add_argument("--verbose", action="store_true", help="Ergebnis je Parameter über den ganzen Zeitraum")
    args = parser.parse_args()

    candles = fetch_candles(args.symbol, args.timeframe, args.candles)
    folds = make_folds(len(candles), WINDOW, args.train, args.test)
    if not folds:
        raise SystemExit("⛔ Zu wenige Kerzen für Train + Test")
    hold = candles['close'].iloc[folds[-1][2] - 1] / candles['open'].iloc[folds[0][1]] - 1
    print(f"📈 {len(candles)} Kerzen {args.symbol} {args.timeframe}: {candles['timestamp'].iloc[0]} – "
          f"{candles['timestamp'].iloc[-1]}, Buy & Hold {buy_and_hold(candles):+.2%}, "
          f"Walk-Forward {len(folds)} Folds (Buy & Hold OOS {hold:+.2%})")
    for setups in [(name,) for name in ALL_SETUPS] + [ALL_SETUPS]:
        _report(candles, setups, args)


if __name__ == "__main__":
    main()
