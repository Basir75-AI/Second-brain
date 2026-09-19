"""The backtest engine.

Design notes that matter for whether the numbers mean anything:

* **No lookahead.** A strategy sees bars ``0..i`` and produces a target
  exposure for bar ``i``. The engine then fills that order on a *later* bar.
* **Execution models** (`execution=`):
    - ``next_open``  (default) signal at the close of bar i, filled at the
      open of bar i+1. The most defensible for end-of-day data: you saw the
      close, you traded the next morning.
    - ``next_close`` filled at the close of bar i+1. More conservative on
      gaps, less realistic on timing.
    - ``signal_close`` filled at the close of bar i itself. This assumes you
      can transact at the closing print you just used to decide. Optimistic;
      included for comparison with vectorised backtests that do this silently.
* **Costs.** `fee_bps` and `slippage_bps` are charged on the *notional traded*,
  each way. 10 bps = 0.10%.
* **Sizing.** Target exposure is a fraction of current equity: 1.0 = fully
  long, 0.0 = flat, -1.0 = fully short. Shorts are frictionless here - there
  is no borrow fee and no margin call. Treat short results as optimistic.
* **Dividends.** Returns come from whichever price series you pass in. Use the
  adjusted series to include dividends and splits; see `provider.price_series`.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .metrics import compute_metrics, drawdown_series, trade_stats

EXECUTION_MODES = ("next_open", "next_close", "signal_close")


@dataclass
class Bar:
    date: _dt.date
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    adj_close: Optional[float] = None

    @property
    def price(self) -> float:
        return self.adj_close if self.adj_close is not None else self.close


@dataclass
class BacktestConfig:
    initial_cash: float = 10_000.0
    fee_bps: float = 5.0
    slippage_bps: float = 5.0
    execution: str = "next_open"
    periods_per_year: int = 252
    rf_annual: float = 0.0
    use_adjusted: bool = True


@dataclass
class _Position:
    units: float = 0.0
    entry_price: float = 0.0
    entry_date: Optional[_dt.date] = None
    entry_index: int = 0
    cost_paid: float = 0.0


@dataclass
class BacktestResult:
    strategy: str
    params: Dict[str, object]
    dates: List[_dt.date]
    equity: List[float]
    exposure: List[float]
    drawdown: List[float]
    trades: List[dict]
    metrics: Dict[str, Optional[float]]
    total_costs: float
    warnings: List[str] = field(default_factory=list)

    def to_dict(self, include_series: bool = True) -> dict:
        out = {
            "strategy": self.strategy,
            "params": self.params,
            "metrics": self.metrics,
            "trades": self.trades,
            "total_costs": self.total_costs,
            "warnings": self.warnings,
        }
        if include_series:
            out["series"] = {
                "dates": [d.isoformat() for d in self.dates],
                "equity": self.equity,
                "exposure": self.exposure,
                "drawdown": self.drawdown,
            }
        return out


def _fill_price(bars: Sequence[Bar], index: int, mode: str, use_adjusted: bool) -> float:
    bar = bars[index]
    if mode == "next_open":
        raw = bar.open
        # Keep the fill on the same (adjusted or raw) scale as the close series,
        # otherwise a split makes an entry look like a 4x instant gain.
        if use_adjusted and bar.adj_close is not None and bar.close:
            return raw * (bar.adj_close / bar.close)
        return raw
    return bar.adj_close if (use_adjusted and bar.adj_close is not None) else bar.close


def _mark_price(bar: Bar, use_adjusted: bool) -> float:
    return bar.adj_close if (use_adjusted and bar.adj_close is not None) else bar.close


def run_backtest(
    bars: Sequence[Bar],
    targets: Sequence[float],
    config: BacktestConfig,
    strategy_name: str = "custom",
    params: Optional[Dict[str, object]] = None,
) -> BacktestResult:
    """Simulate `targets` (one target exposure per bar) over `bars`."""
    if len(bars) != len(targets):
        raise ValueError("targets must have one entry per bar")
    if config.execution not in EXECUTION_MODES:
        raise ValueError(f"execution must be one of {EXECUTION_MODES}")
    if len(bars) < 2:
        raise ValueError("need at least two bars to backtest")

    cost_rate = (config.fee_bps + config.slippage_bps) / 10_000.0
    cash = float(config.initial_cash)
    pos = _Position()
    trades: List[dict] = []
    equity_curve: List[float] = []
    exposure_curve: List[float] = []
    total_costs = 0.0
    pending: Optional[float] = None
    current_target = 0.0
    warnings: List[str] = []

    def execute(target: float, price: float, index: int) -> None:
        nonlocal cash, total_costs
        if price <= 0:
            warnings.append(f"skipped fill on {bars[index].date}: non-positive price")
            return
        equity_now = cash + pos.units * price
        if equity_now <= 0:
            warnings.append(f"account wiped out on {bars[index].date}; trading halted")
            return
        desired_units = (target * equity_now) / price
        delta = desired_units - pos.units
        if abs(delta * price) < 1e-9:
            return
        cost = abs(delta * price) * cost_rate
        cash -= delta * price + cost
        total_costs += cost

        crossed = (pos.units > 0 > desired_units) or (pos.units < 0 < desired_units)
        closing = pos.units != 0 and (desired_units == 0 or crossed)
        if closing:
            _close_trade(trades, pos, price, bars[index].date, index, cost)
        elif pos.units != 0 and (desired_units - pos.units) * pos.units > 0:
            # Adding to a position: keep a size-weighted average entry.
            total_units = pos.units + delta
            pos.entry_price = (
                pos.entry_price * pos.units + price * delta
            ) / total_units
            pos.cost_paid += cost
        if desired_units != 0 and (pos.units == 0 or closing):
            pos.entry_price = price
            pos.entry_date = bars[index].date
            pos.entry_index = index
            pos.cost_paid = cost
        pos.units = desired_units
        if desired_units == 0:
            pos.entry_date = None

    for i, bar in enumerate(bars):
        if pending is not None and config.execution != "signal_close":
            execute(pending, _fill_price(bars, i, config.execution, config.use_adjusted), i)
            current_target = pending
            pending = None

        target = float(targets[i])
        if target != current_target:
            if config.execution == "signal_close":
                execute(target, _mark_price(bar, config.use_adjusted), i)
                current_target = target
            else:
                pending = target

        mark = _mark_price(bar, config.use_adjusted)
        equity = cash + pos.units * mark
        equity_curve.append(equity)
        exposure_curve.append((pos.units * mark / equity) if equity else 0.0)

    # Close any open position at the final mark so the trade list is complete.
    if pos.units != 0:
        last = len(bars) - 1
        final_price = _mark_price(bars[last], config.use_adjusted)
        cost = abs(pos.units * final_price) * cost_rate
        cash += pos.units * final_price - cost
        total_costs += cost
        _close_trade(trades, pos, final_price, bars[last].date, last, cost)
        equity_curve[-1] = cash
        exposure_curve[-1] = 0.0
        pos.units = 0.0

    dates = [b.date for b in bars]
    metrics = compute_metrics(
        equity_curve, dates, config.periods_per_year, config.rf_annual
    )
    metrics.update(trade_stats(trades))
    metrics["exposure"] = (
        sum(1 for e in exposure_curve if abs(e) > 1e-9) / len(exposure_curve)
    )
    metrics["total_costs"] = total_costs
    metrics["cost_drag"] = total_costs / config.initial_cash if config.initial_cash else None
    metrics["final_equity"] = equity_curve[-1]

    if metrics["trades"] == 0:
        warnings.append("strategy never opened a position over this window")
    if metrics["trades"] and metrics["trades"] < 10:
        warnings.append(
            f"only {metrics['trades']} closed trade"
            f"{'' if metrics['trades'] == 1 else 's'} - too few to judge the edge"
        )

    return BacktestResult(
        strategy=strategy_name,
        params=params or {},
        dates=dates,
        equity=equity_curve,
        exposure=exposure_curve,
        drawdown=drawdown_series(equity_curve),
        trades=trades,
        metrics=metrics,
        total_costs=total_costs,
        warnings=warnings,
    )


def _close_trade(
    trades: List[dict],
    pos: _Position,
    price: float,
    date: _dt.date,
    index: int,
    exit_cost: float,
) -> None:
    direction = "long" if pos.units > 0 else "short"
    gross = (price - pos.entry_price) * pos.units
    net = gross - pos.cost_paid - exit_cost
    notional = abs(pos.units * pos.entry_price)
    trades.append(
        {
            "direction": direction,
            "entry_date": pos.entry_date.isoformat() if pos.entry_date else None,
            "entry_price": round(pos.entry_price, 6),
            "exit_date": date.isoformat(),
            "exit_price": round(price, 6),
            "units": round(pos.units, 6),
            "pnl": round(net, 4),
            "return_pct": (net / notional) if notional else 0.0,
            "bars_held": index - pos.entry_index,
            "costs": round(pos.cost_paid + exit_cost, 4),
        }
    )
