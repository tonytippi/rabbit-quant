"""Bulk backtest runner for multiple assets and timeframes.

Orchestrates the execution of backtests across all configured symbols and timeframes,
providing a consolidated summary report and leaderboard.
"""

import asyncio
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

from src.backtest.analyzer import recommend_config
from src.backtest.vbt_runner import run_parameter_sweep, run_backtest
from src.config import AppSettings, AssetConfig, StrategyConfig, TimeframeConfig
from src.data_loader import get_connection, query_ohlcv
from src.fetchers.orchestrator import fetch_all_assets
from src.signals.cycles import detect_dominant_cycle_filtered
from src.signals.fractals import calculate_hurst


def _calculate_atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range (ATR) series."""
    high = df["high_price"]
    low = df["low_price"]
    close = df["close_price"]
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    atr = tr.rolling(window=period).mean()
    return atr.bfill()


def _process_single_symbol_data(
    settings: AppSettings,
    strategy: StrategyConfig,
    symbol: str,
    timeframe: str,
) -> dict | None:
    """Fetch and compute signals for a single symbol to be aggregated."""
    try:
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

        df = df.set_index("timestamp")
        
        return {
            "symbol": symbol,
            "close": df["close_price"],
            "high": df["high_price"],
            "low": df["low_price"],
            "atr": _calculate_atr_series(df, period=14),
            "phase": pd.Series(cycle_result["phase_array"], index=df.index),
            "hurst": hurst_value
        }

    except Exception as e:
        logger.error(f"Error processing {symbol}/{timeframe}: {e}")
        return None


async def run_bulk_backtest(
    settings: AppSettings,
    assets: AssetConfig,
    strategy: StrategyConfig,
    timeframes: TimeframeConfig,
    asset_type: str = "crypto",
    sweep: bool = False,
    fetch: bool = False,
) -> None:
    """Run bulk backtest across all symbols and timeframes."""
    
    # Step 1: Optional Fetch
    if fetch:
        logger.info("Fetching latest data for all assets...")
        conn = get_connection(settings)
        await fetch_all_assets(conn, assets, timeframes)
        conn.close()

    symbols = assets.crypto_symbols if asset_type == "crypto" else assets.stock_symbols
    tfs = timeframes.default_timeframes
    
    logger.info(f"Starting bulk backtest for {len(symbols)} symbols x {len(tfs)} timeframes...")
    start_time = time.monotonic()

    results = []

    for tf in tfs:
        logger.info(f"Processing timeframe: {tf}")
        # 1. Fetch all data into a 2D Matrix (Columns = Assets, Rows = Time)
        tasks_data = []
        with ProcessPoolExecutor() as executor:
            futures = []
            for sym in symbols:
                futures.append(executor.submit(
                    _process_single_symbol_data, settings, strategy, sym, tf
                ))

            for future in as_completed(futures):
                res = future.result()
                if res:
                    tasks_data.append(res)
        
        if not tasks_data:
            continue
            
        # 2. Align into 2D Matrices on the same timestamps
        close_list = []
        high_list = []
        low_list = []
        atr_list = []
        phase_list = []
        hurst_dict = {}
        
        for data in tasks_data:
            sym = data["symbol"]
            close_list.append(data["close"].rename(sym))
            high_list.append(data["high"].rename(sym))
            low_list.append(data["low"].rename(sym))
            atr_list.append(data["atr"].rename(sym))
            phase_list.append(data["phase"].rename(sym))
            hurst_dict[sym] = data["hurst"]
            
        matrix_close = pd.concat(close_list, axis=1).ffill().dropna()
        matrix_high = pd.concat(high_list, axis=1).reindex(matrix_close.index).ffill()
        matrix_low = pd.concat(low_list, axis=1).reindex(matrix_close.index).ffill()
        matrix_atr = pd.concat(atr_list, axis=1).reindex(matrix_close.index).ffill()
        matrix_phase = pd.concat(phase_list, axis=1).reindex(matrix_close.index).ffill()
        
        # Build hurst 2D array matching the shape
        matrix_hurst = np.zeros(matrix_close.shape)
        for i, sym in enumerate(matrix_close.columns):
            matrix_hurst[:, i] = hurst_dict[sym]

        # 3. Call the engine EXACTLY ONCE, passing the config correctly
        res = run_backtest(
            close=matrix_close,
            high=matrix_high,
            low=matrix_low,
            atr=matrix_atr,
            phase_array=matrix_phase.values,
            hurst_value=matrix_hurst,
            hurst_threshold=strategy.hurst_threshold,
            trailing_multiplier=strategy.trailing_atr_multiplier,
            breakeven_threshold=strategy.breakeven_atr_threshold,
            max_concurrent_trades=strategy.max_concurrent_trades,
            risk_per_trade=strategy.risk_per_trade,
            initial_capital=strategy.backtest_initial_capital,
            commission=strategy.backtest_commission,
        )

        if res:
            res["timeframe"] = tf
            res["symbol"] = "PORTFOLIO"
            res["best_hurst_threshold"] = strategy.hurst_threshold
            results.append(res)
            
            # Export trade log for this timeframe
            from src.backtest.analyzer import export_trade_log_csv
            output_dir = Path(strategy.backtest_output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            csv_path = output_dir / f"trades_PORTFOLIO_{tf}.csv"
            export_trade_log_csv(res["portfolio"], str(csv_path), symbol="PORTFOLIO")

    elapsed = time.monotonic() - start_time
    print(f"\n\nBulk run complete in {elapsed:.1f}s. Processed {len(tfs)} timeframes.")

    if not results:
        logger.warning("No results generated. Check if data exists.")
        return

    # Step 3: Aggregate & Report
    df = pd.DataFrame(results)
    
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
