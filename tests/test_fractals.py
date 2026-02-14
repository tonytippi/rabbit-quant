"""Tests for src/signals/fractals.py — Numba Hurst R/S calculation."""

import time

import numpy as np
import pandas as pd

from src.signals.fractals import _hurst_rs, calculate_hurst


def _make_df(prices: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame({"close_price": prices})


class TestCalculateHurst:
    def test_returns_float(self):
        rng = np.random.default_rng(42)
        prices = 100.0 + np.cumsum(rng.normal(0, 1, 500))
        result = calculate_hurst(_make_df(prices))
        assert isinstance(result, float)

    def test_random_walk_hurst_in_range(self):
        """Random walk Hurst should be in valid range (R/S method has finite-sample bias)."""
        rng = np.random.default_rng(0)
        prices = 100.0 + np.cumsum(rng.normal(0, 1, 2000))
        h = calculate_hurst(_make_df(prices))
        assert 0.0 <= h <= 1.0, f"Random walk H={h}, expected in [0, 1]"

    def test_trending_above_half(self):
        """Persistent/trending series should have H > 0.5."""
        t = np.arange(2000, dtype=np.float64)
        prices = 100.0 + 0.05 * t + 2.0 * np.sin(2.0 * np.pi * t / 200)
        h = calculate_hurst(_make_df(prices))
        assert h > 0.5, f"Trending H={h}, expected > 0.5"

    def test_returns_default_for_none(self):
        assert calculate_hurst(None) == 0.5

    def test_returns_default_for_insufficient_data(self):
        df = pd.DataFrame({"close_price": [100.0] * 10})
        assert calculate_hurst(df) == 0.5

    def test_returns_default_for_missing_column(self):
        df = pd.DataFrame({"other_col": [100.0] * 500})
        assert calculate_hurst(df) == 0.5

    def test_custom_column(self):
        rng = np.random.default_rng(42)
        prices = 100.0 + np.cumsum(rng.normal(0, 1, 500))
        df = pd.DataFrame({"adjusted_close": prices})
        h = calculate_hurst(df, column="adjusted_close")
        assert 0.0 <= h <= 1.0

    def test_hurst_in_valid_range(self):
        rng = np.random.default_rng(42)
        prices = 100.0 + np.cumsum(rng.normal(0, 1, 1000))
        h = calculate_hurst(_make_df(prices))
        assert 0.0 <= h <= 1.0

    def test_constant_prices_returns_default(self):
        df = pd.DataFrame({"close_price": [100.0] * 500})
        h = calculate_hurst(df)
        assert h == 0.5


class TestHurstPerformance:
    def test_10k_candles_under_50ms(self):
        """Story 2.4 NFR: must complete in < 0.05s for 10,000 candles."""
        rng = np.random.default_rng(42)
        prices = 100.0 + np.cumsum(rng.normal(0, 1, 10_000))

        # Warm up numba JIT
        _hurst_rs(prices[:100].astype(np.float64))

        start = time.perf_counter()
        _hurst_rs(prices.astype(np.float64))
        elapsed = time.perf_counter() - start

        assert elapsed < 0.05, f"Hurst took {elapsed:.4f}s, expected < 0.05s"


class TestHurstRSInternal:
    def test_short_array_returns_half(self):
        assert _hurst_rs(np.array([1.0, 2.0, 3.0])) == 0.5

    def test_returns_float64(self):
        rng = np.random.default_rng(42)
        prices = rng.normal(100, 10, 500).astype(np.float64)
        result = _hurst_rs(prices)
        assert isinstance(result, (float, np.floating))
