"""Numba-optimized Hurst Exponent calculation using R/S method.

Story 2.4 — Measures trend persistence (H > 0.5 = trending, H < 0.5 = mean-reverting,
H ≈ 0.5 = random walk). Must complete in < 0.05s for 10,000 candles.

Architecture boundary: @njit function uses numpy-only internals,
wrapper function handles pandas-to-numpy conversion.
"""

import numba
import numpy as np
import pandas as pd
from loguru import logger


def calculate_hurst(df: pd.DataFrame, column: str = "close_price") -> float:
    """Calculate Hurst Exponent from OHLCV DataFrame.

    Public API wrapper: accepts DataFrame, validates input,
    converts to numpy, and calls the Numba-optimized core function.

    The Hurst Exponent (H) measures the long-term memory of a time series:
    - H > 0.5: Persistent/trending (past trends likely to continue)
    - H = 0.5: Random walk (no memory)
    - H < 0.5: Anti-persistent/mean-reverting (trends likely to reverse)

    Args:
        df: OHLCV DataFrame with price data.
        column: Column name to analyze (default: close_price).

    Returns:
        Hurst exponent as float (0.0 to 1.0), or 0.5 on error.
    """
    if df is None or len(df) < 20:
        logger.warning(f"Insufficient data for Hurst calculation: {len(df) if df is not None else 0} rows (need 20+)")
        return 0.5

    try:
        prices = df[column].values.astype(np.float64)
        return float(_hurst_rs(prices))
    except Exception as e:
        logger.error(f"Hurst calculation failed: {e}")
        return 0.5


def calculate_rolling_hurst(df: pd.DataFrame, column: str = "close_price", window: int = 100) -> pd.Series:
    """Calculate Rolling Hurst Exponent from OHLCV DataFrame."""
    if df is None or len(df) < window:
        logger.warning(f"Insufficient data for rolling Hurst: need {window}+ rows")
        return pd.Series(0.5, index=df.index if df is not None else [])

    try:
        prices = df[column].values.astype(np.float64)
        rolling_hurst = _rolling_hurst_rs(prices, window)
        return pd.Series(rolling_hurst, index=df.index)
    except Exception as e:
        logger.error(f"Rolling Hurst calculation failed: {e}")
        return pd.Series(0.5, index=df.index)


@numba.njit(cache=True)
def _rolling_hurst_rs(prices: np.ndarray, window: int) -> np.ndarray:
    n = len(prices)
    out = np.full(n, 0.5, dtype=np.float64)
    if n < window:
        return out
    for i in range(window - 1, n):
        out[i] = _hurst_rs(prices[i - window + 1 : i + 1])
    return out


@numba.njit(cache=True)
def _hurst_rs(prices: np.ndarray) -> float:
    """Compute Hurst Exponent using the Rescaled Range (R/S) method.

    The R/S method estimates H by analyzing how the range of cumulative
    deviations from the mean scales with the length of sub-series.

    Algorithm:
    1. Divide the series into sub-series of varying lengths
    2. For each length, compute R/S (rescaled range):
       a. Calculate mean and deviations from mean
       b. Compute cumulative deviations
       c. R = max(cumulative) - min(cumulative)
       d. S = standard deviation of the sub-series
       e. R/S = R / S
    3. Fit log(R/S) vs log(n) — slope is the Hurst exponent

    Args:
        prices: 1D numpy array of prices (float64).

    Returns:
        Hurst exponent (float64), typically between 0 and 1.
    """
    n = len(prices)
    if n < 20:
        return 0.5

    # Generate sub-series lengths: powers of 2 that fit within data
    max_k = int(np.floor(np.log2(n)))
    min_k = 2  # Minimum sub-series length = 4

    if max_k <= min_k:
        return 0.5

    num_sizes = max_k - min_k + 1
    log_sizes = np.empty(num_sizes, dtype=np.float64)
    log_rs = np.empty(num_sizes, dtype=np.float64)

    for i in range(num_sizes):
        size = 2 ** (i + min_k)
        num_subseries = n // size

        if num_subseries == 0:
            log_sizes[i] = np.log(size)
            log_rs[i] = 0.0
            continue

        rs_sum = 0.0
        valid_count = 0

        for j in range(num_subseries):
            start = j * size
            end = start + size
            subseries = prices[start:end]

            # Mean of subseries
            mean_val = 0.0
            for k in range(size):
                mean_val += subseries[k]
            mean_val /= size

            # Standard deviation
            std_sum = 0.0
            for k in range(size):
                std_sum += (subseries[k] - mean_val) ** 2
            std_val = np.sqrt(std_sum / size)

            if std_val == 0.0:
                continue

            # Cumulative deviations from mean
            cum_dev = np.empty(size, dtype=np.float64)
            cum_dev[0] = subseries[0] - mean_val
            for k in range(1, size):
                cum_dev[k] = cum_dev[k - 1] + (subseries[k] - mean_val)

            # R/S = (max - min of cumulative deviations) / std
            r = np.max(cum_dev) - np.min(cum_dev)
            rs_sum += r / std_val
            valid_count += 1

        if valid_count > 0:
            log_sizes[i] = np.log(size)
            log_rs[i] = np.log(rs_sum / valid_count)
        else:
            log_sizes[i] = np.log(size)
            log_rs[i] = 0.0

    # Linear regression: log(R/S) = H * log(n) + c
    # Using least squares: H = sum((x-mx)(y-my)) / sum((x-mx)^2)
    count = 0
    sum_x = 0.0
    sum_y = 0.0
    for i in range(num_sizes):
        if log_rs[i] > 0.0:
            sum_x += log_sizes[i]
            sum_y += log_rs[i]
            count += 1

    if count < 2:
        return 0.5

    mean_x = sum_x / count
    mean_y = sum_y / count

    num = 0.0
    den = 0.0
    for i in range(num_sizes):
        if log_rs[i] > 0.0:
            dx = log_sizes[i] - mean_x
            dy = log_rs[i] - mean_y
            num += dx * dy
            den += dx * dx

    if den == 0.0:
        return 0.5

    hurst = num / den

    # Clamp to valid range
    if hurst < 0.0:
        hurst = 0.0
    elif hurst > 1.0:
        hurst = 1.0

    return hurst

def calculate_chop(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Choppiness Index (CHOP) for vectorized backtesting.
    
    CHOP is a computationally efficient substitute for Hurst.
    - CHOP > 61.8: Ranging (Hurst < 0.5)
    - CHOP < 38.2: Trending (Hurst > 0.5)
    """
    high = df["high_price"]
    low = df["low_price"]
    close = df["close_price"]

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr_sum = tr.rolling(window=period).sum()
    max_high = high.rolling(window=period).max()
    min_low = low.rolling(window=period).min()

    # Avoid division by zero
    range_hl = max_high - min_low
    range_hl = range_hl.replace(0, np.nan)

    chop = 100 * np.log10(atr_sum / range_hl) / np.log10(period)
    return chop.fillna(50.0) # 50 is neutral

