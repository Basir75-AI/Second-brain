"""Performance statistics for an equity curve.

Assumptions are explicit because they change the numbers:
  * `periods_per_year` defaults to 252 (US equity trading days). Change it for
    weekly or monthly bars.
  * Sharpe and Sortino use a configurable annual risk-free rate, default 0.0.
    A 0% risk-free rate flatters Sharpe in a high-rate environment; set
    `rf_annual` to the rate that applies to your period.
  * CAGR uses actual calendar time between the first and last bar (365.25 days
    per year), not bar counts.
"""

from __future__ import annotations

import datetime as _dt
import math
from typing import Dict, List, Optional, Sequence

TRADING_DAYS = 252


def returns_from_equity(equity: Sequence[float]) -> List[float]:
    out: List[float] = []
    for i in range(1, len(equity)):
        prev = equity[i - 1]
        out.append(equity[i] / prev - 1.0 if prev else 0.0)
    return out


def max_drawdown(equity: Sequence[float]) -> Dict[str, Optional[float]]:
    """Largest peak-to-trough decline, as a negative fraction."""
    peak = float("-inf")
    worst = 0.0
    peak_idx = trough_idx = 0
    best_peak_idx = 0
    for i, value in enumerate(equity):
        if value > peak:
            peak = value
            peak_idx = i
        dd = value / peak - 1.0 if peak else 0.0
        if dd < worst:
            worst = dd
            trough_idx = i
            best_peak_idx = peak_idx
    return {"max_drawdown": worst, "peak_index": best_peak_idx, "trough_index": trough_idx}


def drawdown_series(equity: Sequence[float]) -> List[float]:
    peak = float("-inf")
    out: List[float] = []
    for value in equity:
        peak = max(peak, value)
        out.append(value / peak - 1.0 if peak else 0.0)
    return out


def _stdev(values: Sequence[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return (sum((v - mean) ** 2 for v in values) / (n - 1)) ** 0.5


def compute_metrics(
    equity: Sequence[float],
    dates: Sequence[_dt.date],
    periods_per_year: int = TRADING_DAYS,
    rf_annual: float = 0.0,
) -> Dict[str, Optional[float]]:
    """Summary statistics for one equity curve."""
    if len(equity) < 2:
        return {k: None for k in (
            "total_return", "cagr", "volatility", "sharpe", "sortino",
            "max_drawdown", "calmar", "best_day", "worst_day", "positive_days",
        )}

    rets = returns_from_equity(equity)
    total_return = equity[-1] / equity[0] - 1.0 if equity[0] else None

    days = (dates[-1] - dates[0]).days
    years = days / 365.25 if days > 0 else None
    if years and equity[0] > 0 and equity[-1] > 0:
        cagr = (equity[-1] / equity[0]) ** (1.0 / years) - 1.0
    else:
        cagr = None

    sd = _stdev(rets)
    volatility = sd * math.sqrt(periods_per_year) if sd else 0.0

    rf_per_period = (1.0 + rf_annual) ** (1.0 / periods_per_year) - 1.0
    excess = [r - rf_per_period for r in rets]
    mean_excess = sum(excess) / len(excess)
    sharpe = (mean_excess / sd) * math.sqrt(periods_per_year) if sd else None

    downside = [min(e, 0.0) for e in excess]
    dd_rms = (sum(d * d for d in downside) / len(downside)) ** 0.5
    sortino = (mean_excess / dd_rms) * math.sqrt(periods_per_year) if dd_rms else None

    dd = max_drawdown(equity)
    mdd = dd["max_drawdown"]
    calmar = (cagr / abs(mdd)) if (cagr is not None and mdd) else None

    return {
        "total_return": total_return,
        "cagr": cagr,
        "volatility": volatility,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": mdd,
        "max_drawdown_peak_index": dd["peak_index"],
        "max_drawdown_trough_index": dd["trough_index"],
        "calmar": calmar,
        "best_day": max(rets),
        "worst_day": min(rets),
        "positive_days": sum(1 for r in rets if r > 0) / len(rets),
    }


def trade_stats(trades: Sequence[dict]) -> Dict[str, Optional[float]]:
    """Win rate, profit factor and friends, computed over closed round trips."""
    closed = [t for t in trades if t.get("exit_date") is not None]
    if not closed:
        return {
            "trades": 0, "win_rate": None, "profit_factor": None,
            "avg_win": None, "avg_loss": None, "avg_bars_held": None,
            "best_trade": None, "worst_trade": None, "expectancy": None,
        }
    wins = [t for t in closed if t["pnl"] > 0]
    losses = [t for t in closed if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    returns = [t["return_pct"] for t in closed]
    return {
        "trades": len(closed),
        "win_rate": len(wins) / len(closed),
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else None,
        "avg_win": (sum(t["return_pct"] for t in wins) / len(wins)) if wins else None,
        "avg_loss": (sum(t["return_pct"] for t in losses) / len(losses)) if losses else None,
        "avg_bars_held": sum(t["bars_held"] for t in closed) / len(closed),
        "best_trade": max(returns),
        "worst_trade": min(returns),
        "expectancy": sum(returns) / len(returns),
    }
