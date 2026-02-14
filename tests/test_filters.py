"""Tests for src/signals/filters.py — combined signal generation."""

import numpy as np
import pandas as pd

from src.signals.filters import _determine_signal, generate_signal, generate_signals_batch


def _make_sinusoidal_df(period: int = 50, n: int = 500) -> pd.DataFrame:
    t = np.arange(n, dtype=np.float64)
    prices = 100.0 + 10.0 * np.sin(2.0 * np.pi * t / period)
    return pd.DataFrame({"close_price": prices})


class TestDetermineSignal:
    def test_long_at_trough(self):
        """Phase near 3π/2 with high Hurst → long."""
        phase = 3.0 * np.pi / 2.0
        assert _determine_signal(phase, 0.7, 0.6) == "long"

    def test_short_at_peak(self):
        """Phase near π/2 with high Hurst → short."""
        phase = np.pi / 2.0
        assert _determine_signal(phase, 0.7, 0.6) == "short"

    def test_neutral_mid_cycle(self):
        """Phase at π (mid-cycle) → neutral."""
        assert _determine_signal(np.pi, 0.7, 0.6) == "neutral"

    def test_neutral_low_hurst(self):
        """Low Hurst always → neutral regardless of phase."""
        phase = 3.0 * np.pi / 2.0  # trough
        assert _determine_signal(phase, 0.4, 0.6) == "neutral"

    def test_neutral_at_zero_phase(self):
        assert _determine_signal(0.0, 0.7, 0.6) == "neutral"

    def test_long_within_tolerance(self):
        """Phase within π/4 of trough → still long."""
        phase = 3.0 * np.pi / 2.0 + np.pi / 8.0  # slightly past trough
        assert _determine_signal(phase, 0.7, 0.6) == "long"

    def test_short_within_tolerance(self):
        phase = np.pi / 2.0 - np.pi / 8.0
        assert _determine_signal(phase, 0.7, 0.6) == "short"


class TestGenerateSignal:
    def test_returns_dict_with_required_keys(self):
        df = _make_sinusoidal_df(period=50, n=500)
        result = generate_signal(df, "TEST", "1h")

        assert result is not None
        assert result["symbol"] == "TEST"
        assert result["timeframe"] == "1h"
        assert "dominant_period" in result
        assert "current_phase" in result
        assert "hurst_value" in result
        assert "signal" in result
        assert result["signal"] in ("long", "short", "neutral")

    def test_returns_none_for_none_input(self):
        assert generate_signal(None, "X", "1h") is None

    def test_returns_none_for_empty_df(self):
        assert generate_signal(pd.DataFrame(), "X", "1h") is None

    def test_returns_neutral_for_insufficient_cycle_data(self):
        """Short data: cycle detection fails but Hurst still works → neutral signal."""
        df = pd.DataFrame({"close_price": [100.0] * 100})
        result = generate_signal(df, "X", "1h")
        assert result is not None
        assert result["signal"] == "neutral"
        assert result["dominant_period"] == 0

    def test_hurst_value_in_range(self):
        df = _make_sinusoidal_df(period=50, n=500)
        result = generate_signal(df, "TEST", "1h")
        assert result is not None
        assert 0.0 <= result["hurst_value"] <= 1.0

    def test_signal_with_custom_threshold(self):
        df = _make_sinusoidal_df(period=50, n=500)
        # Very high threshold → should force neutral
        result = generate_signal(df, "TEST", "1h", hurst_threshold=0.99)
        assert result is not None
        assert result["signal"] == "neutral"


class TestGenerateSignalsBatch:
    def test_empty_dict_returns_empty(self):
        assert generate_signals_batch({}) == []

    def test_batch_processes_multiple(self):
        data = {
            ("SYM1", "1h"): _make_sinusoidal_df(50, 500),
            ("SYM2", "1d"): _make_sinusoidal_df(30, 500),
        }
        results = generate_signals_batch(data, max_workers=2)
        assert len(results) == 2
        symbols = {r["symbol"] for r in results}
        assert symbols == {"SYM1", "SYM2"}

    def test_batch_handles_mixed_data(self):
        """Batch: good data gets signal, short data gets neutral (not skipped)."""
        data = {
            ("GOOD", "1h"): _make_sinusoidal_df(50, 500),
            ("SHORT", "1h"): pd.DataFrame({"close_price": [100.0] * 100}),
        }
        results = generate_signals_batch(data, max_workers=2)
        assert len(results) == 2
        by_symbol = {r["symbol"]: r for r in results}
        assert by_symbol["SHORT"]["signal"] == "neutral"

    def test_batch_skips_empty_input(self):
        data = {
            ("GOOD", "1h"): _make_sinusoidal_df(50, 500),
            ("EMPTY", "1h"): pd.DataFrame(),
        }
        results = generate_signals_batch(data, max_workers=2)
        assert len(results) == 1
        assert results[0]["symbol"] == "GOOD"
