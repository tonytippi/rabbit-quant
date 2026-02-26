"""VectorBT backtesting engine with parameter sweep support.

Story 3.1 — Configurable long/short signal logic based on cycle phase + Hurst.
Story 3.2 — Multi-dimensional parameter sweep engine using vectorized operations.
Phase 3 — Multi-Asset Portfolio Backtesting & Diversification (Time-First Numba).
Phase 3.5 — Cross-Sectional Ranking for Multi-Asset Capital Allocation.

Architecture boundary: reads signal output (dicts of numpy arrays),
orchestrates VectorBT. Does NOT own data fetching or signal computation.
"""

import numba
import numpy as np
import pandas as pd
import vectorbt as vbt
from loguru import logger


@numba.njit(cache=True)
def simulate_portfolio_nb(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    atr: np.ndarray,
    phase_array: np.ndarray,
    ltf_metric: np.ndarray,
    htf_metric: np.ndarray,
    volatility_zscore: np.ndarray,
    htf_direction: np.ndarray,
    rank_metric: np.ndarray,
    hurst_value: np.ndarray,
    htf_threshold: float,
    ltf_threshold: float,
    veto_threshold: float,
    hurst_threshold: float,
    macro_filter_type: int,
    trailing_multiplier: float,
    breakeven_threshold: float,
    phase_long_center: float,
    phase_short_center: float,
    phase_tolerance: float,
    max_concurrent_trades: int,
) -> tuple:
    """Numba-compiled Time-First loop for Portfolio Execution and Signal Ranking."""
    n_time, n_assets = close.shape

    long_entries = np.zeros((n_time, n_assets), dtype=np.bool_)
    long_exits = np.zeros((n_time, n_assets), dtype=np.bool_)
    short_entries = np.zeros((n_time, n_assets), dtype=np.bool_)
    short_exits = np.zeros((n_time, n_assets), dtype=np.bool_)

    in_position_long = np.zeros(n_assets, dtype=np.bool_)
    in_position_short = np.zeros(n_assets, dtype=np.bool_)
    entry_price = np.zeros(n_assets, dtype=np.float64)
    highest_price = np.zeros(n_assets, dtype=np.float64)
    lowest_price = np.zeros(n_assets, dtype=np.float64)
    stop_loss = np.zeros(n_assets, dtype=np.float64)
    is_breakeven = np.zeros(n_assets, dtype=np.bool_)

    open_trades_count = 0

    for i in range(1, n_time):
        # 1. Process EXITS first to free up concurrency budget
        for a in range(n_assets):
            if in_position_long[a]:
                if high[i, a] > highest_price[a]:
                    highest_price[a] = high[i, a]

                # Dynamic ATR Trailing (Truly dynamic - uses current ATR)
                current_trailing = highest_price[a] - (atr[i, a] * trailing_multiplier)
                if current_trailing > stop_loss[a]:
                    stop_loss[a] = current_trailing

                # Breakeven Ratchet
                if not is_breakeven[a]:
                    if high[i, a] >= entry_price[a] + (atr[i, a] * breakeven_threshold):
                        # Move stop to entry + 0.2% fee coverage
                        be_level = entry_price[a] * 1.002
                        if be_level > stop_loss[a]:
                            stop_loss[a] = be_level
                            is_breakeven[a] = True

                # Check Exit
                if close[i, a] <= stop_loss[a]:
                    long_exits[i, a] = True
                    in_position_long[a] = False
                    open_trades_count -= 1

            elif in_position_short[a]:
                if low[i, a] < lowest_price[a]:
                    lowest_price[a] = low[i, a]

                # Dynamic ATR Trailing
                current_trailing = lowest_price[a] + (atr[i, a] * trailing_multiplier)
                if current_trailing < stop_loss[a]:
                    stop_loss[a] = current_trailing

                # Breakeven Ratchet
                if not is_breakeven[a]:
                    if low[i, a] <= entry_price[a] - (atr[i, a] * breakeven_threshold):
                        be_level = entry_price[a] * 0.998
                        if be_level < stop_loss[a]:
                            stop_loss[a] = be_level
                            is_breakeven[a] = True

                # Check Exit
                if close[i, a] >= stop_loss[a]:
                    short_exits[i, a] = True
                    in_position_short[a] = False
                    open_trades_count -= 1

        # 2. Process ENTRIES
        if open_trades_count < max_concurrent_trades:
            # Rank candidates by Volatility-Adjusted Momentum
            scores = np.full(n_assets, -1e10, dtype=np.float64)
            dirs = np.zeros(n_assets, dtype=np.int8) # 1=Long, -1=Short
            for a in range(n_assets):
                if in_position_long[a] or in_position_short[a] or long_exits[i, a] or short_exits[i, a]:
                    continue

                phase = phase_array[i, a] % (2.0 * np.pi)
                # Check Veto first
                if volatility_zscore[i, a] >= veto_threshold:
                    continue

                # Evaluate macro filters based on macro_filter_type
                # 0 = chop, 1 = hurst, 2 = both
                valid = False
                chop_valid = (htf_metric[i, a] < htf_threshold) and (ltf_metric[i, a] > ltf_threshold)
                hurst_valid = (hurst_value[i, a] > hurst_threshold)

                if macro_filter_type == 0:
                    valid = chop_valid
                elif macro_filter_type == 1:
                    valid = hurst_valid
                else: # 2 = both
                    valid = chop_valid and hurst_valid

                if not valid:
                    continue

                prev_phase = phase_array[i-1, a] % (2.0 * np.pi)

                if htf_direction[i, a] >= 0:
                    if abs(phase - phase_long_center) < phase_tolerance and not (abs(prev_phase - phase_long_center) < phase_tolerance):
                        scores[a] = rank_metric[i, a]
                        dirs[a] = 1
                elif htf_direction[i, a] <= 0:
                    if abs(phase - phase_short_center) < phase_tolerance and not (abs(prev_phase - phase_short_center) < phase_tolerance):
                        scores[a] = -rank_metric[i, a]
                        dirs[a] = -1

            # Sort by Momentum Score descending
            sorted_indices = np.argsort(scores)[::-1]

            for a in sorted_indices:
                if scores[a] <= -1e9 or open_trades_count >= max_concurrent_trades:
                    break

                entry_price[a] = close[i, a]
                highest_price[a] = high[i, a]
                lowest_price[a] = low[i, a]
                is_breakeven[a] = False

                if dirs[a] == 1:
                    long_entries[i, a] = True
                    in_position_long[a] = True
                    stop_loss[a] = entry_price[a] - (atr[i, a] * trailing_multiplier)
                else:
                    short_entries[i, a] = True
                    in_position_short[a] = True
                    stop_loss[a] = entry_price[a] + (atr[i, a] * trailing_multiplier)

                open_trades_count += 1

    return long_entries, long_exits, short_entries, short_exits


