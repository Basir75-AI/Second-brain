"""One place that turns a request description into bars.

Three sources, so the platform is useful whether or not the API answers:
  * ``api``  - Marketstack end-of-day, cached on disk.
  * ``csv``  - any CSV you already have (see provider.load_csv).
  * ``demo`` - a deterministic synthetic random walk. NOT REAL DATA. It exists
    so you can exercise the engine and the UI with no API key and no network.
"""

from __future__ import annotations

import datetime as _dt
import random
from typing import List, Optional, Sequence, Tuple

from .backtest import Bar
from .provider import DataProvider, ProviderError, load_csv, slice_bars

DEMO_SYMBOL = "SYNTHETIC-DEMO"


def synthetic_bars(
    n: int = 1500, seed: int = 7, start_price: float = 100.0,
    start_date: _dt.date | None = None,
) -> List[Bar]:
    """A seeded random walk. Deterministic, and deliberately not any real stock."""
    rng = random.Random(seed)
    bars: List[Bar] = []
    price = start_price
    day = start_date or (_dt.date.today() - _dt.timedelta(days=int(n * 1.45)))
    while day.weekday() > 4:
        day += _dt.timedelta(days=1)
    for _ in range(n):
        open_ = price
        price = max(1.0, price * (1 + 0.0003 + rng.gauss(0, 0.012)))
        high = max(open_, price) * (1 + abs(rng.gauss(0, 0.003)))
        low = min(open_, price) * (1 - abs(rng.gauss(0, 0.003)))
        bars.append(Bar(day, open_, high, low, price, 1_000_000))
        day += _dt.timedelta(days=1)
        while day.weekday() > 4:
            day += _dt.timedelta(days=1)
    return bars


def load_bars(
    source: str = "api",
    symbol: str = "AAPL",
    start: Optional[str] = None,
    end: Optional[str] = None,
    csv_path: Optional[str] = None,
    max_bars: int = 5000,
    use_cache: bool = True,
    provider: Optional[DataProvider] = None,
) -> Tuple[List[Bar], dict]:
    """Return (bars, meta). `meta` always says where the numbers came from."""
    source = (source or "api").lower()
    if source == "demo":
        bars = slice_bars(synthetic_bars(), start, end)
        meta = {
            "source": "demo",
            "symbol": DEMO_SYMBOL,
            "synthetic": True,
            "note": "SYNTHETIC DATA - a seeded random walk, not a real security. "
                    "Nothing here says anything about any real market.",
        }
    elif source == "csv":
        if not csv_path:
            raise ProviderError("source=csv needs a csv path")
        bars = slice_bars(load_csv(csv_path), start, end)
        meta = {
            "source": "csv", "symbol": symbol or csv_path, "synthetic": False,
            "note": f"Loaded from {csv_path}. Accuracy is whatever that file holds.",
        }
    elif source == "api":
        provider = provider or DataProvider()
        bars = provider.eod(symbol, start, end, max_bars=max_bars, use_cache=use_cache)
        meta = {
            "source": "marketstack", "symbol": symbol.upper(), "synthetic": False,
            "note": "End-of-day bars from Marketstack.",
        }
    else:
        raise ProviderError(f"unknown source '{source}' (use api, csv or demo)")

    if len(bars) < 2:
        raise ProviderError(
            f"only {len(bars)} bar(s) after filtering - widen the date range"
        )
    meta.update({
        "bars": len(bars),
        "first_date": bars[0].date.isoformat(),
        "last_date": bars[-1].date.isoformat(),
        "adjusted_prices_available": any(b.adj_close is not None for b in bars),
    })
    if not meta["adjusted_prices_available"] and source != "demo":
        meta["adjustment_warning"] = (
            "No adj_close in this data, so returns are on raw prices: dividends are "
            "excluded and any split will read as a price jump."
        )
    return bars, meta
