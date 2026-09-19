"""Test suite. Run with:  python -m unittest discover -s tests -v"""

from __future__ import annotations

import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marketlab import indicators as ind
from marketlab import strategies as strat
from marketlab.backtest import Bar, BacktestConfig, run_backtest
from marketlab.datasource import synthetic_bars
from marketlab.metrics import compute_metrics, max_drawdown, trade_stats
from marketlab.provider import ProviderError, _parse_bar, _parse_date, _payload_error, load_csv
from marketlab.runner import rank, run_strategies, sweep
from marketlab.server import MAX_STRATEGIES


def make_bars(closes, opens=None):
    day = dt.date(2024, 1, 1)
    bars = []
    for i, close in enumerate(closes):
        open_ = opens[i] if opens else (closes[i - 1] if i else close)
        bars.append(Bar(day, open_, max(open_, close), min(open_, close), close, 1000))
        day += dt.timedelta(days=1)
        while day.weekday() > 4:
            day += dt.timedelta(days=1)
    return bars


class TestIndicators(unittest.TestCase):
    def test_sma_known_values(self):
        self.assertEqual(ind.sma([1, 2, 3, 4, 5], 3), [None, None, 2.0, 3.0, 4.0])

    def test_sma_rejects_zero_period(self):
        with self.assertRaises(ValueError):
            ind.sma([1, 2, 3], 0)

    def test_ema_seeds_on_the_sma(self):
        values = [2.0, 4.0, 6.0, 8.0]
        result = ind.ema(values, 2)
        self.assertIsNone(result[0])
        self.assertEqual(result[1], 3.0)                       # SMA seed of 2 and 4
        self.assertAlmostEqual(result[2], (6 - 3) * (2 / 3) + 3)

    def test_rsi_bounds(self):
        rising = ind.rsi(list(range(1, 30)), 14)[-1]
        falling = ind.rsi(list(range(30, 1, -1)), 14)[-1]
        self.assertEqual(rising, 100.0)
        self.assertEqual(falling, 0.0)

    def test_macd_on_a_linear_ramp_is_constant(self):
        line, signal, hist = ind.macd([float(x) for x in range(1, 80)], 12, 26, 9)
        self.assertAlmostEqual(line[-1], 7.0, places=6)        # (26-12)/2
        self.assertAlmostEqual(hist[-1], 0.0, places=6)

    def test_bollinger_matches_hand_calculation(self):
        mid, upper, lower = ind.bollinger([1, 2, 3, 4], 4, 2.0)
        self.assertAlmostEqual(mid[3], 2.5)
        self.assertAlmostEqual(upper[3], 2.5 + 2 * (1.25 ** 0.5))
        self.assertAlmostEqual(lower[3], 2.5 - 2 * (1.25 ** 0.5))

    def test_warmup_is_none_not_zero(self):
        # A zero would silently become a tradeable signal.
        for series in (ind.sma([1, 2, 3], 3), ind.ema([1, 2, 3], 3), ind.rsi([1, 2, 3], 3)):
            self.assertIsNone(series[0])

    def test_stochastic_places_the_close_in_the_range(self):
        # Range pinned to 0..10, so %K is just the close times ten.
        k, d = ind.stochastic([10.0] * 6, [0.0] * 6, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0], 3, 2)
        self.assertEqual(k[2:], [30.0, 40.0, 50.0, 60.0])
        self.assertEqual(d[3:], [35.0, 45.0, 55.0])      # SMA(2) of %K

    def test_stochastic_flat_range_reads_neutral(self):
        k, _ = ind.stochastic([5.0] * 4, [5.0] * 4, [5.0] * 4, 2, 2)
        self.assertEqual(k[1:], [50.0, 50.0, 50.0])

    def test_keltner_bands_are_atr_wide(self):
        # Constant bar: high 11, low 9, close 10 -> true range 2, so ATR is 2.
        mid, upper, lower = ind.keltner([11.0] * 40, [9.0] * 40, [10.0] * 40, 20, 10, 2.0)
        self.assertAlmostEqual(mid[-1], 10.0)
        self.assertAlmostEqual(upper[-1], 14.0)
        self.assertAlmostEqual(lower[-1], 6.0)

    def test_realized_volatility_of_constant_growth_is_zero(self):
        steady = [100 * (1.01 ** i) for i in range(30)]
        self.assertAlmostEqual(ind.realized_volatility(steady, 10)[-1], 0.0, places=10)

    def test_realized_volatility_rises_with_noise(self):
        calm = [100 * (1.001 ** i) for i in range(60)]
        wild = [100 * (1.05 if i % 2 else 0.96) ** 1 for i in range(60)]
        self.assertLess(
            ind.realized_volatility(calm, 20)[-1], ind.realized_volatility(wild, 20)[-1]
        )

    def test_indicators_are_causal(self):
        values = [float(v) for v in (5, 7, 6, 9, 11, 10, 14, 13, 17, 16, 20, 19)]
        for fn in (lambda v: ind.sma(v, 3), lambda v: ind.ema(v, 3),
                   lambda v: ind.rsi(v, 4), lambda v: ind.rolling_max(v, 3),
                   lambda v: ind.realized_volatility(v, 4),
                   lambda v: ind.stochastic(v, v, v, 3, 2)[0]):
            full = fn(values)
            for cut in range(5, len(values)):
                self.assertEqual(fn(values[:cut]), full[:cut], f"{fn} leaked the future")


