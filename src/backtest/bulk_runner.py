"""Bulk backtest runner for multiple assets and timeframes.

Orchestrates the execution of backtests across all configured symbols and timeframes,
providing a consolidated summary report and leaderboard.
"""

import asyncio
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from loguru import logger

from src.backtest.analyzer import recommend_config
from src.backtest.vbt_runner import run_parameter_sweep, run_backtest
from src.config import AppSettings, AssetConfig, StrategyConfig, TimeframeConfig
from src.data_loader import get_connection, query_ohlcv
from src.fetchers.orchestrator import fetch_all_assets
from src.signals.cycles import detect_dominant_cycle_filtered
from src.signals.fractals import calculate_hurst


def _process_single_backtest(
    settings: AppSettings,
    strategy: StrategyConfig,
    symbol: str,
    timeframe: str,
    sweep: bool = False,
) -> dict | None:
    """Run a single backtest or sweep for one symbol/timeframe.
    
    This function is designed to be pickleable for ProcessPoolExecutor.
    """
    try:
        # Each process needs its own DB connection (read-only)
        conn = get_connection(settings, read_only=True)
        df = query_ohlcv(conn, symbol, timeframe)
        conn.close()

        if df.empty or len(df) < strategy.hurst_min_data_points:
            return None

        # Compute signals
        cycle_result = detect_dominant_cycle_filtered(df, cutoff=strategy.cycle_lowpass_cutoff)
        hurst_value = calculate_hurst(df)

        if cycle_result is None:
            return None

        close = df.set_index("timestamp")["close_price"]
        phase_array = cycle_result["phase_array"]

        result_data = {
            "symbol": symbol,
            "timeframe": timeframe,
            "hurst_value": hurst_value,
            "dominant_period": cycle_result["dominant_period"],
        }

        if sweep:
            sweep_df = run_parameter_sweep(
                close, phase_array, hurst_value,
                hurst_range=strategy.backtest_hurst_range,
                phase_long_range=strategy.backtest_phase_long_range,
                phase_short_range=strategy.backtest_phase_short_range,
                initial_capital=strategy.backtest_initial_capital,
                commission=strategy.backtest_commission,
            )
            rec = recommend_config(sweep_df)
            if rec:
                result_data.update({
                    "sharpe_ratio": rec["sharpe_ratio"],
                    "total_return": rec["total_return"],
                    "max_drawdown": rec["max_drawdown"],
                    "win_rate": rec["win_rate"],
                    "best_hurst_threshold": rec["hurst_threshold"],
                    "best_phase_long": rec["phase_long"],
                    "best_phase_short": rec["phase_short"],
                })
            else:
                return None
        else:
            # Single run with current config
            res = run_backtest(
                close, phase_array, hurst_value,
                hurst_threshold=strategy.hurst_threshold,
                initial_capital=strategy.backtest_initial_capital,
                commission=strategy.backtest_commission,
            )
            if res:
                result_data.update({
                    "sharpe_ratio": res["sharpe_ratio"],
                    "total_return": res["total_return"],
                    "max_drawdown": res["max_drawdown"],
                    "win_rate": res["win_rate"],
                    "best_hurst_threshold": strategy.hurst_threshold,
                })
            else:
                return None

        return result_data

    except Exception as e:
        logger.error(f"Error processing {symbol}/{timeframe}: {e}")
        return None


async def run_bulk_backtest(
    settings: AppSettings,
    assets: AssetConfig,
    strategy: StrategyConfig,
    timeframes: TimeframeConfig,
    asset_type: str = "crypto",
    sweep: bool = True,
    fetch: bool = False,
) -> None:
    """Run bulk backtest across all symbols and timeframes."""
    
    # Step 1: Optional Fetch
    if fetch:
        logger.info("Fetching latest data for all assets...")
        conn = get_connection(settings)
        await fetch_all_assets(conn, assets, timeframes)
        conn.close()

    # Step 2: Prepare Tasks
    symbols = assets.crypto_symbols if asset_type == "crypto" else assets.stock_symbols
    # Use all configured default timeframes
    tfs = timeframes.default_timeframes
    
    tasks = []
    logger.info(f"Starting bulk backtest for {len(symbols)} symbols x {len(tfs)} timeframes...")
    start_time = time.monotonic()

    with ProcessPoolExecutor() as executor:
        futures = []
        for sym in symbols:
            for tf in tfs:
                futures.append(executor.submit(
                    _process_single_backtest, settings, strategy, sym, tf, sweep
                ))

        for future in as_completed(futures):
            res = future.result()
            if res:
                tasks.append(res)
                # print(".", end="", flush=True) # Simple progress indicator

    elapsed = time.monotonic() - start_time
    print(f"\n\nBulk run complete in {elapsed:.1f}s. Processed {len(tasks)} combinations.")

    if not tasks:
        logger.warning("No results generated. Check if data exists.")
        return

    # Step 3: Aggregate & Report
    df = pd.DataFrame(tasks)
    
    # Sort by Sharpe Ratio descending
    df = df.sort_values("sharpe_ratio", ascending=False).reset_index(drop=True)

    # Console Leaderboard
    print("\n=== LEADERBOARD (Top 10) ===")
    print(df[[
        "symbol", "timeframe", "sharpe_ratio", "total_return", "max_drawdown", "best_hurst_threshold"
    ]].head(10).to_string(index=False))

    # Save to CSV
    output_dir = Path(strategy.backtest_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"summary_bulk_{asset_type}.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nFull results saved to: {csv_path}")
