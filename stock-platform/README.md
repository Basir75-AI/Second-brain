# marketlab

A personal stock analysis and strategy backtesting platform. Pure Python standard
library — no pip install, no build step, no CDN. It runs a local web UI and a CLI.

> **Scope note.** This directory is a standalone application. It has nothing to do with
> the agency SOP wiki in the rest of this repository and does not follow `CLAUDE.md`'s
> wiki schema.

---

## Read this first: the API is not verified

The Marketstack client here was written against the documented REST shape (`/eod` with
`symbols`, `date_from`, `date_to`, `limit`, `offset`, returning
`{"pagination": …, "data": [...]}`). **It has never been run against the live API.** The
machine it was built on blocks outbound connections to both `api.marketstack.com` and
`api.apilayer.com` at the network policy level, so no request could be made.

Everything downstream of the client — indicators, the backtest engine, metrics, the
sweep, the UI — *is* verified, by 44 unit tests and by hand-checked worked examples.

So the first thing to run is:

```bash
cd stock-platform
cp .env.example .env          # then paste your key into MARKETSTACK_API_KEY
python3 cli.py doctor
```

`doctor` probes both transports and prints the HTTP status, the raw response body, and
the exact field names that came back. If a field name differs from what
`provider._parse_bar` expects, the parser raises an error naming the keys it actually
saw rather than silently producing a wrong number. Send me that output and the fix is
one line.

Two further things I could not check and you should:

- **Which host your key belongs to.** A key bought through apilayer's marketplace
  authenticates with an `apikey:` header against `api.apilayer.com/marketstack`; a key
  bought direct from marketstack.com uses an `access_key=` query parameter against
  `api.marketstack.com`. `transport=auto` tries both.
- **What your plan includes.** Free tiers are typically end-of-day only, with a monthly
  request cap, a limited history window, and no `adj_close`. Intraday, and therefore
  anything genuinely "live", is usually a paid feature. I can't see your plan — check
  your dashboard. The platform caches every response to disk precisely because that cap
  is easy to burn.

Your key was shared in a chat message, which means it exists in that transcript.
Rotating it in your Marketstack dashboard is cheap insurance.

---

## Run it

```bash
python3 cli.py serve          # web UI at http://127.0.0.1:8787
```

No API key yet? Everything works on synthetic data:

```bash
python3 cli.py compare DEMO --source demo --start 2021-01-01
```

Or on a CSV you already have (`date,open,high,low,close,adj close,volume`):

```bash
python3 cli.py compare MYDATA --source csv --csv ~/prices/aapl.csv
```

### CLI

```bash
python3 cli.py doctor                       # is the key working, and what shape is the data
python3 cli.py strategies                   # list strategies and their parameters
python3 cli.py quote AAPL MSFT NVDA
python3 cli.py analyze AAPL --start 2020-01-01
python3 cli.py compare AAPL --start 2015-01-01 --rank-by sharpe
python3 cli.py backtest AAPL \
    -s sma_crossover:fast=20,slow=100 \
    -s rsi_reversion:period=14,oversold=25 \
    --trades 10
python3 cli.py sweep AAPL -s sma_crossover -g fast=10,20,30,50 -g slow=100,150,200
```

Every command takes `--fee-bps`, `--slippage-bps`, `--execution`, `--cash`, `--rf`,
`--start`, `--end`, `--source`, `--no-cache`.

### Tests

```bash
python3 -m unittest discover -s tests -v
```

GitHub Actions runs the same suite on Python 3.9 through 3.13, plus a smoke job
that drives the CLI and the HTTP server on synthetic data — see
`.github/workflows/tests.yml`. It only fires when something under
`stock-platform/` changes, so wiki edits don't trigger it.

---

## What it does

**Analysis.** Last close, RSI(14), distance from the 50- and 200-day moving averages,
trailing 1/3/6/12-month returns, 52-week range, annualised volatility, current and worst
drawdown. A price chart with moving averages and a Bollinger band. These are
descriptive statistics of past prices, not forecasts.

**Backtesting.** Sixteen strategies, all runnable head to head on the same bars with the
same cost model, always against buy-and-hold:

