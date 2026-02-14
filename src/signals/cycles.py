"""FFT-based cycle detection, low-pass filtering, and forward projection.

Stories 2.1, 2.2, 2.3 — Detects dominant market cycles using Fast Fourier
Transform, applies noise smoothing, and projects cycles forward.

Architecture boundary: accepts numpy arrays internally, wrapper functions
handle pandas conversion at the module edge.
"""

import numpy as np
import pandas as pd
from loguru import logger
from scipy.signal import butter, filtfilt


def detect_dominant_cycle(df: pd.DataFrame, column: str = "close_price") -> dict | None:
    """Detect dominant cycle period from OHLCV DataFrame.

    Wrapper function: converts DataFrame to numpy, runs FFT analysis,
    and returns a result dict for downstream consumption.

    Args:
        df: OHLCV DataFrame with at least 256 rows.
        column: Column name to analyze (default: close_price).

    Returns:
        Dict with dominant_period, phase_array, projection_array,
        or None if detection fails.
    """
    if df is None or len(df) < 256:
        logger.warning(f"Insufficient data for cycle detection: {len(df) if df is not None else 0} rows (need 256+)")
        return None

    try:
        prices = df[column].values.astype(np.float64)
        return _analyze_cycle(prices)
    except Exception as e:
        logger.error(f"Cycle detection failed: {e}")
        return None


def detect_dominant_cycle_filtered(
    df: pd.DataFrame,
    column: str = "close_price",
    cutoff: float = 0.1,
) -> dict | None:
    """Detect dominant cycle with low-pass filtering applied first.

    Applies a Butterworth low-pass filter to remove high-frequency noise
    before running FFT cycle detection, improving accuracy.

    Args:
        df: OHLCV DataFrame with at least 256 rows.
        column: Column name to analyze.
        cutoff: Low-pass filter cutoff frequency (0.0-1.0, fraction of Nyquist).

    Returns:
        Dict with dominant_period, phase_array, projection_array,
        or None if detection fails.
    """
    if df is None or len(df) < 256:
        logger.warning(f"Insufficient data for filtered cycle detection: {len(df) if df is not None else 0} rows")
        return None

    try:
        prices = df[column].values.astype(np.float64)
        filtered = _lowpass_filter(prices, cutoff)
        return _analyze_cycle(filtered)
    except Exception as e:
        logger.error(f"Filtered cycle detection failed: {e}")
        return None


def _lowpass_filter(prices: np.ndarray, cutoff: float = 0.1, order: int = 3) -> np.ndarray:
    """Apply Butterworth low-pass filter to smooth price data.

    Removes high-frequency noise while preserving the dominant cycle component.
    Uses a zero-phase digital filter (filtfilt) to avoid phase distortion.

    Args:
        prices: 1D numpy array of close prices.
        cutoff: Normalized cutoff frequency (0.0-1.0, fraction of Nyquist freq).
                Lower values = more smoothing. Default 0.1 keeps cycles > 10 bars.
        order: Filter order. Higher = sharper cutoff but more ringing.

    Returns:
        Filtered price array with same length as input.
    """
    # Clamp cutoff to valid range
    cutoff = max(0.01, min(cutoff, 0.99))

    b, a = butter(order, cutoff, btype="low")
    return filtfilt(b, a, prices)


def _analyze_cycle(prices: np.ndarray, min_period: int = 10, max_period: int = 200, projection_bars: int = 20) -> dict:
    """Core FFT cycle analysis on a numpy price array.

    Uses Fast Fourier Transform to decompose the price series into frequency
    components, identifies the dominant cycle period, fits a sine wave to
    determine phase, and projects the cycle forward.

    Algorithm:
    1. Detrend prices (remove linear trend to isolate oscillation)
    2. Apply FFT to get frequency spectrum
    3. Find peak frequency within the valid period range
    4. Convert peak frequency to dominant period (bars)
    5. Fit sine wave to determine amplitude and phase
    6. Project the fitted sine wave forward by projection_bars

    Args:
        prices: Detrended or filtered 1D price array.
        min_period: Minimum cycle period to consider (bars).
        max_period: Maximum cycle period to consider (bars).
        projection_bars: Number of bars to project forward.

    Returns:
        Dict containing:
        - dominant_period: int, cycle length in bars
        - phase_array: numpy array, phase values for historical data
        - projection_array: numpy array, projected cycle values
        - amplitude: float, cycle amplitude
        - current_phase: float, current phase in radians
    """
    n = len(prices)

    # Step 1: Detrend — remove linear trend
    x = np.arange(n, dtype=np.float64)
    slope = (prices[-1] - prices[0]) / (n - 1)
    trend = prices[0] + slope * x
    detrended = prices - trend

    # Step 2: Apply FFT
    fft_vals = np.fft.rfft(detrended)
    fft_power = np.abs(fft_vals) ** 2
    freqs = np.fft.rfftfreq(n)

    # Step 3: Find dominant frequency within valid period range
    # Convert period bounds to frequency bounds
    min_freq = 1.0 / max_period if max_period > 0 else 0.0
    max_freq = 1.0 / min_period if min_period > 0 else 0.5

    # Mask valid frequency range (exclude DC component at index 0)
    valid_mask = (freqs > min_freq) & (freqs <= max_freq)
    if not np.any(valid_mask):
        logger.warning("No valid frequencies in specified period range")
        return {
            "dominant_period": 0,
            "phase_array": np.zeros(n),
            "projection_array": np.zeros(projection_bars),
            "amplitude": 0.0,
            "current_phase": 0.0,
        }

    # Find peak power in valid range
    valid_power = np.where(valid_mask, fft_power, 0.0)
    peak_idx = np.argmax(valid_power)
    dominant_freq = freqs[peak_idx]
    dominant_period = int(round(1.0 / dominant_freq)) if dominant_freq > 0 else 0

    # Step 4: Extract phase from FFT at dominant frequency
    phase_angle = np.angle(fft_vals[peak_idx])
    amplitude = 2.0 * np.abs(fft_vals[peak_idx]) / n

    # Step 5: Generate phase array for historical data
    phase_array = amplitude * np.sin(2.0 * np.pi * dominant_freq * x + phase_angle)

    # Step 6: Project forward
    future_x = np.arange(n, n + projection_bars, dtype=np.float64)
    projection_array = amplitude * np.sin(2.0 * np.pi * dominant_freq * future_x + phase_angle)

    # Current phase (last point)
    current_phase = (2.0 * np.pi * dominant_freq * (n - 1) + phase_angle) % (2.0 * np.pi)

    return {
        "dominant_period": dominant_period,
        "phase_array": phase_array,
        "projection_array": projection_array,
        "amplitude": float(amplitude),
        "current_phase": float(current_phase),
    }