class TestMetrics(unittest.TestCase):
    def test_max_drawdown(self):
        self.assertAlmostEqual(max_drawdown([100, 110, 90, 120, 60, 130])["max_drawdown"], -0.5)

    def test_cagr_over_whole_years(self):
        dates = [dt.date(2020, 1, 1) + dt.timedelta(days=365.25 * i) for i in range(0)] or [
            dt.date(2020, 1, 1), dt.date(2024, 12, 31)
        ]
        m = compute_metrics([100.0, 200.0], dates)
        self.assertAlmostEqual(m["total_return"], 1.0)
        self.assertGreater(m["cagr"], 0.14)     # ~14.9% over five years
        self.assertLess(m["cagr"], 0.16)

    def test_flat_curve_has_no_sharpe(self):
        m = compute_metrics([100.0] * 10, [dt.date(2020, 1, 1) + dt.timedelta(i) for i in range(10)])
        self.assertIsNone(m["sharpe"])
        self.assertEqual(m["total_return"], 0.0)

    def test_trade_stats_profit_factor(self):
        trades = [
            {"pnl": 100, "return_pct": 0.1, "bars_held": 5, "exit_date": "2024-01-05"},
            {"pnl": -50, "return_pct": -0.05, "bars_held": 3, "exit_date": "2024-01-09"},
        ]
        stats = trade_stats(trades)
        self.assertEqual(stats["trades"], 2)
        self.assertAlmostEqual(stats["win_rate"], 0.5)
        self.assertAlmostEqual(stats["profit_factor"], 2.0)

    def test_trade_stats_with_no_trades(self):
        self.assertEqual(trade_stats([])["trades"], 0)


