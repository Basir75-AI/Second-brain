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
from typing import Callable, Dict, List, Sequence, Tuple

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


def _hlc(bars: Sequence[Bar]) -> Tuple[List[float], List[float], List[float]]:
    """Highs, lows and closes on one consistent scale.

    `Bar.price` is the adjusted close where the feed supplies one, but high and
    low are always raw. Mixing the two would make a split look like a crash to
    any range-based indicator, so scale the range by the same factor.
    """
    highs: List[float] = []
    lows: List[float] = []
    closes: List[float] = []
    for bar in bars:
        factor = (
            bar.adj_close / bar.close
            if (bar.adj_close is not None and bar.close)
            else 1.0
        )
        highs.append(bar.high * factor)
        lows.append(bar.low * factor)
        closes.append(bar.price)
    return highs, lows, closes


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



def _atr_trailing_stop(bars, p):
    """Break out to an N-bar high, then ride it behind an ATR trailing stop.

    The stop widens when the market is volatile and tightens when it is calm,
    which is the point: a fixed percentage stop is too tight in a storm and too
    loose in a drift.
    """
    highs, lows, closes = _hlc(bars)
    ranges = ind.atr(highs, lows, closes, int(p["atr_period"]))
    breakout = ind.rolling_max(closes, int(p["entry_lookback"]))
    breakdown = ind.rolling_min(closes, int(p["entry_lookback"]))
    multiplier = float(p["multiplier"])
    short = _short_leg(p["allow_short"])
    out: List[float] = []
    state = 0.0
    peak = trough = 0.0
    for i, close in enumerate(closes):
        width, high_mark, low_mark = ranges[i], breakout[i], breakdown[i]
        if width is None or high_mark is None:
            out.append(0.0)
            continue
        if state == 0.0:
            if close >= high_mark:
                state, peak = 1.0, close
            elif short and low_mark is not None and close <= low_mark:
                state, trough = short, close
        elif state > 0:
            peak = max(peak, close)
            if close < peak - multiplier * width:
                state = 0.0
        else:
            trough = min(trough, close)
            if close > trough + multiplier * width:
                state = 0.0
        out.append(state)
    return out


def _keltner_breakout(bars, p):
    """Bollinger breakout's cousin, with the band width set by ATR."""
    highs, lows, closes = _hlc(bars)
    mid, upper, lower = ind.keltner(
        highs, lows, closes, int(p["period"]), int(p["atr_period"]), float(p["k"])
    )
    short = _short_leg(p["allow_short"])
    out: List[float] = []
    state = 0.0
    for close, m, u, l in zip(closes, mid, upper, lower):
        if m is None or u is None or l is None:
            out.append(0.0)
            continue
        if state == 0.0:
            if close > u:
                state = 1.0
            elif short and close < l:
                state = short
        elif state > 0 and close <= m:
            state = 0.0
        elif state < 0 and close >= m:
            state = 0.0
        out.append(state)
    return out


def _stochastic_reversion(bars, p):
    """Buy an oversold stochastic that has already turned up.

    Requiring %K above %D is what stops this buying all the way down: the
    oscillator has to be low *and* rising.
    """
    highs, lows, closes = _hlc(bars)
    k_line, d_line = ind.stochastic(
        highs, lows, closes, int(p["k_period"]), int(p["d_period"])
    )
    oversold, overbought = float(p["oversold"]), float(p["overbought"])
    short = _short_leg(p["allow_short"])
    out: List[float] = []
    state = 0.0
    for k, d in zip(k_line, d_line):
        if k is None or d is None:
            out.append(0.0)
            continue
        if state == 0.0:
            if k < oversold and k > d:
                state = 1.0
            elif short and k > overbought and k < d:
                state = short
        elif state > 0 and k > overbought:
            state = 0.0
        elif state < 0 and k < oversold:
            state = 0.0
        out.append(state)
    return out


def _vol_target(bars, p):
    """Hold a constant *risk* budget rather than a constant position.

    Exposure is the target volatility divided by what the market is actually
    doing, so a calm market gets a full position and a violent one gets a
    fraction. Only the long side, and only above the trend filter. The
    rebalance band stops it trading every single bar; without one, a
    continuously varying target is eaten alive by costs.

    Exposure is capped at 1.0 because nothing here models margin or borrowing.
    """
    closes = _closes(bars)
    vol = ind.realized_volatility(closes, int(p["vol_lookback"]))
    trend = ind.sma(closes, int(p["trend_period"]))
    target = float(p["target_vol"]) / 100.0
    cap = float(p["max_exposure"])
    band = float(p["rebalance_band"]) / 100.0
    out: List[float] = []
    state = 0.0
    for close, v, t in zip(closes, vol, trend):
        if v is None or t is None or v <= 0 or close <= t:
            desired = 0.0
        else:
            desired = min(cap, target / v)
        if abs(desired - state) > band:
            state = desired
        out.append(state)
    return out


