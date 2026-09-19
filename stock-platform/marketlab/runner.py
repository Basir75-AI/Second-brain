"""Orchestration: analysis snapshots, multi-strategy comparison, and sweeps."""

from __future__ import annotations

import datetime as _dt
import itertools
import math
from typing import Dict, Iterable, List, Optional, Sequence

from . import indicators as ind
from . import strategies as strat
from .backtest import Bar, BacktestConfig, BacktestResult, run_backtest
from .metrics import compute_metrics, drawdown_series

RANKABLE = (
    "cagr", "total_return", "sharpe", "sortino", "calmar",
    "max_drawdown", "profit_factor", "win_rate", "final_equity",
)


# -- analysis --------------------------------------------------------------

def price_analysis(bars: Sequence[Bar]) -> dict:
    """A snapshot of where the stock stands, using only what the data says."""
    closes = [b.price for b in bars]
    last = closes[-1]
    out: dict = {
        "first_date": bars[0].date.isoformat(),
        "last_date": bars[-1].date.isoformat(),
        "bars": len(bars),
        "last_close": last,
        "currency_note": "Prices are whatever currency the exchange reports; the API does not normalise this.",
    }

    for period in (20, 50, 100, 200):
        value = ind.sma(closes, period)[-1] if len(closes) >= period else None
        out[f"sma_{period}"] = value
        out[f"pct_from_sma_{period}"] = (last / value - 1.0) if value else None

    rsi_series = ind.rsi(closes, 14)
    out["rsi_14"] = rsi_series[-1]

    for label, window in (("1m", 21), ("3m", 63), ("6m", 126), ("1y", 252)):
        out[f"return_{label}"] = (
            (last / closes[-1 - window] - 1.0) if len(closes) > window else None
        )

    window = closes[-252:] if len(closes) >= 252 else closes
    high, low = max(window), min(window)
    out["high_52w"] = high
    out["low_52w"] = low
    out["pct_from_52w_high"] = (last / high - 1.0) if high else None
    out["pct_from_52w_low"] = (last / low - 1.0) if low else None

    rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes)) if closes[i - 1]]
    recent = rets[-252:] if len(rets) >= 252 else rets
    if len(recent) > 1:
        mean = sum(recent) / len(recent)
        sd = (sum((r - mean) ** 2 for r in recent) / (len(recent) - 1)) ** 0.5
        out["volatility_annualised"] = sd * math.sqrt(252)
    else:
        out["volatility_annualised"] = None

    dd = drawdown_series(closes)
    out["current_drawdown"] = dd[-1]
    out["max_drawdown_in_window"] = min(dd)
    out["avg_volume_20"] = (
        sum(b.volume for b in bars[-20:]) / min(20, len(bars)) if bars else None
    )
    out["has_adjusted_prices"] = any(b.adj_close is not None for b in bars)
    return out


def indicator_overlays(bars: Sequence[Bar]) -> dict:
    """Series the chart draws on top of price."""
    closes = [b.price for b in bars]
    mid, upper, lower = ind.bollinger(closes, 20, 2.0)
    macd_line, macd_signal, macd_hist = ind.macd(closes)
    return {
        "dates": [b.date.isoformat() for b in bars],
        "close": closes,
        "volume": [b.volume for b in bars],
        "sma_50": ind.sma(closes, 50),
        "sma_200": ind.sma(closes, 200),
        "bb_upper": upper,
        "bb_lower": lower,
        "rsi_14": ind.rsi(closes, 14),
        "macd": macd_line,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist,
    }


# -- comparison ------------------------------------------------------------

def run_strategies(
    bars: Sequence[Bar],
    specs: Sequence[dict],
    config: BacktestConfig,
    include_benchmark: bool = True,
) -> List[BacktestResult]:
    """Run each {"key": ..., "params": {...}} spec over the same bars."""
    seen = set()
    queue: List[dict] = []
    for spec in specs:
        key = spec.get("key") or spec.get("strategy")
        if not key:
            raise ValueError("each strategy spec needs a 'key'")
        queue.append({"key": key, "params": spec.get("params") or {}})
        seen.add(key)
    if include_benchmark and "buy_and_hold" not in seen:
        queue.append({"key": "buy_and_hold", "params": {}})

    results: List[BacktestResult] = []
    for spec in queue:
        strategy = strat.get(spec["key"])
        targets, params = strategy.generate(bars, spec["params"])
        result = run_backtest(bars, targets, config, strategy.label, params)
        result.strategy = strategy.label
        result.params = dict(params)
        result.params["_key"] = strategy.key
        results.append(result)
    return results