class TestEngine(unittest.TestCase):
    def setUp(self):
        self.bars = make_bars([100.0, 110.0, 121.0, 133.1])
        self.free = BacktestConfig(initial_cash=10_000, fee_bps=0, slippage_bps=0,
                                   execution="next_open", use_adjusted=False)

    def test_buy_and_hold_matches_the_price(self):
        result = run_backtest(self.bars, [1.0] * 4, self.free)
        self.assertEqual([round(e, 6) for e in result.equity], [10000, 11000, 12100, 13310])
        self.assertAlmostEqual(result.metrics["total_return"], 0.331)

    def test_costs_are_charged_both_ways(self):
        config = BacktestConfig(initial_cash=10_000, fee_bps=5, slippage_bps=5,
                                execution="next_open", use_adjusted=False)
        result = run_backtest(self.bars, [1.0] * 4, config)
        self.assertAlmostEqual(result.equity[1], 10_990.0)        # 10 bps on 10k entry
        self.assertAlmostEqual(result.total_costs, 23.31, places=2)

    def test_short_inverts_the_return(self):
        result = run_backtest(self.bars, [-1.0] * 4, self.free)
        self.assertEqual([round(e, 6) for e in result.equity], [10000, 9000, 7900, 6690])

    def test_flat_strategy_never_moves(self):
        result = run_backtest(self.bars, [0.0] * 4, self.free)
        self.assertEqual(set(result.equity), {10_000.0})
        self.assertEqual(result.metrics["trades"], 0)
        self.assertIn("never opened a position", " ".join(result.warnings))

    def test_execution_delay_changes_the_fill(self):
        # A signal on the last bar cannot be filled under a delayed model.
        targets = [0.0, 0.0, 0.0, 1.0]
        delayed = run_backtest(self.bars, targets, self.free)
        immediate = run_backtest(
            self.bars, targets,
            BacktestConfig(initial_cash=10_000, fee_bps=0, slippage_bps=0,
                           execution="signal_close", use_adjusted=False),
        )
        self.assertEqual(delayed.metrics["trades"], 0)
        self.assertEqual(immediate.metrics["trades"], 1)

    def test_rejects_mismatched_targets(self):
        with self.assertRaises(ValueError):
            run_backtest(self.bars, [1.0, 1.0], self.free)

    def test_rejects_unknown_execution_mode(self):
        with self.assertRaises(ValueError):
            run_backtest(self.bars, [1.0] * 4,
                         BacktestConfig(execution="teleport"))

    def test_open_position_is_closed_at_the_end(self):
        result = run_backtest(self.bars, [1.0] * 4, self.free)
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0]["exit_date"], self.bars[-1].date.isoformat())

    def test_half_exposure_earns_half_the_move(self):
        half = run_backtest(self.bars, [0.5] * 4, self.free)
        full = run_backtest(self.bars, [1.0] * 4, self.free)
        # The target never changes, so the engine sizes once and holds: half the
        # position earns exactly half the dollar gain, with no rebalancing drift.
        self.assertAlmostEqual(
            half.equity[-1] - 10_000.0, (full.equity[-1] - 10_000.0) / 2, places=6
        )
        # Exposure is sized at the fill but marked at the close, so a position
        # opened at 100 and marked at 110 reads a little above its 0.5 target.
        # That drift is real, not a rounding artefact.
        self.assertGreater(half.exposure[1], 0.5)
        self.assertLess(half.exposure[1], 0.55)

    def test_adjusted_fill_stays_on_the_adjusted_scale(self):
        # A 2:1 split: raw close halves, adjusted close does not.
        bars = [
            Bar(dt.date(2024, 1, 1), 100, 101, 99, 100, 1000, adj_close=50.0),
            Bar(dt.date(2024, 1, 2), 100, 101, 99, 100, 1000, adj_close=50.0),
            Bar(dt.date(2024, 1, 3), 50, 51, 49, 50, 1000, adj_close=50.0),
        ]
        result = run_backtest(bars, [1.0] * 3,
                              BacktestConfig(initial_cash=1000, fee_bps=0, slippage_bps=0,
                                             execution="next_open", use_adjusted=True))
        # Flat on an adjusted basis, so equity must not jump.
        self.assertAlmostEqual(result.equity[-1], 1000.0, places=6)


