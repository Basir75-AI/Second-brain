"""Marketstack data access, with on-disk caching and a CSV fallback.

IMPORTANT - read this before trusting a number
----------------------------------------------
The request/response shapes below follow Marketstack's published REST API:
an ``/eod`` endpoint keyed by ``symbols``/``date_from``/``date_to``/``limit``/
``offset``, returning ``{"pagination": {...}, "data": [ {...bars...} ]}``.
They could not be exercised from the machine this file was written on, because
its egress policy blocks both ``api.marketstack.com`` and ``api.apilayer.com``.

So: run ``python cli.py doctor`` first. It prints the raw response and tells
you which transport works. If a field name differs from what is mapped here,
``_parse_bar`` raises with the keys it actually saw rather than guessing.

Two transports are supported because the same key is sold through two front
doors and they authenticate differently:
  * ``native``   -> https://api.marketstack.com/v1/eod?access_key=KEY
  * ``apilayer`` -> https://api.apilayer.com/marketstack/eod  with an
    ``apikey:`` request header
``transport=auto`` tries native first, then apilayer, and remembers the winner.
"""

from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .backtest import Bar
from .config import Settings, get_settings

NATIVE_BASE = "https://api.marketstack.com"
APILAYER_BASE = "https://api.apilayer.com/marketstack"
# Marketstack documents a maximum page size of 1000 rows. If your plan rejects
# it, lower MARKETLAB_PAGE_SIZE in the environment.
MAX_PAGE = 1000


class ProviderError(RuntimeError):
    """Raised for anything that stops us returning honest price data."""