def build_entries_exits(
    close: np.ndarray,
    high: np.ndarray | None = None,
    low: np.ndarray | None = None,
    atr: np.ndarray | None = None,
    phase_array: np.ndarray | None = None,
    ltf_metric: np.ndarray | None = None,
    htf_metric: np.ndarray | None = None,
    volatility_zscore: np.ndarray | None = None,
    htf_direction: np.ndarray | None = None,
    rank_metric: np.ndarray | None = None,
    htf_threshold: float = 45,
    ltf_threshold: float = 61.8,
    veto_threshold: float = 3.0,
    trailing_multiplier: float = 2.0,
    breakeven_threshold: float = 1.0,
    max_concurrent_trades: int = 3,
    hurst_value: np.ndarray | float = 0.6,
    hurst_threshold: float = 0.6,
    macro_filter_type: str = "both",
    phase_long_center: float = 4.712,
    phase_short_center: float = 1.571,
    phase_tolerance: float = 0.785,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build long/short entry and exit boolean arrays from cycle phase + MTF metrics.
    Handles 1D (single asset) and 2D (multi-asset) inputs.
    """
    is_1d = close.ndim == 1

    # Force 2D for Numba processing
    def to_2d(arr):
        if arr is None:
            return None
        return arr.reshape(-1, 1) if arr.ndim == 1 else arr

    c_2d = to_2d(close).astype(np.float64)
    h_2d = to_2d(high).astype(np.float64) if high is not None else c_2d.copy()
    l_2d = to_2d(low).astype(np.float64) if low is not None else c_2d.copy()
    a_2d = to_2d(atr).astype(np.float64) if atr is not None else np.zeros_like(c_2d)

    if phase_array is None:
        empty = np.zeros_like(c_2d, dtype=bool)
        return (empty.flatten(), empty.flatten(), empty.flatten(), empty.flatten()) if is_1d else (empty, empty, empty, empty)

    p_2d = to_2d(phase_array).astype(np.float64)

    # Fill missing metrics with safe defaults if not provided
    ltf_m = to_2d(ltf_metric).astype(np.float64) if ltf_metric is not None else np.full_like(c_2d, 100.0)
    htf_m = to_2d(htf_metric).astype(np.float64) if htf_metric is not None else np.full_like(c_2d, 0.0)
    vz_2d = to_2d(volatility_zscore).astype(np.float64) if volatility_zscore is not None else np.zeros_like(c_2d)
    hd_2d = to_2d(htf_direction).astype(np.float64) if htf_direction is not None else np.ones_like(c_2d)
    rm_2d = to_2d(rank_metric).astype(np.float64) if rank_metric is not None else np.zeros_like(c_2d)

    if isinstance(hurst_value, (float, int)):
        hv_2d = np.full_like(c_2d, float(hurst_value))
    else:
        hv_2d = to_2d(hurst_value).astype(np.float64)

    filter_type_map = {"chop": 0, "hurst": 1, "both": 2}
    mf_type = filter_type_map.get(macro_filter_type, 2)

    long_entries, long_exits, short_entries, short_exits = simulate_portfolio_nb(
        c_2d, h_2d, l_2d, a_2d, p_2d, ltf_m, htf_m, vz_2d, hd_2d, rm_2d, hv_2d,
        float(htf_threshold), float(ltf_threshold), float(veto_threshold), float(hurst_threshold), int(mf_type),
        float(trailing_multiplier), float(breakeven_threshold),
        float(phase_long_center), float(phase_short_center), float(phase_tolerance),
        int(max_concurrent_trades)
    )

    if is_1d:
        return long_entries.flatten(), long_exits.flatten(), short_entries.flatten(), short_exits.flatten()
    return long_entries, long_exits, short_entries, short_exits


def run_backtest(
    close: pd.Series | pd.DataFrame,
    high: pd.Series | pd.DataFrame | None = None,
    low: pd.Series | pd.DataFrame | None = None,
    atr: pd.Series | pd.DataFrame | None = None,
    phase_array: np.ndarray | None = None,
    hurst_value: np.ndarray | float = 0.6,
    ltf_metric: np.ndarray | None = None,
    htf_metric: np.ndarray | None = None,
    volatility_zscore: np.ndarray | None = None,
    htf_direction: np.ndarray | None = None,
    rank_metric: np.ndarray | None = None,
    htf_threshold: float = 45,
    ltf_threshold: float = 61.8,
    veto_threshold: float = 3.0,
    trailing_multiplier: float = 2.0,
    breakeven_threshold: float = 1.0,
    max_concurrent_trades: int = 3,
    risk_per_trade: float = 0.01,
    hurst_threshold: float = 0.6,
    macro_filter_type: str = "both",
    initial_capital: float = 100_000.0,
    commission: float = 0.001,
    phase_long_center: float = 4.712,
    phase_short_center: float = 1.571,
    phase_tolerance: float = 0.785,
    freq: str | None = None,
) -> dict | None:
    """Run a single backtest with given parameters (1D or 2D)."""
    try:
        c_val = close.values if hasattr(close, "values") else np.asarray(close)
        h_val = high.values if hasattr(high, "values") else (np.asarray(high) if high is not None else None)
        l_val = low.values if hasattr(low, "values") else (np.asarray(low) if low is not None else None)
        a_val = atr.values if hasattr(atr, "values") else (np.asarray(atr) if atr is not None else None)

        long_entries, long_exits, short_entries, short_exits = build_entries_exits(
            c_val,
            high=h_val,
            low=l_val,
            atr=a_val,
            phase_array=phase_array,
            ltf_metric=ltf_metric, htf_metric=htf_metric, volatility_zscore=volatility_zscore,
            htf_direction=htf_direction, rank_metric=rank_metric,
            htf_threshold=htf_threshold, ltf_threshold=ltf_threshold, veto_threshold=veto_threshold,
            trailing_multiplier=trailing_multiplier,
            breakeven_threshold=breakeven_threshold,
            max_concurrent_trades=max_concurrent_trades,
            hurst_value=hurst_value, hurst_threshold=hurst_threshold,
            macro_filter_type=macro_filter_type,
            phase_long_center=phase_long_center, phase_short_center=phase_short_center,
            phase_tolerance=phase_tolerance,
        )

        size = np.full(c_val.shape, np.nan)
        if a_val is not None:
            # THE CORRECT PERCENT SIZING FORMULA (Phase 3.5 Fix)
            # Fraction of Equity = Risk% * (Price / Distance to stop)
            # This ensures that a move of 'Distance_to_Stop' results in a 'Risk%' loss of account equity.

            # ATR Floor to prevent infinite leverage
            min_atr = c_val * 0.002
            safe_atr = np.maximum(a_val, min_atr)

            distance_to_stop = trailing_multiplier * safe_atr
            calculated_fraction = risk_per_trade * (c_val / distance_to_stop)

            # Cap maximum leverage per trade to 1.0 (100% of equity)
            calculated_fraction = np.minimum(calculated_fraction, 1.0)

            size[long_entries] = calculated_fraction[long_entries]
            size[short_entries] = calculated_fraction[short_entries]

        # Run VectorBT portfolio simulation
        # Using group_by=True groups all columns into a single portfolio for 2D inputs
        pf = vbt.Portfolio.from_signals(
            close,
            entries=long_entries,
            exits=long_exits,
            short_entries=short_entries,
            short_exits=short_exits,
            size=size if not np.all(np.isnan(size)) else None,
            size_type="percent",
            accumulate=False,
            init_cash=initial_capital,
            fees=commission,
            freq=freq,
            group_by=True if close.ndim == 2 else None,
        )

        stats = pf.stats()

        return {
            "total_return": float(stats.get("Total Return [%]", 0.0)),
            "sharpe_ratio": float(stats.get("Sharpe Ratio", 0.0)),
            "max_drawdown": float(stats.get("Max Drawdown [%]", 0.0)),
            "win_rate": float(stats.get("Win Rate [%]", 0.0)),
            "total_trades": int(stats.get("Total Trades", 0)),
            "profit_factor": float(stats.get("Profit Factor", 0.0)),
            "portfolio": pf,
        }

    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        return None


def run_parameter_sweep(
    close: pd.Series | pd.DataFrame,
    high: pd.Series | pd.DataFrame | None = None,
    low: pd.Series | pd.DataFrame | None = None,
    atr: pd.Series | pd.DataFrame | None = None,
    phase_array: np.ndarray | None = None,
    hurst_value: np.ndarray | float = 0.6,
    ltf_metric: np.ndarray | None = None,
    htf_metric: np.ndarray | None = None,
    volatility_zscore: np.ndarray | None = None,
    htf_direction: np.ndarray | None = None,
    rank_metric: np.ndarray | None = None,
    hurst_range: list[float] | None = None,
    phase_long_range: list[float] | None = None,
    phase_short_range: list[float] | None = None,
    trailing_multiplier_range: list[float] | None = None,
    macro_filter_type_range: list[str] | None = None,
    breakeven_threshold: float = 2.0,
    max_concurrent_trades: int = 3,
    risk_per_trade: float = 0.02,
    initial_capital: float = 100_000.0,
    commission: float = 0.001,
    freq: str | None = None,
) -> pd.DataFrame:
    """Sweep strategy parameters across a multi-dimensional grid."""
    if hurst_range is None:
        hurst_range = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60]
    if phase_long_range is None:
        phase_long_range = [4.0, 4.4, 4.712, 5.0, 5.5]
    if phase_short_range is None:
        phase_short_range = [1.0, 1.3, 1.571, 1.8, 2.1]
    if trailing_multiplier_range is None:
        trailing_multiplier_range = [2.5, 3.0, 3.5]
    if macro_filter_type_range is None:
        macro_filter_type_range = ["both"]

    results = []
    total_combos = len(hurst_range) * len(phase_long_range) * len(phase_short_range) * len(trailing_multiplier_range) * len(macro_filter_type_range)
    logger.info(f"Parameter sweep: {total_combos} combinations")

    for ht in hurst_range:
        for pl in phase_long_range:
            for ps in phase_short_range:
                for tm in trailing_multiplier_range:
                    for mf in macro_filter_type_range:
                        ltf_chop_threshold = 50 - 118 * (ht - 0.5)

                        result = run_backtest(
                            close, high=high, low=low, atr=atr, phase_array=phase_array, hurst_value=hurst_value,
                            ltf_metric=ltf_metric, htf_metric=htf_metric, volatility_zscore=volatility_zscore,
                            htf_direction=htf_direction, rank_metric=rank_metric,
                            hurst_threshold=ht,
                            ltf_threshold=ltf_chop_threshold,
                            htf_threshold=45, # change from 38.2 to catch the trend beginning earlier
                            macro_filter_type=mf,
                            trailing_multiplier=tm,
                            breakeven_threshold=breakeven_threshold,
                            max_concurrent_trades=max_concurrent_trades,
                            risk_per_trade=risk_per_trade,
                            initial_capital=initial_capital,
                            commission=commission,
                            phase_long_center=pl,
                            phase_short_center=ps,
                            freq=freq,
                        )

                        row = {
                            "hurst_threshold": ht,
                            "phase_long": pl,
                            "phase_short": ps,
                            "trailing_multiplier": tm,
                            "macro_filter_type": mf,
                            "total_return": result["total_return"] if result else 0.0,
                            "sharpe_ratio": result["sharpe_ratio"] if result else 0.0,
                            "max_drawdown": result["max_drawdown"] if result else 0.0,
                        "win_rate": result["win_rate"] if result else 0.0,
                        "profit_factor": result["profit_factor"] if result else 0.0,
                        "total_trades": result["total_trades"] if result else 0,
                    }
                    results.append(row)

    df = pd.DataFrame(results)
    logger.info(f"Sweep complete: {len(df)} results")
    return df