class TestStrategies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bars = synthetic_bars(400, seed=3)

    def test_every_strategy_is_well_formed(self):
        for key, strategy in strat.REGISTRY.items():
            targets, params = strategy.generate(self.bars)
            with self.subTest(strategy=key):
                self.assertEqual(len(targets), len(self.bars))
                self.assertTrue(all(-1.0 <= t <= 1.0 for t in targets))
                self.assertEqual(set(params), {p.name for p in strategy.params})

    def test_no_strategy_can_see_the_future(self):
        """Signals on a truncated history must match the full-history prefix."""
        for key, strategy in strat.REGISTRY.items():
            full, _ = strategy.generate(self.bars)
            for cut in (250, 320, 399):
                prefix, _ = strategy.generate(self.bars[:cut])
                with self.subTest(strategy=key, cut=cut):
                    self.assertEqual(prefix, full[:cut],
                                     f"{key} used information from after bar {cut}")

    def test_params_are_coerced_from_strings(self):
        targets, params = strat.get("sma_crossover").generate(self.bars, {"fast": "5", "slow": "20"})
        self.assertEqual(params["fast"], 5)
        self.assertEqual(params["slow"], 20)
        self.assertIsInstance(params["allow_short"], bool)

    def test_shorting_flag_produces_short_exposure(self):
        long_only, _ = strat.get("sma_crossover").generate(self.bars, {"allow_short": False})
        with_shorts, _ = strat.get("sma_crossover").generate(self.bars, {"allow_short": True})
        self.assertEqual(min(long_only), 0.0)
        self.assertEqual(min(with_shorts), -1.0)

    def test_vol_target_takes_fractional_positions(self):
        """The only strategy that sizes below a full position - a distinct path."""
        targets, _ = strat.get("vol_target").generate(self.bars)
        fractional = [t for t in targets if 0.0 < t < 1.0]
        self.assertTrue(fractional, "vol targeting never sized below full exposure")
        self.assertTrue(all(0.0 <= t <= 1.0 for t in targets))

    def test_vol_target_rebalance_band_reduces_churn(self):
        wide, _ = strat.get("vol_target").generate(self.bars, {"rebalance_band": 40})
        tight, _ = strat.get("vol_target").generate(self.bars, {"rebalance_band": 1})
        changes = lambda s: sum(1 for a, b in zip(s, s[1:]) if a != b)
        self.assertLess(changes(wide), changes(tight))

    def test_atr_trailing_stop_exits_on_a_drop(self):
        # Climb steadily to trigger the breakout, then fall off a cliff.
        closes = [100.0 + i for i in range(60)] + [120.0, 100.0, 80.0]
        bars = make_bars(closes)
        targets, _ = strat.get("atr_trailing_stop").generate(
            bars, {"entry_lookback": 20, "atr_period": 14, "multiplier": 2.0}
        )
        self.assertEqual(targets[59], 1.0, "should be long at the top of the climb")
        self.assertEqual(targets[-1], 0.0, "trailing stop should have closed it")

    def test_rsi_pullback_stays_out_below_the_trend(self):
        falling = make_bars([200.0 - i for i in range(300)])
        targets, _ = strat.get("rsi_pullback").generate(falling)
        self.assertEqual(set(targets), {0.0},
                         "bought a dip while price was below its trend filter")

    def test_stochastic_reversion_needs_the_turn_up(self):
        # A straight decline is oversold throughout, but %K never crosses %D,
        # so nothing should be bought.
        targets, _ = strat.get("stochastic_reversion").generate(
            make_bars([300.0 - i for i in range(200)])
        )
        self.assertEqual(set(targets), {0.0})

    def test_new_strategies_are_registered(self):
        for key in ("atr_trailing_stop", "keltner_breakout", "stochastic_reversion",
                    "vol_target", "rsi_pullback"):
            self.assertIn(key, strat.REGISTRY)

    def test_strategy_cap_covers_the_registry(self):
        """The UI can tick every strategy at once; the API must accept that."""
        self.assertGreaterEqual(
            MAX_STRATEGIES, len(strat.REGISTRY),
            "server.MAX_STRATEGIES is below the registry size, so selecting every "
            "strategy in the UI would be rejected",
        )

    def test_unknown_strategy_raises(self):
        with self.assertRaises(KeyError):
            strat.get("moon_phase")

    def test_fast_must_be_shorter_than_slow(self):
        with self.assertRaises(ValueError):
            strat.get("macd_cross").generate(self.bars, {"fast": 30, "slow": 10})


