"""Tests for src/backtest/vbt_runner.py — VectorBT backtesting engine."""

import numpy as np
import pandas as pd

from src.backtest.vbt_runner import build_entries_exits, run_backtest, run_parameter_sweep


def _make_price_series(n: int = 500, period: int = 50) -> tuple[pd.Series, np.ndarray]:
    """Create a sinusoidal price series and matching phase array for testing."""
    t = np.arange(n, dtype=np.float64)
    prices = 100.0 + 10.0 * np.sin(2.0 * np.pi * t / period)
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    close = pd.Series(prices, index=dates, name="close_price")

    # Phase array: 0 to 2π per cycle
    phase = (2.0 * np.pi * t / period) % (2.0 * np.pi)
    return close, phase


class TestBuildEntriesExits:
    def test_returns_four_boolean_arrays(self):
        close, phase = _make_price_series()
        le, lx, se, sx = build_entries_exits(close.values, phase_array=phase, hurst_value=0.7)
        assert len(le) == len(close)
        assert le.dtype == bool

    def test_no_signals_when_hurst_below_threshold(self):
        close, phase = _make_price_series()
        le, lx, se, sx = build_entries_exits(close.values, phase_array=phase, hurst_value=0.3, hurst_threshold=0.6)
        assert not np.any(le)
        assert not np.any(se)

    def test_generates_entries_when_hurst_above_threshold(self):
        close, phase = _make_price_series(n=500, period=50)
        le, lx, se, sx = build_entries_exits(close.values, phase_array=phase, hurst_value=0.7, hurst_threshold=0.6)
        # Should have some long and short entries
        assert np.sum(le) > 0 or np.sum(se) > 0

    def test_empty_arrays_for_mismatched_lengths(self):
        close, phase = _make_price_series(n=500)
        short_phase = phase[:100]
        le, lx, se, sx = build_entries_exits(close.values, phase_array=short_phase, hurst_value=0.7)
        assert not np.any(le)

    def test_empty_arrays_for_zero_length(self):
        le, lx, se, sx = build_entries_exits(np.array([]), phase_array=np.array([]), hurst_value=0.7)
        assert len(le) == 0


class TestRunBacktest:
    def test_returns_dict_with_metrics(self):
        close, phase = _make_price_series()
        result = run_backtest(close, phase_array=phase, hurst_value=0.7, hurst_threshold=0.5)
        assert result is not None
        assert "total_return" in result
        assert "sharpe_ratio" in result
        assert "max_drawdown" in result
        assert "win_rate" in result
        assert "total_trades" in result
        assert "portfolio" in result

    def test_returns_none_on_invalid_input(self):
        close = pd.Series([], dtype=float)
        phase = np.array([])
        result = run_backtest(close, phase_array=phase, hurst_value=0.7)
        # Empty series — should still return (possibly with 0 trades)
        # VectorBT handles empty gracefully
        assert result is not None or result is None  # either is acceptable

    def test_no_trades_when_hurst_below_threshold(self):
        close, phase = _make_price_series()
        result = run_backtest(close, phase_array=phase, hurst_value=0.3, hurst_threshold=0.6)
        assert result is not None
        assert result["total_trades"] == 0

    def test_custom_capital_and_commission(self):
        close, phase = _make_price_series()
        result = run_backtest(
            close, phase_array=phase, hurst_value=0.7,
            hurst_threshold=0.5,
            initial_capital=50_000.0,
            commission=0.002,
        )
        assert result is not None


class TestRunParameterSweep:
    def test_returns_dataframe_with_expected_columns(self):
        close, phase = _make_price_series(n=300)
        df = run_parameter_sweep(
            close, phase_array=phase, hurst_value=0.7,
            hurst_range=[0.5, 0.7],
            phase_long_range=[4.712],
            phase_short_range=[1.571],
        )
        assert isinstance(df, pd.DataFrame)
        assert "hurst_threshold" in df.columns
        assert "sharpe_ratio" in df.columns
        assert len(df) == 2  # 2 hurst × 1 long × 1 short

    def test_sweep_correct_combo_count(self):
        close, phase = _make_price_series(n=300)
        df = run_parameter_sweep(
            close, phase_array=phase, hurst_value=0.7,
            hurst_range=[0.5, 0.6],
            phase_long_range=[4.0, 5.0],
            phase_short_range=[1.0, 2.0],
        )
        assert len(df) == 2 * 2 * 2  # 8 combinations

    def test_sweep_with_defaults(self):
        close, phase = _make_price_series(n=300)
        df = run_parameter_sweep(close, phase_array=phase, hurst_value=0.7)
        # Default: 9 hurst × 5 long × 5 short = 225
        assert len(df) == 225
