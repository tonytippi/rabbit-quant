"""VectorBT backtesting engine with parameter sweep support.

Story 3.1 — Configurable long/short signal logic based on cycle phase + Hurst.
Story 3.2 — Multi-dimensional parameter sweep engine using vectorized operations.

Architecture boundary: reads signal output (dicts of numpy arrays),
orchestrates VectorBT. Does NOT own data fetching or signal computation.
"""

import numpy as np
import pandas as pd
import vectorbt as vbt
from loguru import logger


def build_entries_exits(
    close: np.ndarray,
    phase_array: np.ndarray,
    hurst_value: float,
    hurst_threshold: float = 0.6,
    phase_long_center: float = 4.712,  # 3π/2
    phase_short_center: float = 1.571,  # π/2
    phase_tolerance: float = 0.785,  # π/4
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build long/short entry and exit boolean arrays from cycle phase + Hurst.

    Signal logic:
    - Long entry: phase near trough (phase_long_center ± tolerance) AND Hurst > threshold
    - Short entry: phase near peak (phase_short_center ± tolerance) AND Hurst > threshold
    - Long exit: phase reaches peak zone (short entry zone)
    - Short exit: phase reaches trough zone (long entry zone)

    Args:
        close: Close price array.
        phase_array: Cycle phase values (same length as close).
        hurst_value: Hurst exponent for the series.
        hurst_threshold: Minimum Hurst for directional signals.
        phase_long_center: Center phase angle for long entries (radians).
        phase_short_center: Center phase angle for short entries (radians).
        phase_tolerance: Phase tolerance for entry zones (radians).

    Returns:
        Tuple of (long_entries, long_exits, short_entries, short_exits) boolean arrays.
    """
    n = len(close)

    if len(phase_array) != n or n == 0:
        empty = np.zeros(n, dtype=bool)
        return empty, empty, empty.copy(), empty.copy()

    # Normalize phase to 0-2π
    phase = phase_array % (2.0 * np.pi)

    # Hurst filter: no signals if below threshold
    if hurst_value < hurst_threshold:
        empty = np.zeros(n, dtype=bool)
        return empty, empty, empty.copy(), empty.copy()

    # Entry zones
    long_zone = np.abs(phase - phase_long_center) < phase_tolerance
    short_zone = np.abs(phase - phase_short_center) < phase_tolerance

    # Entries: first bar entering the zone (rising edge)
    long_entries = np.zeros(n, dtype=bool)
    short_entries = np.zeros(n, dtype=bool)

    for i in range(1, n):
        if long_zone[i] and not long_zone[i - 1]:
            long_entries[i] = True
        if short_zone[i] and not short_zone[i - 1]:
            short_entries[i] = True

    # Exits: entering the opposite zone
    long_exits = short_zone.copy()
    short_exits = long_zone.copy()

    return long_entries, long_exits, short_entries, short_exits


def run_backtest(
    close: pd.Series,
    phase_array: np.ndarray,
    hurst_value: float,
    hurst_threshold: float = 0.6,
    initial_capital: float = 100_000.0,
    commission: float = 0.001,
    phase_long_center: float = 4.712,
    phase_short_center: float = 1.571,
    phase_tolerance: float = 0.785,
) -> dict | None:
    """Run a single backtest with given parameters.

    Args:
        close: Close price Series with DatetimeIndex.
        phase_array: Cycle phase array matching close length.
        hurst_value: Hurst exponent.
        hurst_threshold: Min Hurst for signals.
        initial_capital: Starting capital.
        commission: Commission rate per trade.
        phase_long_center: Long entry phase center.
        phase_short_center: Short entry phase center.
        phase_tolerance: Phase zone tolerance.

    Returns:
        Dict with portfolio stats, or None on failure.
    """
    try:
        long_entries, long_exits, short_entries, short_exits = build_entries_exits(
            close.values, phase_array, hurst_value,
            hurst_threshold, phase_long_center, phase_short_center, phase_tolerance,
        )

        # Run VectorBT portfolio simulation
        pf = vbt.Portfolio.from_signals(
            close,
            entries=long_entries,
            exits=long_exits,
            short_entries=short_entries,
            short_exits=short_exits,
            init_cash=initial_capital,
            fees=commission,
            freq="1D",
        )

        stats = pf.stats()

        return {
            "total_return": float(stats.get("Total Return [%]", 0.0)),
            "sharpe_ratio": float(stats.get("Sharpe Ratio", 0.0)),
            "max_drawdown": float(stats.get("Max Drawdown [%]", 0.0)),
            "win_rate": float(stats.get("Win Rate [%]", 0.0)),
            "total_trades": int(stats.get("Total Trades", 0)),
            "portfolio": pf,
        }

    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        return None


def run_parameter_sweep(
    close: pd.Series,
    phase_array: np.ndarray,
    hurst_value: float,
    hurst_range: list[float] | None = None,
    phase_long_range: list[float] | None = None,
    phase_short_range: list[float] | None = None,
    initial_capital: float = 100_000.0,
    commission: float = 0.001,
) -> pd.DataFrame:
    """Sweep strategy parameters across a multi-dimensional grid.

    Iterates over all combinations of hurst_threshold, phase_long_center,
    and phase_short_center, running a backtest for each.

    Args:
        close: Close price Series.
        phase_array: Cycle phase array.
        hurst_value: Actual Hurst exponent of the data.
        hurst_range: List of hurst_threshold values to test.
        phase_long_range: List of long entry phase centers to test.
        phase_short_range: List of short entry phase centers to test.
        initial_capital: Starting capital.
        commission: Commission rate.

    Returns:
        DataFrame with columns: hurst_threshold, phase_long, phase_short,
        total_return, sharpe_ratio, max_drawdown, win_rate, total_trades.
    """
    if hurst_range is None:
        hurst_range = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]
    if phase_long_range is None:
        phase_long_range = [4.0, 4.4, 4.712, 5.0, 5.5]
    if phase_short_range is None:
        phase_short_range = [1.0, 1.3, 1.571, 1.8, 2.1]

    results = []
    total_combos = len(hurst_range) * len(phase_long_range) * len(phase_short_range)
    logger.info(f"Parameter sweep: {total_combos} combinations")

    for ht in hurst_range:
        for pl in phase_long_range:
            for ps in phase_short_range:
                result = run_backtest(
                    close, phase_array, hurst_value,
                    hurst_threshold=ht,
                    initial_capital=initial_capital,
                    commission=commission,
                    phase_long_center=pl,
                    phase_short_center=ps,
                )

                row = {
                    "hurst_threshold": ht,
                    "phase_long": pl,
                    "phase_short": ps,
                    "total_return": result["total_return"] if result else 0.0,
                    "sharpe_ratio": result["sharpe_ratio"] if result else 0.0,
                    "max_drawdown": result["max_drawdown"] if result else 0.0,
                    "win_rate": result["win_rate"] if result else 0.0,
                    "total_trades": result["total_trades"] if result else 0,
                }
                results.append(row)

    df = pd.DataFrame(results)
    logger.info(f"Sweep complete: {len(df)} results")
    return df