class TestRunner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bars = synthetic_bars(600, seed=11)
        cls.config = BacktestConfig(initial_cash=10_000, fee_bps=5, slippage_bps=5)

    def test_benchmark_is_added_once(self):
        results = run_strategies(self.bars, [{"key": "sma_crossover"}], self.config)
        keys = [r.params["_key"] for r in results]
        self.assertEqual(keys.count("buy_and_hold"), 1)

    def test_ranking_orders_by_metric(self):
        results = run_strategies(
            self.bars, [{"key": "sma_crossover"}, {"key": "rsi_reversion"}], self.config
        )
        rows = rank(results, "cagr")
        values = [r["metrics"]["cagr"] for r in rows if r["metrics"]["cagr"] is not None]
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertEqual([r["rank"] for r in rows], list(range(1, len(rows) + 1)))

    def test_drawdown_ranking_prefers_the_shallowest(self):
        results = run_strategies(
            self.bars, [{"key": "sma_crossover"}, {"key": "donchian"}], self.config
        )
        rows = rank(results, "max_drawdown")
        values = [r["metrics"]["max_drawdown"] for r in rows]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_rank_rejects_unknown_metric(self):
        results = run_strategies(self.bars, [{"key": "sma_crossover"}], self.config)
        with self.assertRaises(ValueError):
            rank(results, "vibes")

    def test_sweep_splits_and_reports_out_of_sample(self):
        report = sweep(self.bars, "sma_crossover", {"fast": [5, 10], "slow": [50, 100]},
                       self.config, "sharpe", 0.7)
        self.assertEqual(report["combinations_tested"], 4)
        self.assertEqual(report["in_sample_bars"], int(600 * 0.7))
        for row in report["results"]:
            self.assertIn("out_of_sample", row)
            self.assertIn("in_sample", row)

    def test_sweep_caps_the_grid(self):
        with self.assertRaises(ValueError):
            sweep(self.bars, "sma_crossover",
                  {"fast": list(range(2, 42)), "slow": list(range(50, 90))},
                  self.config, max_combos=100)

    def test_sweep_needs_enough_bars_each_side(self):
        with self.assertRaises(ValueError):
            sweep(self.bars[:50], "sma_crossover", {"fast": [5]}, self.config)


class TestProviderParsing(unittest.TestCase):
    def test_parses_a_marketstack_shaped_row(self):
        bar = _parse_bar({
            "open": 129.8, "high": 133.04, "low": 129.47, "close": 132.995,
            "volume": 106_686_700.0, "adj_close": 132.995,
            "symbol": "AAPL", "exchange": "XNAS", "date": "2021-04-09T00:00:00+0000",
        })
        self.assertEqual(bar.date, dt.date(2021, 4, 9))
        self.assertAlmostEqual(bar.close, 132.995)
        self.assertAlmostEqual(bar.price, 132.995)

    def test_missing_close_is_an_error_not_a_guess(self):
        with self.assertRaises(ProviderError) as ctx:
            _parse_bar({"date": "2024-01-02", "volume": 100})
        self.assertIn("close", str(ctx.exception))

    def test_missing_date_is_an_error(self):
        with self.assertRaises(ProviderError):
            _parse_bar({"close": 10.0})

    def test_open_high_low_fall_back_to_close(self):
        bar = _parse_bar({"date": "2024-01-02", "close": 10.0})
        self.assertEqual((bar.open, bar.high, bar.low), (10.0, 10.0, 10.0))

    def test_date_formats(self):
        for text, expected in (
            ("2024-01-02", dt.date(2024, 1, 2)),
            ("2024-01-02T00:00:00+0000", dt.date(2024, 1, 2)),
            ("2024-01-02T00:00:00Z", dt.date(2024, 1, 2)),
        ):
            self.assertEqual(_parse_date(text), expected)

    def test_unparseable_date_raises(self):
        with self.assertRaises(ProviderError):
            _parse_date("last Tuesday")

    def test_error_bodies_are_detected(self):
        self.assertIn("invalid", _payload_error(
            {"error": {"code": "invalid_access_key", "message": "invalid key"}}))
        self.assertIsNotNone(_payload_error({"message": "You cannot consume this service"}))
        self.assertIsNone(_payload_error({"data": [], "pagination": {}}))

    def test_csv_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bars.csv"
            path.write_text(
                "Date,Open,High,Low,Close,Adj Close,Volume\n"
                "2024-01-02,10,11,9,10.5,10.5,1000\n"
                "2024-01-03,10.5,12,10,11.5,11.5,1200\n"
            )
            bars = load_csv(path)
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0].date, dt.date(2024, 1, 2))
        self.assertAlmostEqual(bars[1].close, 11.5)
        self.assertAlmostEqual(bars[1].adj_close, 11.5)

    def test_missing_csv_raises(self):
        with self.assertRaises(ProviderError):
            load_csv("/nonexistent/nope.csv")


if __name__ == "__main__":
    unittest.main(verbosity=2)