def _rsi_pullback(bars, p):
    """Buy a short-term dip, but only while the long-term trend is up.

    A plain oversold signal fires just as often in a collapse; the trend filter
    is what separates a pullback from the start of one.
    """
    closes = _closes(bars)
    strength = ind.rsi(closes, int(p["rsi_period"]))
    trend = ind.sma(closes, int(p["trend_period"]))
    exit_line = ind.sma(closes, int(p["exit_ma"]))
    oversold = float(p["oversold"])
    out: List[float] = []
    state = 0.0
    for close, r, t, e in zip(closes, strength, trend, exit_line):
        if r is None or t is None or e is None:
            out.append(0.0)
            continue
        if state == 0.0:
            if close > t and r < oversold:
                state = 1.0
        elif close > e or close < t:
            # Take the bounce, or leave if the trend itself has broken.
            state = 0.0
        out.append(state)
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


register(Strategy(
    "atr_trailing_stop", "ATR trailing stop",
    "Break out to an N-bar high, then ride it behind a stop set by recent volatility.",
    [Param("entry_lookback", "Entry lookback", 50, minimum=2, maximum=300),
     Param("atr_period", "ATR period", 14, minimum=2, maximum=100),
     Param("multiplier", "Stop width (ATR)", 3.0, kind="float",
           minimum=0.5, maximum=10.0, step=0.5), SHORT_PARAM],
    _atr_trailing_stop, family="volatility",
))
register(Strategy(
    "keltner_breakout", "Keltner breakout",
    "Buy a close above an ATR-width channel, exit back at its middle.",
    [Param("period", "EMA period", 20, minimum=5, maximum=200),
     Param("atr_period", "ATR period", 10, minimum=2, maximum=100),
     Param("k", "Band width (ATR)", 2.0, kind="float", minimum=0.5, maximum=5.0, step=0.1),
     SHORT_PARAM],
    _keltner_breakout, family="volatility",
))
register(Strategy(
    "stochastic_reversion", "Stochastic reversion",
    "Buy an oversold stochastic that has already turned up, sell it overbought.",
    [Param("k_period", "%K period", 14, minimum=2, maximum=100),
     Param("d_period", "%D smoothing", 3, minimum=1, maximum=30),
     Param("oversold", "Buy below", 20, minimum=5, maximum=45),
     Param("overbought", "Sell above", 80, minimum=55, maximum=95), SHORT_PARAM],
    _stochastic_reversion, family="mean-reversion",
))
register(Strategy(
    "vol_target", "Volatility targeting",
    "Size the position so risk stays constant: full when calm, a fraction when wild.",
    [Param("target_vol", "Target vol %", 15.0, kind="float",
           minimum=2.0, maximum=60.0, step=1.0),
     Param("vol_lookback", "Vol lookback", 20, minimum=5, maximum=252),
     Param("trend_period", "Trend MA", 200, minimum=5, maximum=400),
     Param("max_exposure", "Max exposure", 1.0, kind="float",
           minimum=0.1, maximum=1.0, step=0.1),
     Param("rebalance_band", "Rebalance band %", 10.0, kind="float",
           minimum=1.0, maximum=50.0, step=1.0)],
    _vol_target, family="risk",
))
register(Strategy(
    "rsi_pullback", "RSI pullback in an uptrend",
    "Buy a short-term oversold dip, but only while price holds above its long trend.",
    [Param("rsi_period", "RSI period", 2, minimum=2, maximum=30),
     Param("oversold", "Buy below", 10, minimum=2, maximum=45),
     Param("trend_period", "Trend MA", 200, minimum=5, maximum=400),
     Param("exit_ma", "Exit MA", 5, minimum=2, maximum=100)],
    _rsi_pullback, family="mean-reversion",
))


def get(key: str) -> Strategy:
    if key not in REGISTRY:
        raise KeyError(f"unknown strategy '{key}'. Known: {', '.join(sorted(REGISTRY))}")
    return REGISTRY[key]


def list_strategies() -> List[dict]:
    return [s.to_dict() for s in REGISTRY.values()]