class DataProvider:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.cache_dir = Path(self.settings.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._state_path = self.cache_dir / "_transport.json"

    # -- transport ---------------------------------------------------------

    def _preferred_order(self) -> List[str]:
        if self.settings.transport in ("native", "apilayer"):
            return [self.settings.transport]
        remembered = None
        if self._state_path.is_file():
            try:
                remembered = json.loads(self._state_path.read_text()).get("transport")
            except (ValueError, OSError):
                remembered = None
        order = ["native", "apilayer"]
        if remembered in order:
            order.remove(remembered)
            order.insert(0, remembered)
        return order

    def _remember(self, transport: str) -> None:
        try:
            self._state_path.write_text(json.dumps({"transport": transport}))
        except OSError:
            pass

    def _build_request(
        self, transport: str, endpoint: str, params: Dict[str, object]
    ) -> urllib.request.Request:
        if not self.settings.api_key:
            raise ProviderError(
                "No API key. Put MARKETSTACK_API_KEY=... in stock-platform/.env "
                "(copy .env.example) or export it in your shell."
            )
        query = {k: v for k, v in params.items() if v not in (None, "")}
        headers = {"Accept": "application/json", "User-Agent": "marketlab/0.1"}
        if transport == "native":
            query["access_key"] = self.settings.api_key
            version = self.settings.api_version or "v1"
            url = f"{NATIVE_BASE}/{version}/{endpoint}?" + urllib.parse.urlencode(query)
        else:
            headers["apikey"] = self.settings.api_key
            url = f"{APILAYER_BASE}/{endpoint}?" + urllib.parse.urlencode(query)
        return urllib.request.Request(url, headers=headers)

    def _fetch(self, endpoint: str, params: Dict[str, object]) -> Tuple[dict, str]:
        """Return (payload, transport_used). Raises ProviderError on failure."""
        errors = []
        for transport in self._preferred_order():
            request = self._build_request(transport, endpoint, params)
            try:
                with urllib.request.urlopen(
                    request, timeout=self.settings.request_timeout
                ) as response:
                    body = response.read().decode("utf-8", errors="replace")
                payload = json.loads(body)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:400]
                errors.append(f"{transport}: HTTP {exc.code} {exc.reason} {detail}")
                continue
            except urllib.error.URLError as exc:
                errors.append(f"{transport}: network error - {exc.reason}")
                continue
            except ValueError as exc:
                errors.append(f"{transport}: response was not JSON - {exc}")
                continue

            problem = _payload_error(payload)
            if problem:
                errors.append(f"{transport}: API said - {problem}")
                continue
            self._remember(transport)
            return payload, transport
        raise ProviderError(
            "Could not fetch data from Marketstack.\n  " + "\n  ".join(errors)
        )

    # -- caching -----------------------------------------------------------

    def _cache_path(self, endpoint: str, params: Dict[str, object]) -> Path:
        stable = json.dumps({"e": endpoint, "p": params}, sort_keys=True)
        digest = hashlib.sha256(stable.encode()).hexdigest()[:20]
        return self.cache_dir / f"{endpoint.replace('/', '_')}-{digest}.json"

    def _cached_fetch(
        self, endpoint: str, params: Dict[str, object], use_cache: bool = True
    ) -> dict:
        path = self._cache_path(endpoint, params)
        if use_cache and path.is_file():
            age = time.time() - path.stat().st_mtime
            if age < self.settings.cache_ttl_seconds:
                try:
                    return json.loads(path.read_text())
                except (ValueError, OSError):
                    pass
        payload, transport = self._fetch(endpoint, params)
        payload["_transport"] = transport
        try:
            path.write_text(json.dumps(payload))
        except OSError:
            pass
        return payload

    # -- public API --------------------------------------------------------

    def eod(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        max_bars: int = 5000,
        use_cache: bool = True,
    ) -> List[Bar]:
        """Daily bars for one symbol, oldest first."""
        symbol = symbol.strip().upper()
        collected: List[dict] = []
        offset = 0
        page_size = min(MAX_PAGE, max_bars)
        while len(collected) < max_bars:
            params = {
                "symbols": symbol,
                "date_from": start,
                "date_to": end,
                "limit": page_size,
                "offset": offset,
                "sort": "DESC",
            }
            payload = self._cached_fetch("eod", params, use_cache=use_cache)
            rows = payload.get("data")
            if rows is None:
                raise ProviderError(
                    "Response had no 'data' array. Keys seen: "
                    f"{sorted(payload)}. Run `python cli.py doctor` and send me the output."
                )
            if isinstance(rows, dict):        # single-row responses seen on some plans
                rows = [rows]
            collected.extend(rows)
            pagination = payload.get("pagination") or {}
            total = pagination.get("total")
            count = pagination.get("count", len(rows))
            if not rows or (isinstance(count, int) and count < page_size):
                break
            if isinstance(total, int) and offset + count >= total:
                break
            offset += page_size
        bars = [_parse_bar(row) for row in collected[:max_bars]]
        bars.sort(key=lambda b: b.date)
        deduped: List[Bar] = []
        for bar in bars:
            if deduped and deduped[-1].date == bar.date:
                deduped[-1] = bar
            else:
                deduped.append(bar)
        if not deduped:
            raise ProviderError(
                f"No bars returned for {symbol} between {start or 'the start'} and "
                f"{end or 'today'}. Check the ticker and that your plan covers that range."
            )
        return deduped

    def latest(self, symbols: Sequence[str], use_cache: bool = False) -> List[dict]:
        """Most recent available bar per symbol (end-of-day on most plans)."""
        joined = ",".join(s.strip().upper() for s in symbols if s.strip())
        payload = self._cached_fetch(
            "eod/latest", {"symbols": joined}, use_cache=use_cache
        )
        rows = payload.get("data") or []
        if isinstance(rows, dict):
            rows = [rows]
        out = []
        for row in rows:
            bar = _parse_bar(row)
            out.append({
                "symbol": row.get("symbol", "?"),
                "date": bar.date.isoformat(),
                "open": bar.open, "high": bar.high, "low": bar.low,
                "close": bar.close, "adj_close": bar.adj_close, "volume": bar.volume,
                "change": bar.close - bar.open,
                "change_pct": (bar.close / bar.open - 1.0) if bar.open else None,
            })
        return out

    def doctor(self) -> dict:
        """Probe every transport and report exactly what happened."""
        report = {
            "api_key_present": bool(self.settings.api_key),
            "api_key_fingerprint": (
                self.settings.api_key[:4] + "..." + self.settings.api_key[-4:]
                if self.settings.api_key else None
            ),
            "configured_transport": self.settings.transport,
            "api_version": self.settings.api_version,
            "cache_dir": str(self.cache_dir),
            "probes": [],
        }
        if not self.settings.api_key:
            report["verdict"] = "No API key configured."
            return report
        for transport in ("native", "apilayer"):
            probe = {"transport": transport}
            try:
                request = self._build_request(
                    transport, "eod", {"symbols": "AAPL", "limit": 1}
                )
                probe["url"] = request.full_url.replace(self.settings.api_key, "***")
                with urllib.request.urlopen(
                    request, timeout=self.settings.request_timeout
                ) as response:
                    body = response.read().decode("utf-8", errors="replace")
                probe["http_status"] = 200
                probe["body_preview"] = body[:600]
                payload = json.loads(body)
                problem = _payload_error(payload)
                if problem:
                    probe["ok"] = False
                    probe["error"] = problem
                else:
                    probe["ok"] = True
                    rows = payload.get("data") or []
                    probe["row_keys"] = sorted(rows[0]) if rows else []
                    probe["pagination"] = payload.get("pagination")
            except urllib.error.HTTPError as exc:
                probe["ok"] = False
                probe["http_status"] = exc.code
                probe["error"] = f"{exc.reason}"
                probe["body_preview"] = exc.read().decode("utf-8", errors="replace")[:600]
            except Exception as exc:  # noqa: BLE001 - the whole point is to report it
                probe["ok"] = False
                probe["error"] = f"{type(exc).__name__}: {exc}"
            report["probes"].append(probe)
        working = [p["transport"] for p in report["probes"] if p.get("ok")]
        report["verdict"] = (
            f"Working transport(s): {', '.join(working)}"
            if working else "No transport worked - see the probe errors above."
        )
        return report


