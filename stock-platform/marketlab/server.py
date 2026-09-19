"""A dependency-free JSON API plus the static web UI.

Binds to 127.0.0.1 by default. Your API key sits in this process's environment,
so do not expose this port to a network you do not control.
"""

from __future__ import annotations

import json
import mimetypes
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

from . import strategies as strat
from .backtest import EXECUTION_MODES, BacktestConfig
from .config import WEB_DIR, get_settings
from .datasource import load_bars
from .provider import DataProvider, ProviderError
from .runner import indicator_overlays, price_analysis, rank, run_strategies, sweep

MAX_BODY = 1_000_000
# Must stay comfortably above the strategy registry: the UI lets you tick every
# strategy at once, and a cap below that count rejects the request outright.
# `test_strategy_cap_covers_the_registry` holds this to the registry's size.
MAX_STRATEGIES = 24


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _config_from(payload: Dict[str, Any]) -> BacktestConfig:
    execution = str(payload.get("execution", "next_open"))
    if execution not in EXECUTION_MODES:
        raise ApiError(f"execution must be one of {', '.join(EXECUTION_MODES)}")
    try:
        cfg = BacktestConfig(
            initial_cash=float(payload.get("initial_cash", 10_000)),
            fee_bps=float(payload.get("fee_bps", 5)),
            slippage_bps=float(payload.get("slippage_bps", 5)),
            execution=execution,
            periods_per_year=int(payload.get("periods_per_year", 252)),
            rf_annual=float(payload.get("rf_annual", 0.0)),
            use_adjusted=bool(payload.get("use_adjusted", True)),
        )
    except (TypeError, ValueError) as exc:
        raise ApiError(f"bad backtest settings: {exc}") from exc
    if cfg.initial_cash <= 0:
        raise ApiError("initial_cash must be positive")
    if cfg.fee_bps < 0 or cfg.slippage_bps < 0:
        raise ApiError("costs cannot be negative")
    return cfg


def _bars_from(payload: Dict[str, Any]):
    try:
        return load_bars(
            source=payload.get("source", "api"),
            symbol=str(payload.get("symbol", "AAPL")),
            start=payload.get("start") or None,
            end=payload.get("end") or None,
            csv_path=payload.get("csv_path") or None,
            max_bars=int(payload.get("max_bars", 5000)),
            use_cache=bool(payload.get("use_cache", True)),
        )
    except ProviderError as exc:
        raise ApiError(str(exc), status=502) from exc


class Handler(BaseHTTPRequestHandler):
    server_version = "marketlab/0.1"

    # -- plumbing ----------------------------------------------------------

    def log_message(self, fmt: str, *args) -> None:  # quieter console
        print(f"  {self.address_string()} {fmt % args}")

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.is_file():
            self._send_json({"error": "not found"}, 404)
            return
        data = path.read_bytes()
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ApiError("request body too large", 413)
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except ValueError as exc:
            raise ApiError(f"body was not valid JSON: {exc}") from exc

    # -- routes ------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        parsed = urlparse(self.path)
        route = parsed.path
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        try:
            if route == "/" or route == "/index.html":
                self._send_file(WEB_DIR / "index.html")
            elif route.startswith("/static/"):
                name = Path(route[len("/static/"):]).name   # no traversal
                self._send_file(WEB_DIR / name)
            elif route == "/api/health":
                settings = get_settings()
                self._send_json({
                    "ok": True,
                    "api_key_configured": settings.has_key,
                    "transport": settings.transport,
                    "execution_modes": list(EXECUTION_MODES),
                })
            elif route == "/api/strategies":
                self._send_json({"strategies": strat.list_strategies()})
            elif route == "/api/doctor":
                self._send_json(DataProvider().doctor())
            elif route == "/api/quote":
                symbols = [s for s in (query.get("symbols", "")).split(",") if s.strip()]
                if not symbols:
                    raise ApiError("pass ?symbols=AAPL,MSFT")
                try:
                    rows = DataProvider().latest(symbols)
                except ProviderError as exc:
                    raise ApiError(str(exc), 502) from exc
                self._send_json({
                    "quotes": rows,
                    "note": "Marketstack's standard feed is end-of-day, so the "
                            "'latest' bar is the last completed session, not a live tick.",
                })
            elif route == "/api/analysis":
                bars, meta = _bars_from(query)
                self._send_json({
                    "meta": meta,
                    "analysis": price_analysis(bars),
                    "chart": indicator_overlays(bars),
                })
            else:
                self._send_json({"error": f"no route {route}"}, 404)
        except ApiError as exc:
            self._send_json({"error": str(exc)}, exc.status)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        try:
            payload = self._read_json()
            if route == "/api/backtest":
                self._send_json(self._backtest(payload))
            elif route == "/api/sweep":
                self._send_json(self._sweep(payload))
            else:
                self._send_json({"error": f"no route {route}"}, 404)
        except ApiError as exc:
            self._send_json({"error": str(exc)}, exc.status)
        except (ValueError, KeyError) as exc:
            self._send_json({"error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    # -- handlers ----------------------------------------------------------

    def _backtest(self, payload: Dict[str, Any]) -> dict:
        bars, meta = _bars_from(payload)
        config = _config_from(payload)
        specs = payload.get("strategies") or [{"key": "sma_crossover"}]
        if not isinstance(specs, list):
            raise ApiError("'strategies' must be a list")
        if len(specs) > MAX_STRATEGIES:
            raise ApiError(
                f"'strategies' must be a list of at most {MAX_STRATEGIES} entries; "
                f"got {len(specs)}"
            )
        results = run_strategies(
            bars, specs, config, include_benchmark=payload.get("include_benchmark", True)
        )
        metric = payload.get("rank_by", "sharpe")
        include_series = bool(payload.get("include_series", True))
        return {
            "meta": meta,
            "config": {
                "initial_cash": config.initial_cash, "fee_bps": config.fee_bps,
                "slippage_bps": config.slippage_bps, "execution": config.execution,
                "rf_annual": config.rf_annual, "use_adjusted": config.use_adjusted,
            },
            "ranking": rank(results, metric),
            "results": [r.to_dict(include_series=include_series) for r in results],
            "chart": indicator_overlays(bars) if include_series else None,
        }

    def _sweep(self, payload: Dict[str, Any]) -> dict:
        bars, meta = _bars_from(payload)
        config = _config_from(payload)
        key = payload.get("key") or payload.get("strategy")
        if not key:
            raise ApiError("sweep needs a strategy 'key'")
        grid = payload.get("grid") or {}
        if not isinstance(grid, dict) or not grid:
            raise ApiError("sweep needs a non-empty 'grid', e.g. {\"fast\":[10,20]}")
        result = sweep(
            bars, key, grid, config,
            metric=payload.get("metric", "sharpe"),
            in_sample_fraction=float(payload.get("in_sample_fraction", 0.7)),
        )
        result["meta"] = meta
        return result


def serve(host: str | None = None, port: int | None = None) -> None:
    settings = get_settings()
    host = host or settings.host
    port = port or settings.port
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"\n  marketlab running at http://{host}:{port}")
    print(f"  API key configured: {'yes' if settings.has_key else 'NO - set MARKETSTACK_API_KEY'}")
    print("  Ctrl-C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")
    finally:
        httpd.server_close()