| Key | What it does |
|---|---|
| `buy_and_hold` | The benchmark every other row has to beat. |
| `sma_crossover` | Long while the fast SMA is above the slow SMA. |
| `ema_crossover` | Same, with exponential averages. |
| `trend_filter` | Long while price is above its own moving average (the 200-day rule). |
| `rsi_reversion` | Buy oversold, sell into the bounce. |
| `macd_cross` | Long while MACD is above its signal line. |
| `bollinger_reversion` | Buy the lower band, exit at the middle. |
| `bollinger_breakout` | Buy through the upper band, exit at the middle. |
| `donchian` | Buy an N-bar high, exit on an M-bar low. |
| `momentum` | Long while the trailing N-bar return clears a threshold. |
| `dual_momentum_filter` | Momentum, but only above a long trend filter. |
| `atr_trailing_stop` | Break out to an N-bar high, then ride it behind an ATR-width trailing stop. |
| `keltner_breakout` | Buy through an ATR-width channel, exit at its middle. |
| `stochastic_reversion` | Buy an oversold stochastic that has already turned up. |
| `vol_target` | Size the position so risk stays constant — full when calm, a fraction when wild. |
| `rsi_pullback` | Buy a short-term dip, but only while the long trend holds. |

Most take an `allow_short` flag. `vol_target` is the only one that sizes below a full
position; its exposure is capped at 1.0 because nothing here models margin or borrowing,
and its rebalance band exists to stop a continuously varying target from being eaten
alive by costs.

**Metrics.** Total return, CAGR, annualised volatility, Sharpe, Sortino, max drawdown,
Calmar, win rate, profit factor, expectancy, average bars held, time in market, total
costs paid, and the full trade list.

**Parameter sweep.** Grid-search on the first 70% of the history, then score the winner
on the 30% it never saw. The gap between the in-sample and out-of-sample columns is the
size of the curve fit.

---

## How the backtest avoids fooling you

These are the choices that decide whether a backtest means anything.

- **No lookahead, enforced by test.** A strategy sees bars `0..i` and sets a target for
  bar `i`; the engine fills it on a *later* bar. `test_no_strategy_can_see_the_future`
  re-runs every strategy on truncated history and asserts the signals match the
  full-history prefix, so a future-peeking indicator fails the build.
- **Execution is explicit.** `next_open` (default) fills at the next bar's open — you
  saw the close, you traded the next morning. `next_close` fills at the next close.
  `signal_close` fills at the close you just decided on, which is what most vectorised
  backtests quietly assume; it is there so you can measure how much that assumption is
  worth.
- **Costs are charged on every trade**, both ways, on notional: 5 bps commission + 5 bps
  slippage by default. Turn them to zero and watch the high-frequency strategies
  "improve" — that gap is the cost of churn.
- **Position sizing is fractional equity**, so results compound rather than depending on
  share counts.
- **Splits and dividends** are handled by using `adj_close` when the feed provides it;
  the entry fill is rescaled to the same adjusted basis so a split doesn't read as an
  instant gain. If the feed has no `adj_close`, the UI says so.

### What it still does not model

Borrow costs and hard-to-borrow constraints on shorts; taxes; the bid-ask spread beyond
the flat slippage figure; market impact; dividends when the feed has no adjusted close;
survivorship bias if you only test tickers that still exist; and the plain fact that a
fill you assumed might not have happened. Short results in particular are optimistic.

And the structural one: a strategy that wins on one ticker over one window usually won
by luck. The sweep's out-of-sample column, and whether *neighbouring* parameters also
work, tell you more than any single headline number.

---

## Layout

```
cli.py                  command line entry point
marketlab/
  config.py             settings from the environment / .env
  provider.py           Marketstack client, disk cache, CSV loader   <- the unverified part
  datasource.py         api | csv | demo dispatch
  indicators.py         SMA, EMA, RSI, MACD, Bollinger, Keltner, stochastic,
                        Donchian, ROC, ATR, realised volatility
  strategies.py         the strategy registry
  backtest.py           the engine
  metrics.py            performance statistics
  runner.py             comparison, ranking, parameter sweep
  server.py             stdlib HTTP server + JSON API
web/                    the UI (hand-built SVG charts, no dependencies)
tests/                  56 unit tests
data/cache/             cached API responses (gitignored)
```

### HTTP API

| Route | Purpose |
|---|---|
| `GET /api/health` | is a key configured |
| `GET /api/doctor` | probe the API and report the raw response |
| `GET /api/strategies` | registry, with parameter schemas |
| `GET /api/quote?symbols=AAPL,MSFT` | latest available bar |
| `GET /api/analysis?symbol=AAPL&start=…` | snapshot + chart series |
| `POST /api/backtest` | run strategies, ranked, with equity curves and trades |
| `POST /api/sweep` | in-sample grid search, out-of-sample scoring |

The server binds to `127.0.0.1` and holds your API key in its environment. Don't expose
that port.

---

Backtests are simulations of the past. Nothing here is investment advice.
