#!/usr/bin/env python3
"""marketlab command line.

    python cli.py doctor                      # does the API key work? what shape?
    python cli.py quote AAPL MSFT
    python cli.py analyze AAPL --start 2020-01-01
    python cli.py compare AAPL --start 2015-01-01
    python cli.py backtest AAPL -s sma_crossover:fast=20,slow=100 -s rsi_reversion
    python cli.py sweep AAPL -s sma_crossover -g fast=10,20,30,50 -g slow=100,150,200
    python cli.py serve                       # the web UI

Add --source demo to any command to use seeded synthetic data (no API key, no
network). Add --source csv --csv path/to/file.csv to use your own file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from marketlab import strategies as strat            # noqa: E402
from marketlab.backtest import EXECUTION_MODES, BacktestConfig  # noqa: E402
from marketlab.datasource import load_bars           # noqa: E402
from marketlab.provider import DataProvider, ProviderError      # noqa: E402
from marketlab.runner import RANKABLE, price_analysis, rank, run_strategies, sweep  # noqa: E402
from marketlab.server import serve                   # noqa: E402


# -- formatting ------------------------------------------------------------

def pct(value, digits: int = 2) -> str:
    return "—" if value is None else f"{value * 100:.{digits}f}%"


def num(value, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def table(headers, rows, aligns=None) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    aligns = aligns or ["<"] + [">"] * (len(headers) - 1)
    def line(cells):
        return "  ".join(
            f"{str(c):{aligns[i]}{widths[i]}}" for i, c in enumerate(cells)
        )
    out = [line(headers), "  ".join("-" * w for w in widths)]
    out.extend(line(r) for r in rows)
    return "\n".join(out)


def parse_strategy_spec(text: str) -> dict:
    """`sma_crossover:fast=20,slow=100,allow_short=1` -> spec dict."""
    key, _, param_text = text.partition(":")
    key = key.strip()
    if key not in strat.REGISTRY:
        raise SystemExit(
            f"unknown strategy '{key}'.\nAvailable: {', '.join(sorted(strat.REGISTRY))}"
        )
    params = {}
    for chunk in param_text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, _, value = chunk.partition("=")
        if not value:
            raise SystemExit(f"bad parameter '{chunk}' - use name=value")
        params[name.strip()] = value.strip()
    return {"key": key, "params": params}


def parse_grid(entries) -> dict:
    grid = {}
    for entry in entries or []:
        name, _, values = entry.partition("=")
        if not values:
            raise SystemExit(f"bad grid entry '{entry}' - use name=1,2,3")
        parsed = []
        for raw in values.split(","):
            raw = raw.strip()
            parsed.append(float(raw) if "." in raw else int(raw))
        grid[name.strip()] = parsed
    return grid


def add_data_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", default="api", choices=("api", "csv", "demo"))
    parser.add_argument("--csv", dest="csv_path", help="path to a CSV of bars")
    parser.add_argument("--start", help="YYYY-MM-DD")
    parser.add_argument("--end", help="YYYY-MM-DD")
    parser.add_argument("--max-bars", type=int, default=5000)
    parser.add_argument("--no-cache", action="store_true", help="bypass the disk cache")


def add_backtest_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cash", type=float, default=10_000.0)
    parser.add_argument("--fee-bps", type=float, default=5.0,
                        help="commission in basis points per side (5 = 0.05%%)")
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--execution", default="next_open", choices=EXECUTION_MODES)
    parser.add_argument("--rf", type=float, default=0.0,
                        help="annual risk-free rate for Sharpe, e.g. 0.04")
    parser.add_argument("--raw-prices", action="store_true",
                        help="use unadjusted closes (excludes dividends)")


def bars_for(args):
    return load_bars(
        source=args.source,
        symbol=getattr(args, "symbol", "AAPL"),
        start=args.start,
        end=args.end,
        csv_path=args.csv_path,
        max_bars=args.max_bars,
        use_cache=not args.no_cache,
    )


def config_for(args) -> BacktestConfig:
    return BacktestConfig(
        initial_cash=args.cash, fee_bps=args.fee_bps, slippage_bps=args.slippage_bps,
        execution=args.execution, rf_annual=args.rf, use_adjusted=not args.raw_prices,
    )


def banner(meta: dict) -> None:
    print(f"\n{meta['symbol']}  {meta['first_date']} → {meta['last_date']}  "
          f"({meta['bars']} bars, source: {meta['source']})")
    if meta.get("synthetic"):
        print("  !! SYNTHETIC DATA - a seeded random walk, not a real security.")
    if meta.get("adjustment_warning"):
        print(f"  ! {meta['adjustment_warning']}")


# -- commands --------------------------------------------------------------

def cmd_doctor(args) -> int:
    report = DataProvider().doctor()
    print(json.dumps(report, indent=2))
    print("\n" + report["verdict"])
    return 0 if "Working" in report["verdict"] else 1


def cmd_quote(args) -> int:
    rows = DataProvider().latest(args.symbols)
    if not rows:
        print("no quotes returned")
        return 1
    print(table(
        ["symbol", "date", "open", "high", "low", "close", "change%", "volume"],
        [[r["symbol"], r["date"], num(r["open"]), num(r["high"]), num(r["low"]),
          num(r["close"]), pct(r["change_pct"]), f"{r['volume']:,.0f}"] for r in rows],
    ))
    print("\nMarketstack's standard feed is end-of-day: this is the last completed "
          "session, not a live tick.")
    return 0


def cmd_analyze(args) -> int:
    bars, meta = bars_for(args)
    banner(meta)
    a = price_analysis(bars)
    print(table(["measure", "value"], [
        ["last close", num(a["last_close"])],
        ["RSI(14)", num(a["rsi_14"], 1)],
        ["vs SMA(50)", pct(a["pct_from_sma_50"])],
        ["vs SMA(200)", pct(a["pct_from_sma_200"])],
        ["return 1m / 3m", f"{pct(a['return_1m'])} / {pct(a['return_3m'])}"],
        ["return 6m / 1y", f"{pct(a['return_6m'])} / {pct(a['return_1y'])}"],
        ["52w high / low", f"{num(a['high_52w'])} / {num(a['low_52w'])}"],
        ["from 52w high", pct(a["pct_from_52w_high"])],
        ["annualised vol", pct(a["volatility_annualised"], 1)],
        ["current drawdown", pct(a["current_drawdown"])],
        ["worst drawdown in window", pct(a["max_drawdown_in_window"])],
        ["adjusted prices present", "yes" if a["has_adjusted_prices"] else "no"],
    ]))
    print("\nThese are descriptive statistics of past prices. They are not a forecast.")
    return 0


def _print_ranking(rows, metric: str) -> None:
    print(table(
        ["#", "strategy", "CAGR", "total", "Sharpe", "Sortino", "MaxDD",
         "Calmar", "trades", "win%", "PF", "expos."],
        [[r["rank"], r["strategy"], pct(r["metrics"]["cagr"], 1),
          pct(r["metrics"]["total_return"], 1), num(r["metrics"]["sharpe"]),
          num(r["metrics"]["sortino"]), pct(r["metrics"]["max_drawdown"], 1),
          num(r["metrics"]["calmar"]), r["metrics"]["trades"],
          pct(r["metrics"]["win_rate"], 0), num(r["metrics"]["profit_factor"]),
          pct(r["metrics"]["exposure"], 0)] for r in rows],
    ))
    print(f"\nRanked by {metric}. Costs are included. Past results are not a forecast.")


def cmd_compare(args) -> int:
    bars, meta = bars_for(args)
    banner(meta)
    specs = [{"key": k} for k in strat.REGISTRY if k != "buy_and_hold"]
    results = run_strategies(bars, specs, config_for(args))
    _print_ranking(rank(results, args.rank_by), args.rank_by)
    warnings = {w for r in results for w in r.warnings}
    for w in sorted(warnings):
        print(f"  ! {w}")
    return 0


def cmd_backtest(args) -> int:
    bars, meta = bars_for(args)
    banner(meta)
    specs = [parse_strategy_spec(s) for s in args.strategy]
    results = run_strategies(bars, specs, config_for(args))
    _print_ranking(rank(results, args.rank_by), args.rank_by)
    for result in results:
        if result.params.get("_key") == "buy_and_hold" and not any(
            s["key"] == "buy_and_hold" for s in specs
        ):
            continue
        params = {k: v for k, v in result.params.items() if k != "_key"}
        print(f"\n{result.strategy}  {params}")
        for w in result.warnings:
            print(f"  ! {w}")
        if args.trades and result.trades:
            shown = result.trades[: args.trades]
            print(table(
                ["dir", "entry", "price", "exit", "price", "bars", "return", "pnl"],
                [[t["direction"], t["entry_date"], num(t["entry_price"]),
                  t["exit_date"], num(t["exit_price"]), t["bars_held"],
                  pct(t["return_pct"]), num(t["pnl"])] for t in shown],
            ))
            if len(result.trades) > len(shown):
                print(f"  ... {len(result.trades) - len(shown)} more trades")
    return 0


def cmd_sweep(args) -> int:
    bars, meta = bars_for(args)
    banner(meta)
    grid = parse_grid(args.grid)
    if not grid:
        raise SystemExit("sweep needs at least one -g name=1,2,3")
    report = sweep(bars, args.strategy, grid, config_for(args),
                   metric=args.metric, in_sample_fraction=args.in_sample)
    print(f"\n{report['strategy']}: {report['combinations_tested']} combinations, "
          f"split at {report['split_date']} "
          f"({report['in_sample_bars']} in-sample / {report['out_of_sample_bars']} out)")
    rows = []
    for r in report["results"][: args.top]:
        params = ", ".join(f"{k}={v}" for k, v in r["params"].items() if k != "allow_short")
        ins, oos = r["in_sample"], r.get("out_of_sample") or {}
        rows.append([
            params, num(ins[args.metric]), num(oos.get(args.metric)),
            pct(ins["cagr"], 1), pct(oos.get("cagr"), 1),
            pct(ins["max_drawdown"], 1), pct(oos.get("max_drawdown"), 1),
            ins["trades"],
        ])
    print(table(
        ["params", f"IS {args.metric}", f"OOS {args.metric}", "IS CAGR", "OOS CAGR",
         "IS MaxDD", "OOS MaxDD", "IS trades"], rows,
    ))
    print(f"\n{report['caveat']}")
    return 0


def cmd_strategies(args) -> int:
    for s in strat.REGISTRY.values():
        params = ", ".join(f"{p.name}={p.default}" for p in s.params) or "none"
        print(f"\n{s.key}  [{s.family}]\n  {s.summary}\n  params: {params}")
    return 0


def cmd_serve(args) -> int:
    serve(args.host, args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subs = parser.add_subparsers(dest="command", required=True)

    subs.add_parser("doctor", help="probe the API and print what came back").set_defaults(func=cmd_doctor)
    subs.add_parser("strategies", help="list strategies and their parameters").set_defaults(func=cmd_strategies)

    p = subs.add_parser("quote", help="latest available bar per symbol")
    p.add_argument("symbols", nargs="+")
    p.set_defaults(func=cmd_quote)

    p = subs.add_parser("analyze", help="descriptive snapshot of one symbol")
    p.add_argument("symbol")
    add_data_args(p)
    p.set_defaults(func=cmd_analyze)

    p = subs.add_parser("compare", help="backtest every strategy on its defaults")
    p.add_argument("symbol")
    add_data_args(p)
    add_backtest_args(p)
    p.add_argument("--rank-by", default="sharpe", choices=RANKABLE)
    p.set_defaults(func=cmd_compare)

    p = subs.add_parser("backtest", help="backtest specific strategies")
    p.add_argument("symbol")
    p.add_argument("-s", "--strategy", action="append", required=True,
                   help="key[:param=value,...], repeatable")
    add_data_args(p)
    add_backtest_args(p)
    p.add_argument("--rank-by", default="sharpe", choices=RANKABLE)
    p.add_argument("--trades", type=int, default=0, metavar="N",
                   help="also print the first N trades per strategy")
    p.set_defaults(func=cmd_backtest)

    p = subs.add_parser("sweep", help="grid-search parameters, report out-of-sample")
    p.add_argument("symbol")
    p.add_argument("-s", "--strategy", required=True)
    p.add_argument("-g", "--grid", action="append", required=True,
                   help="name=1,2,3 - repeatable")
    add_data_args(p)
    add_backtest_args(p)
    p.add_argument("--metric", default="sharpe", choices=RANKABLE)
    p.add_argument("--in-sample", type=float, default=0.7)
    p.add_argument("--top", type=int, default=12)
    p.set_defaults(func=cmd_sweep)

    p = subs.add_parser("serve", help="run the web UI")
    p.add_argument("--host", default=None)
    p.add_argument("--port", type=int, default=None)
    p.set_defaults(func=cmd_serve)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ProviderError as exc:
        print(f"\ndata error: {exc}\n", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
