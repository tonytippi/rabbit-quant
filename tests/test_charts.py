"""Tests for src/dashboard/charts.py — Plotly chart components."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.dashboard.charts import _infer_freq, create_candlestick_chart


def _make_ohlcv_df(n: int = 100) -> pd.DataFrame:
    """Create sample OHLCV DataFrame for chart testing."""
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    rng = np.random.default_rng(42)
    close = 100.0 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame({
        "timestamp": dates,
        "open_price": close - rng.uniform(0, 1, n),
        "high_price": close + rng.uniform(0, 2, n),
        "low_price": close - rng.uniform(0, 2, n),
        "close_price": close,
        "volume": rng.integers(1000, 10000, n),
    })


def _make_cycle_result(n: int = 100) -> dict:
    """Create sample cycle detection result."""
    t = np.arange(n, dtype=np.float64)
    phase = 5.0 * np.sin(2.0 * np.pi * t / 50)
    projection = 5.0 * np.sin(2.0 * np.pi * np.arange(n, n + 20) / 50)
    return {
        "dominant_period": 50,
        "phase_array": phase,
        "projection_array": projection,
        "amplitude": 5.0,
        "current_phase": 3.14,
    }


class TestCreateCandlestickChart:
    def test_returns_plotly_figure(self):
        df = _make_ohlcv_df()
        fig = create_candlestick_chart(df, "AAPL", "1d")
        assert isinstance(fig, go.Figure)

    def test_has_candlestick_and_volume_traces(self):
        df = _make_ohlcv_df()
        fig = create_candlestick_chart(df, "AAPL", "1d")
        trace_types = [type(t).__name__ for t in fig.data]
        assert "Candlestick" in trace_types
        assert "Bar" in trace_types

    def test_with_cycle_overlay(self):
        df = _make_ohlcv_df()
        cycle = _make_cycle_result()
        fig = create_candlestick_chart(df, "AAPL", "1d", cycle_result=cycle)
        # Should have extra Scatter traces for sine wave + projection
        trace_names = [t.name for t in fig.data if t.name]
        assert any("Cycle" in n for n in trace_names)
        assert any("Projection" in n for n in trace_names)

    def test_with_long_signal(self):
        df = _make_ohlcv_df()
        signal = {"signal": "long", "current_phase": 4.712}
        fig = create_candlestick_chart(df, "AAPL", "1d", signal_data=signal)
        trace_names = [t.name for t in fig.data if t.name]
        assert "Long Signal" in trace_names

    def test_with_short_signal(self):
        df = _make_ohlcv_df()
        signal = {"signal": "short", "current_phase": 1.571}
        fig = create_candlestick_chart(df, "AAPL", "1d", signal_data=signal)
        trace_names = [t.name for t in fig.data if t.name]
        assert "Short Signal" in trace_names

    def test_neutral_signal_no_marker(self):
        df = _make_ohlcv_df()
        signal = {"signal": "neutral", "current_phase": 0.0}
        fig = create_candlestick_chart(df, "AAPL", "1d", signal_data=signal)
        trace_names = [t.name for t in fig.data if t.name]
        assert "Long Signal" not in trace_names
        assert "Short Signal" not in trace_names

    def test_no_overlays(self):
        df = _make_ohlcv_df()
        fig = create_candlestick_chart(df, "AAPL", "1d")
        # Only candlestick + volume = 2 traces
        assert len(fig.data) == 2

    def test_empty_cycle_result(self):
        df = _make_ohlcv_df()
        empty_cycle = {
            "dominant_period": 0,
            "phase_array": np.array([]),
            "projection_array": np.array([]),
            "amplitude": 0.0,
            "current_phase": 0.0,
        }
        fig = create_candlestick_chart(df, "TEST", "1h", cycle_result=empty_cycle)
        assert isinstance(fig, go.Figure)


class TestInferFreq:
    def test_daily(self):
        ts = pd.Series(pd.date_range("2024-01-01", periods=5, freq="D"))
        assert _infer_freq(ts) == "D"

    def test_hourly(self):
        ts = pd.Series(pd.date_range("2024-01-01", periods=5, freq="h"))
        assert _infer_freq(ts) == "h"

    def test_minute(self):
        ts = pd.Series(pd.date_range("2024-01-01", periods=5, freq="min"))
        assert _infer_freq(ts) == "min"

    def test_single_timestamp(self):
        ts = pd.Series([pd.Timestamp("2024-01-01")])
        assert _infer_freq(ts) == "D"  # default