def rank(results: Sequence[BacktestResult], metric: str = "sharpe") -> List[dict]:
    """Rank strategies by a metric, highest-is-best except for drawdown."""
    if metric not in RANKABLE:
        raise ValueError(f"cannot rank by '{metric}'. Try one of: {', '.join(RANKABLE)}")
    # Every rankable metric is "higher is better", drawdown included: it is a
    # negative number, so -12% sorts above -30% under a plain descending sort.
    rows = [
        {
            "strategy": r.strategy,
            "key": r.params.get("_key"),
            "params": {k: v for k, v in r.params.items() if k != "_key"},
            "metrics": r.metrics,
        }
        for r in results
    ]
    def sort_key(row):
        value = row["metrics"].get(metric)
        return float("-inf") if value is None else value    # unscorable rows sink
    rows.sort(key=sort_key, reverse=True)
    for position, row in enumerate(rows, start=1):
        row["rank"] = position
    return rows


# -- parameter sweep / walk-forward ---------------------------------------

def _expand_grid(grid: Dict[str, Sequence]) -> List[Dict[str, float]]:
    if not grid:
        return [{}]
    names = list(grid)
    combos = itertools.product(*(grid[name] for name in names))
    return [dict(zip(names, combo)) for combo in combos]


def sweep(
    bars: Sequence[Bar],
    strategy_key: str,
    grid: Dict[str, Sequence],
    config: BacktestConfig,
    metric: str = "sharpe",
    in_sample_fraction: float = 0.7,
    max_combos: int = 400,
) -> dict:
    """Grid-search a strategy in-sample, then report the winner out-of-sample.

    The out-of-sample number is the only one worth anything. A grid search will
    always find *something* that looks good on the data it was fitted to; the
    gap between the in-sample and out-of-sample column is the size of the lie.
    """
    strategy = strat.get(strategy_key)
    combos = _expand_grid(grid)
    if len(combos) > max_combos:
        raise ValueError(
            f"{len(combos)} combinations exceeds the {max_combos} cap. Narrow the grid."
        )
    if not 0.2 <= in_sample_fraction <= 0.9:
        raise ValueError("in_sample_fraction must be between 0.2 and 0.9")

    split = int(len(bars) * in_sample_fraction)
    in_sample = bars[:split]
    out_sample = bars[split:]
    if len(in_sample) < 30 or len(out_sample) < 30:
        raise ValueError(
            "not enough bars on one side of the split - fetch a longer history"
        )

    rows = []
    for params in combos:
        try:
            targets, resolved = strategy.generate(in_sample, params)
            result = run_backtest(in_sample, targets, config, strategy.label, resolved)
        except (ValueError, ZeroDivisionError) as exc:
            rows.append({"params": params, "error": str(exc)})
            continue
        rows.append({
            "params": resolved,
            "in_sample": _compact(result.metrics),
        })

    scored = [r for r in rows if "in_sample" in r and r["in_sample"].get(metric) is not None]
    scored.sort(key=lambda r: r["in_sample"][metric], reverse=True)

    best_oos = None
    if scored:
        best_params = scored[0]["params"]
        targets, resolved = strategy.generate(out_sample, best_params)
        oos = run_backtest(out_sample, targets, config, strategy.label, resolved)
        best_oos = _compact(oos.metrics)
        scored[0]["out_of_sample"] = best_oos

    # Everything, evaluated out-of-sample, so you can see whether the winner
    # was a fluke or the whole neighbourhood works.
    for row in scored[:25]:
        if "out_of_sample" in row:
            continue
        targets, resolved = strategy.generate(out_sample, row["params"])
        row["out_of_sample"] = _compact(
            run_backtest(out_sample, targets, config, strategy.label, resolved).metrics
        )

    return {
        "strategy": strategy.label,
        "key": strategy.key,
        "metric": metric,
        "combinations_tested": len(combos),
        "split_date": bars[split].date.isoformat(),
        "in_sample_bars": len(in_sample),
        "out_of_sample_bars": len(out_sample),
        "results": scored[:25],
        "failed": [r for r in rows if "error" in r][:10],
        "caveat": (
            "In-sample rankings are fitted to the past. Judge a strategy on the "
            "out-of-sample column, and on whether nearby parameters also work."
        ),
    }


def _compact(metrics: Dict[str, Optional[float]]) -> dict:
    keys = (
        "total_return", "cagr", "sharpe", "sortino", "max_drawdown", "calmar",
        "win_rate", "profit_factor", "trades", "exposure", "final_equity",
    )
    return {k: metrics.get(k) for k in keys}
