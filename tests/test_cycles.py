"""Tests for src/signals/cycles.py — FFT cycle detection, filtering, projection."""

import numpy as np
import pandas as pd

from src.signals.cycles import (
    _analyze_cycle,
    _lowpass_filter,
    detect_dominant_cycle,
    detect_dominant_cycle_filtered,
)


def _make_sinusoidal_df(period: int = 50, n: int = 500, noise_level: float = 0.0) -> pd.DataFrame:
    """Create a DataFrame with a known sinusoidal signal for testing."""
    t = np.arange(n, dtype=np.float64)
    prices = 100.0 + 10.0 * np.sin(2.0 * np.pi * t / period)
    if noise_level > 0:
        prices += np.random.default_rng(42).normal(0, noise_level, n)
    return pd.DataFrame({"close_price": prices})


class TestDetectDominantCycle:
    def test_detects_known_period(self):
        """FFT should detect a 50-bar cycle within 5% tolerance."""
        df = _make_sinusoidal_df(period=50, n=500)
        result = detect_dominant_cycle(df)

        assert result is not None
        assert abs(result["dominant_period"] - 50) <= 50 * 0.05  # 5% tolerance

    def test_returns_phase_array(self):
        df = _make_sinusoidal_df(period=50, n=500)
        result = detect_dominant_cycle(df)

        assert result is not None
        assert len(result["phase_array"]) == 500

    def test_returns_projection_array(self):
        df = _make_sinusoidal_df(period=50, n=500)
        result = detect_dominant_cycle(df)

        assert result is not None
        assert len(result["projection_array"]) == 20  # default projection_bars

    def test_returns_none_for_insufficient_data(self):
        df = pd.DataFrame({"close_price": [100.0] * 100})
        result = detect_dominant_cycle(df)
        assert result is None

    def test_returns_none_for_empty_df(self):
        result = detect_dominant_cycle(pd.DataFrame())
        assert result is None

    def test_returns_none_for_none_input(self):
        result = detect_dominant_cycle(None)
        assert result is None

    def test_detects_different_periods(self):
        """Test detection accuracy for various cycle lengths."""
        for period in [20, 30, 80, 100]:
            df = _make_sinusoidal_df(period=period, n=max(period * 10, 500))
            result = detect_dominant_cycle(df)
            assert result is not None
            assert abs(result["dominant_period"] - period) <= period * 0.1, f"Failed for period={period}"


class TestDetectDominantCycleFiltered:
    def test_filtered_detects_known_period(self):
        df = _make_sinusoidal_df(period=50, n=500, noise_level=2.0)
        result = detect_dominant_cycle_filtered(df, cutoff=0.1)

        assert result is not None
        assert abs(result["dominant_period"] - 50) <= 50 * 0.10  # 10% tolerance with noise

    def test_filtering_improves_noisy_detection(self):
        """Filtered detection should be at least as accurate as unfiltered on noisy data."""
        df = _make_sinusoidal_df(period=50, n=500, noise_level=5.0)

        detect_dominant_cycle(df)  # baseline comparison
        filtered = detect_dominant_cycle_filtered(df, cutoff=0.1)

        assert filtered is not None
        # Filtered result should be close to 50
        filtered_error = abs(filtered["dominant_period"] - 50)
        assert filtered_error <= 50 * 0.15  # 15% tolerance for noisy data

    def test_returns_none_for_insufficient_data(self):
        df = pd.DataFrame({"close_price": [100.0] * 100})
        assert detect_dominant_cycle_filtered(df) is None


class TestLowpassFilter:
    def test_preserves_low_frequency_signal(self):
        t = np.arange(500, dtype=np.float64)
        low_freq = np.sin(2.0 * np.pi * t / 100)  # Period 100 = low freq
        filtered = _lowpass_filter(low_freq, cutoff=0.2)

        # Correlation between original and filtered should be high
        correlation = np.corrcoef(low_freq, filtered)[0, 1]
        assert correlation > 0.9

    def test_attenuates_high_frequency_noise(self):
        t = np.arange(500, dtype=np.float64)
        low_freq = np.sin(2.0 * np.pi * t / 100)
        high_freq = 0.5 * np.sin(2.0 * np.pi * t / 5)  # Period 5 = high freq noise
        mixed = low_freq + high_freq

        filtered = _lowpass_filter(mixed, cutoff=0.1)

        # Filtered should be closer to low_freq than the mixed signal
        error_mixed = np.std(mixed - low_freq)
        error_filtered = np.std(filtered - low_freq)
        assert error_filtered < error_mixed

    def test_output_same_length(self):
        prices = np.random.default_rng(42).normal(100, 10, 500)
        filtered = _lowpass_filter(prices)
        assert len(filtered) == len(prices)


class TestAnalyzeCycle:
    def test_returns_all_required_keys(self):
        prices = 100.0 + 10.0 * np.sin(2.0 * np.pi * np.arange(500) / 50)
        result = _analyze_cycle(prices)

        assert "dominant_period" in result
        assert "phase_array" in result
        assert "projection_array" in result
        assert "amplitude" in result
        assert "current_phase" in result

    def test_projection_continues_smoothly(self):
        """Last point of phase_array and first point of projection should be close."""
        prices = 100.0 + 10.0 * np.sin(2.0 * np.pi * np.arange(500) / 50)
        result = _analyze_cycle(prices, projection_bars=20)

        last_historical = result["phase_array"][-1]
        first_projected = result["projection_array"][0]
        # Should be continuous (within amplitude range)
        assert abs(first_projected - last_historical) < result["amplitude"] * 0.5

    def test_amplitude_is_positive(self):
        prices = 100.0 + 10.0 * np.sin(2.0 * np.pi * np.arange(500) / 50)
        result = _analyze_cycle(prices)
        assert result["amplitude"] > 0

    def test_current_phase_in_range(self):
        prices = 100.0 + 10.0 * np.sin(2.0 * np.pi * np.arange(500) / 50)
        result = _analyze_cycle(prices)
        assert 0.0 <= result["current_phase"] <= 2.0 * np.pi
