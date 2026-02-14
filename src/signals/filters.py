"""Combined signal generation — cycle phase + Hurst → trading signals.

Story 2.5 — Combines cycle detection (Stories 2.1-2.3) and Hurst exponent
(Story 2.4) into actionable long/short/neutral signals.

Architecture boundary: reads from DuckDB, computes signals, returns dicts.
Does NOT own backtesting or data fetching.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd
from loguru import logger

from src.signals.cycles import detect_dominant_cycle_filtered
from src.signals.fractals import calculate_hurst


def generate_signal(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    hurst_threshold: float = 0.6,
    lowpass_cutoff: float = 0.1,
) -> dict | None:
    """Generate combined trading signal for a single symbol/timeframe.

    Runs cycle detection (with low-pass filtering) and Hurst calculation,
    then combines them into a signal decision.

    Signal logic:
    - LONG: Cycle phase near bottom (trough) AND Hurst > threshold
    - SHORT: Cycle phase near top (peak) AND Hurst > threshold
    - NEUTRAL: Hurst below threshold or mid-cycle phase

    Args:
        df: OHLCV DataFrame for one symbol/timeframe.
        symbol: Asset symbol string.
        timeframe: Timeframe string.
        hurst_threshold: Minimum Hurst value for signal generation.
        lowpass_cutoff: Low-pass filter cutoff frequency.

    Returns:
        Signal dict, or None on failure.
    """
    if df is None or df.empty:
        logger.warning(f"No data for signal generation: {symbol}/{timeframe}")
        return None

    try:
        # Compute cycle
        cycle_result = detect_dominant_cycle_filtered(df, cutoff=lowpass_cutoff)

        # Compute Hurst
        hurst_value = calculate_hurst(df)

        # Build signal dict
        if cycle_result is None:
            cycle_result = {
                "dominant_period": 0,
                "phase_array": np.array([]),
                "projection_array": np.array([]),
                "amplitude": 0.0,
                "current_phase": 0.0,
            }

        # Determine signal direction based on cycle phase and Hurst
        signal = _determine_signal(cycle_result["current_phase"], hurst_value, hurst_threshold)

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "dominant_period": cycle_result["dominant_period"],
            "current_phase": cycle_result["current_phase"],
            "hurst_value": hurst_value,
            "phase_array": cycle_result["phase_array"],
            "projection_array": cycle_result["projection_array"],
            "amplitude": cycle_result["amplitude"],
            "signal": signal,
        }

    except Exception as e:
        logger.error(f"Signal generation failed for {symbol}/{timeframe}: {e}")
        return None


def _determine_signal(current_phase: float, hurst_value: float, hurst_threshold: float) -> str:
    """Determine trading signal from cycle phase and Hurst value.

    Phase convention (radians):
    - ~3π/2 (4.71): Cycle bottom/trough → potential LONG
    - ~π/2 (1.57): Cycle top/peak → potential SHORT
    - Other: Mid-cycle → NEUTRAL

    Args:
        current_phase: Current cycle phase in radians (0 to 2π).
        hurst_value: Hurst exponent (0 to 1).
        hurst_threshold: Minimum Hurst for directional signal.

    Returns:
        "long", "short", or "neutral".
    """
    if hurst_value < hurst_threshold:
        return "neutral"

    # Normalize phase to 0-2π
    phase = current_phase % (2.0 * np.pi)

    # Bottom zone: 3π/2 ± π/4 (cycle trough)
    bottom_center = 3.0 * np.pi / 2.0
    # Top zone: π/2 ± π/4 (cycle peak)
    top_center = np.pi / 2.0

    phase_tolerance = np.pi / 4.0  # 45 degrees

    if abs(phase - bottom_center) < phase_tolerance:
        return "long"
    elif abs(phase - top_center) < phase_tolerance:
        return "short"
    else:
        return "neutral"


def generate_signals_batch(
    data_dict: dict[tuple[str, str], pd.DataFrame],
    hurst_threshold: float = 0.6,
    lowpass_cutoff: float = 0.1,
    max_workers: int | None = None,
) -> list[dict]:
    """Generate signals for multiple symbol/timeframe pairs in parallel.

    Uses ProcessPoolExecutor for CPU-bound signal computation across
    multiple assets, as specified in the Architecture doc.

    Args:
        data_dict: Dict mapping (symbol, timeframe) tuples to DataFrames.
        hurst_threshold: Minimum Hurst for directional signals.
        lowpass_cutoff: Low-pass filter cutoff frequency.
        max_workers: Max parallel processes (None = CPU count).

    Returns:
        List of signal dicts (excludes None results from failures).
    """
    results = []

    if not data_dict:
        return results

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for (symbol, timeframe), df in data_dict.items():
            future = executor.submit(
                generate_signal, df, symbol, timeframe, hurst_threshold, lowpass_cutoff
            )
            futures[future] = (symbol, timeframe)

        for future in as_completed(futures):
            symbol, timeframe = futures[future]
            try:
                result = future.result()
                if result is not None:
                    results.append(result)
            except Exception as e:
                logger.error(f"Batch signal failed for {symbol}/{timeframe}: {e}")

    logger.info(f"Generated {len(results)}/{len(data_dict)} signals")
    return results
