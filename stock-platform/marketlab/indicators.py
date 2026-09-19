"""Causal technical indicators.

Every function returns a list the same length as its input. Positions that
cannot be computed yet (the warm-up window) hold ``None``. No function ever
reads an index greater than the one it is producing, so nothing here can leak
future information into a backtest.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

Num = Optional[float]


def sma(values: Sequence[float], period: int) -> List[Num]:
    """Simple moving average."""
    if period < 1:
        raise ValueError("period must be >= 1")
    out: List[Num] = [None] * len(values)
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= period:
            running -= values[i - period]
        if i >= period - 1:
            out[i] = running / period
    return out


def ema(values: Sequence[float], period: int) -> List[Num]:
    """Exponential moving average, seeded with the SMA of the first `period`."""
    if period < 1:
        raise ValueError("period must be >= 1")
    out: List[Num] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1.0)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = (values[i] - prev) * k + prev
        out[i] = prev
    return out


def rolling_stdev(values: Sequence[float], period: int) -> List[Num]:
    """Population standard deviation over a rolling window."""
    out: List[Num] = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        mean = sum(window) / period
        var = sum((x - mean) ** 2 for x in window) / period
        out[i] = var ** 0.5
    return out


def rsi(values: Sequence[float], period: int = 14) -> List[Num]:
    """Relative Strength Index using Wilder's smoothing."""
    out: List[Num] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = _rsi_from_averages(avg_gain, avg_loss)
    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(change, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-change, 0.0)) / period
        out[i] = _rsi_from_averages(avg_gain, avg_loss)
    return out


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def macd(
    values: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> Tuple[List[Num], List[Num], List[Num]]:
    """MACD line, signal line, histogram."""
    if fast >= slow:
        raise ValueError("fast period must be shorter than slow period")
    fast_line = ema(values, fast)
    slow_line = ema(values, slow)
    macd_line: List[Num] = [
        (f - s) if (f is not None and s is not None) else None
        for f, s in zip(fast_line, slow_line)
    ]
    # The signal line is an EMA of the MACD line, seeded once MACD exists.
    start = next((i for i, v in enumerate(macd_line) if v is not None), None)
    signal_line: List[Num] = [None] * len(values)
    hist: List[Num] = [None] * len(values)
    if start is not None:
        dense = [v for v in macd_line[start:] if v is not None]
        dense_signal = ema(dense, signal)
        for offset, v in enumerate(dense_signal):
            signal_line[start + offset] = v
    for i, (m, s) in enumerate(zip(macd_line, signal_line)):
        if m is not None and s is not None:
            hist[i] = m - s
    return macd_line, signal_line, hist


def bollinger(
    values: Sequence[float], period: int = 20, k: float = 2.0
) -> Tuple[List[Num], List[Num], List[Num]]:
    """Middle band (SMA), upper band, lower band."""
    mid = sma(values, period)
    sd = rolling_stdev(values, period)
    upper: List[Num] = [None] * len(values)
    lower: List[Num] = [None] * len(values)
    for i, (m, s) in enumerate(zip(mid, sd)):
        if m is not None and s is not None:
            upper[i] = m + k * s
            lower[i] = m - k * s
    return mid, upper, lower


def rolling_max(values: Sequence[float], period: int) -> List[Num]:
    out: List[Num] = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = max(values[i - period + 1 : i + 1])
    return out


def rolling_min(values: Sequence[float], period: int) -> List[Num]:
    out: List[Num] = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = min(values[i - period + 1 : i + 1])
    return out


def roc(values: Sequence[float], period: int) -> List[Num]:
    """Rate of change over `period` bars, as a fraction (0.05 == +5%)."""
    out: List[Num] = [None] * len(values)
    for i in range(period, len(values)):
        past = values[i - period]
        if past:
            out[i] = values[i] / past - 1.0
    return out


def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> List[Num]:
    """Average True Range using Wilder's smoothing."""
    n = len(closes)
    out: List[Num] = [None] * n
    if n <= period:
        return out
    true_ranges = [highs[0] - lows[0]]
    for i in range(1, n):
        prev_close = closes[i - 1]
        true_ranges.append(
            max(
                highs[i] - lows[i],
                abs(highs[i] - prev_close),
                abs(lows[i] - prev_close),
            )
        )
    current = sum(true_ranges[1 : period + 1]) / period
    out[period] = current
    for i in range(period + 1, n):
        current = (current * (period - 1) + true_ranges[i]) / period
        out[i] = current
    return out
