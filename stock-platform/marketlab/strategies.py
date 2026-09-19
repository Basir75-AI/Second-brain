"""Strategy library.

A strategy is a pure function ``(bars, params) -> list[float]`` where entry *i*
is the target exposure decided at the **close of bar i** (1.0 long, 0.0 flat,
-1.0 short). The engine fills it on a later bar, so a strategy can never trade
on information it did not have.

Each strategy declares its parameters so the web UI can build a form and the
optimiser can sweep a grid without hard-coding anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Sequence

from . import indicators as ind
from .backtest import Bar


@dataclass
class Param:
    name: str
    label: str
    default: float
    kind: str = "int"          # "int" | "float" | "bool"
    minimum: float = 1
    maximum: float = 400
    step: float = 1
    help: str = ""

    def coerce(self, value):
        if self.kind == "bool":
            return bool(value)
        if self.kind == "int":
            return int(round(float(value)))
        return float(value)

    def to_dict(self) -> dict:
        return {
            "name": self.name, "label": self.label, "default": self.default,
            "kind": self.kind, "min": self.minimum, "max": self.maximum,
            "step": self.step, "help": self.help,
        }


@dataclass
class Strategy:
    key: str
    label: str
    summary: str
    params: List[Param]
    fn: Callable[[Sequence[Bar], Dict[str, float]], List[float]]
    family: str = "trend"

    def resolve(self, raw: Dict[str, object] | None) -> Dict[str, float]:
        raw = raw or {}
        resolved = {}
        for p in self.params:
            resolved[p.name] = p.coerce(raw.get(p.name, p.default))
        return resolved

    def generate(self, bars: Sequence[Bar], raw_params: Dict[str, object] | None = None):
        params = self.resolve(raw_params)
        return self.fn(bars, params), params

    def to_dict(self) -> dict:
        return {
            "key": self.key, "label": self.label, "summary": self.summary,
            "family": self.family, "params": [p.to_dict() for p in self.params],
        }


def _closes(bars: Sequence[Bar]) -> List[float]:
    return [b.price for b in bars]


def _short_leg(allow_short: bool) -> float:
    return -1.0 if allow_short else 0.0


SHORT_PARAM = Param(
    "allow_short", "Allow shorting", 0, kind="bool",
    help="Go -1 instead of flat on a bearish signal. Shorts here pay no borrow fee.",
)


# --- individual strategies -------------------------------------------------

def _buy_and_hold(bars, p):
    return [1.0] * len(bars)


def _sma_crossover(bars, p):
    closes = _closes(bars)
    fast = ind.sma(closes, int(p["fast"]))
    slow = ind.sma(closes, int(p["slow"]))
    short = _short_leg(p["allow_short"])
    out = []
    for f, s in zip(fast, slow):
        if f is None or s is None:
            out.append(0.0)
        else:
            out.append(1.0 if f > s else short)
    return out


def _ema_crossover(bars, p):
    closes = _closes(bars)
    fast = ind.ema(closes, int(p["fast"]))
    slow = ind.ema(closes, int(p["slow"]))
    short = _short_leg(p["allow_short"])
    return [
        0.0 if (f is None or s is None) else (1.0 if f > s else short)
        for f, s in zip(fast, slow)
    ]


def _trend_filter(bars, p):
    """The classic long-above-its-own-moving-average filter."""
    closes = _closes(bars)
    line = ind.sma(closes, int(p["period"]))
    short = _short_leg(p["allow_short"])
    return [
        0.0 if m is None else (1.0 if c > m else short)
        for c, m in zip(closes, line)
    ]


def _rsi_reversion(bars, p):
    """Buy oversold, exit when the bounce carries RSI back above `exit_level`."""
    closes = _closes(bars)
    values = ind.rsi(closes, int(p["period"]))
    low, exit_level, high = p["oversold"], p["exit_level"], p["overbought"]
    short = _short_leg(p["allow_short"])
    out: List[float] = []
    state = 0.0
    for v in values:
        if v is None:
            out.append(0.0)
            continue
        if state == 0.0:
            if v < low:
                state = 1.0
            elif short and v > high:
                state = short
        elif state > 0 and v > exit_level:
            state = 0.0
        elif state < 0 and v < (100.0 - exit_level):
            state = 0.0
        out.append(state)
    return out


def _macd_cross(bars, p):
    closes = _closes(bars)
    line, signal, _ = ind.macd(closes, int(p["fast"]), int(p["slow"]), int(p["signal"]))
    short = _short_leg(p["allow_short"])
    return [
        0.0 if (m is None or s is None) else (1.0 if m > s else short)
        for m, s in zip(line, signal)
    ]


def _bollinger_reversion(bars, p):
    """Buy the lower band, exit at the middle band."""
    closes = _closes(bars)
    mid, upper, lower = ind.bollinger(closes, int(p["period"]), float(p["k"]))
    short = _short_leg(p["allow_short"])
    out: List[float] = []
    state = 0.0
    for c, m, u, l in zip(closes, mid, upper, lower):
        if m is None:
            out.append(0.0)
            continue
        if state == 0.0:
            if c < l:
                state = 1.0
            elif short and c > u:
                state = short
        elif state > 0 and c >= m:
            state = 0.0
        elif state < 0 and c <= m:
            state = 0.0
        out.append(state)
    return out


def _bollinger_breakout(bars, p):
    """The opposite trade: buy strength through the upper band."""
    closes = _closes(bars)
    mid, upper, lower = ind.bollinger(closes, int(p["period"]), float(p["k"]))
    short = _short_leg(p["allow_short"])
    out: List[float] = []
    state = 0.0
    for c, m, u, l in zip(closes, mid, upper, lower):
        if m is None:
            out.append(0.0)
            continue
        if state == 0.0:
            if c > u:
                state = 1.0
            elif short and c < l:
                state = short
        elif state > 0 and c <= m:
            state = 0.0
        elif state < 0 and c >= m:
            state = 0.0
        out.append(state)
    return out


def _donchian(bars, p):
    """Turtle-style channel breakout: buy an N-bar high, exit an M-bar low."""
    closes = _closes(bars)
    entry_n, exit_n = int(p["entry"]), int(p["exit"])
    highs = ind.rolling_max(closes, entry_n)
    lows = ind.rolling_min(closes, exit_n)
    entry_lows = ind.rolling_min(closes, entry_n)
    exit_highs = ind.rolling_max(closes, exit_n)
    short = _short_leg(p["allow_short"])
    out: List[float] = []
    state = 0.0
    for i, c in enumerate(closes):
        hi, lo = highs[i], lows[i]
        if hi is None or lo is None:
            out.append(0.0)
            continue
        if state == 0.0:
            if c >= hi:
                state = 1.0
            elif short and entry_lows[i] is not None and c <= entry_lows[i]:
                state = short
        elif state > 0 and c <= lo:
            state = 0.0
        elif state < 0 and exit_highs[i] is not None and c >= exit_highs[i]:
            state = 0.0
        out.append(state)
    return out


def _momentum(bars, p):
    """Time-series momentum: long while the N-bar return clears a threshold."""
    closes = _closes(bars)
    values = ind.roc(closes, int(p["lookback"]))
    threshold = float(p["threshold"]) / 100.0
    short = _short_leg(p["allow_short"])
    return [
        0.0 if v is None else (1.0 if v > threshold else (short if v < -threshold else 0.0))
        for v in values
    ]


def _dual_momentum_filter(bars, p):
    """Momentum entry, but only while price is above a long trend filter."""
    closes = _closes(bars)
    mom = ind.roc(closes, int(p["lookback"]))
    trend = ind.sma(closes, int(p["trend_period"]))
    out: List[float] = []
    for c, m, t in zip(closes, mom, trend):
        if m is None or t is None:
            out.append(0.0)
        else:
            out.append(1.0 if (m > 0 and c > t) else 0.0)
    return out


REGISTRY: Dict[str, Strategy] = {}


def register(strategy: Strategy) -> Strategy:
    REGISTRY[strategy.key] = strategy
    return strategy


register(Strategy(
    "buy_and_hold", "Buy and hold", "Own it from the first bar to the last. The benchmark every other row has to beat.",
    [], _buy_and_hold, family="benchmark",
))
register(Strategy(
    "sma_crossover", "SMA crossover",
    "Long while the fast simple moving average is above the slow one.",
    [Param("fast", "Fast period", 20, minimum=2, maximum=200),
     Param("slow", "Slow period", 50, minimum=3, maximum=400), SHORT_PARAM],
    _sma_crossover,
))
register(Strategy(
    "ema_crossover", "EMA crossover",
    "Same idea as the SMA cross but with exponential averages, which turn faster.",
    [Param("fast", "Fast period", 12, minimum=2, maximum=200),
     Param("slow", "Slow period", 26, minimum=3, maximum=400), SHORT_PARAM],
    _ema_crossover,
))
register(Strategy(
    "trend_filter", "Price vs moving average",
    "Long whenever price closes above its own moving average. The 200-day version of this is the most-cited trend rule there is.",
    [Param("period", "MA period", 200, minimum=5, maximum=400), SHORT_PARAM],
    _trend_filter,
))
register(Strategy(
    "rsi_reversion", "RSI mean reversion",
    "Buy when RSI marks the market oversold, sell into the bounce.",
    [Param("period", "RSI period", 14, minimum=2, maximum=60),
     Param("oversold", "Buy below", 30, minimum=5, maximum=50),
     Param("exit_level", "Exit above", 55, minimum=30, maximum=95),
     Param("overbought", "Short above", 70, minimum=50, maximum=95), SHORT_PARAM],
    _rsi_reversion, family="mean-reversion",
))
register(Strategy(
    "macd_cross", "MACD signal cross",
    "Long while the MACD line is above its signal line.",
    [Param("fast", "Fast EMA", 12, minimum=2, maximum=100),
     Param("slow", "Slow EMA", 26, minimum=3, maximum=200),
     Param("signal", "Signal EMA", 9, minimum=2, maximum=60), SHORT_PARAM],
    _macd_cross,
))
register(Strategy(
    "bollinger_reversion", "Bollinger mean reversion",
    "Buy a close below the lower band, exit back at the middle band.",
    [Param("period", "Period", 20, minimum=5, maximum=200),
     Param("k", "Band width (sd)", 2.0, kind="float", minimum=0.5, maximum=4.0, step=0.1),
     SHORT_PARAM],
    _bollinger_reversion, family="mean-reversion",
))
register(Strategy(
    "bollinger_breakout", "Bollinger breakout",
    "The mirror image: buy a close above the upper band, exit at the middle band.",
    [Param("period", "Period", 20, minimum=5, maximum=200),
     Param("k", "Band width (sd)", 2.0, kind="float", minimum=0.5, maximum=4.0, step=0.1),
     SHORT_PARAM],
    _bollinger_breakout,
))
register(Strategy(
    "donchian", "Donchian breakout",
    "Buy an N-bar high, exit on an M-bar low. The classic turtle channel.",
    [Param("entry", "Entry lookback", 20, minimum=2, maximum=300),
     Param("exit", "Exit lookback", 10, minimum=2, maximum=300), SHORT_PARAM],
    _donchian,
))
register(Strategy(
    "momentum", "Time-series momentum",
    "Long while the trailing N-bar return clears a threshold.",
    [Param("lookback", "Lookback bars", 126, minimum=2, maximum=400),
     Param("threshold", "Threshold %", 0.0, kind="float", minimum=-20, maximum=20, step=0.5),
     SHORT_PARAM],
    _momentum,
))
register(Strategy(
    "dual_momentum_filter", "Momentum + trend filter",
    "Only take the momentum signal while price also sits above a long moving average.",
    [Param("lookback", "Momentum lookback", 126, minimum=2, maximum=400),
     Param("trend_period", "Trend MA", 200, minimum=5, maximum=400)],
    _dual_momentum_filter,
))


def get(key: str) -> Strategy:
    if key not in REGISTRY:
        raise KeyError(f"unknown strategy '{key}'. Known: {', '.join(sorted(REGISTRY))}")
    return REGISTRY[key]


def list_strategies() -> List[dict]:
    return [s.to_dict() for s in REGISTRY.values()]