def _payload_error(payload: object) -> Optional[str]:
    """Marketstack and apilayer both return errors inside a 200 response."""
    if not isinstance(payload, dict):
        return f"expected a JSON object, got {type(payload).__name__}"
    error = payload.get("error")
    if isinstance(error, dict):
        return error.get("message") or error.get("info") or json.dumps(error)[:300]
    if isinstance(error, str) and error:
        return error
    if "message" in payload and "data" not in payload:
        return str(payload["message"])
    return None


def _num(row: dict, *names: str) -> Optional[float]:
    for name in names:
        if name in row and row[name] is not None:
            try:
                return float(row[name])
            except (TypeError, ValueError):
                continue
    return None


def _parse_bar(row: dict) -> Bar:
    if not isinstance(row, dict):
        raise ProviderError(f"expected a bar object, got {type(row).__name__}")
    raw_date = row.get("date") or row.get("datetime") or row.get("trade_date")
    if not raw_date:
        raise ProviderError(f"bar has no date field. Keys: {sorted(row)}")
    date = _parse_date(str(raw_date))
    close = _num(row, "close", "last", "adj_close")
    if close is None:
        raise ProviderError(
            f"bar has no usable close price. Keys seen: {sorted(row)}. "
            "The API shape may have changed - run `python cli.py doctor`."
        )
    open_ = _num(row, "open") or close
    high = _num(row, "high") or max(open_, close)
    low = _num(row, "low") or min(open_, close)
    return Bar(
        date=date,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=_num(row, "volume", "adj_volume") or 0.0,
        adj_close=_num(row, "adj_close"),
    )


def _parse_date(value: str) -> _dt.date:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return _dt.datetime.fromisoformat(text).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return _dt.datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    raise ProviderError(f"could not parse date '{value}'")


# -- CSV fallback ----------------------------------------------------------

def load_csv(path: str | Path) -> List[Bar]:
    """Load bars from a CSV so the platform works with no API at all.

    Accepts the common header spellings: date/Date/timestamp,
    open/high/low/close/volume, and adj_close/'Adj Close'.
    """
    path = Path(path)
    if not path.is_file():
        raise ProviderError(f"CSV not found: {path}")
    bars: List[Bar] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ProviderError(f"{path} has no header row")
        for raw in reader:
            row = {(k or "").strip().lower().replace(" ", "_"): v for k, v in raw.items()}
            if not any(row.values()):
                continue
            bars.append(_parse_bar(row))
    if not bars:
        raise ProviderError(f"{path} contained no rows")
    bars.sort(key=lambda b: b.date)
    return bars


def slice_bars(
    bars: Sequence[Bar], start: Optional[str], end: Optional[str]
) -> List[Bar]:
    lo = _parse_date(start) if start else None
    hi = _parse_date(end) if end else None
    return [
        b for b in bars
        if (lo is None or b.date >= lo) and (hi is None or b.date <= hi)
    ]
