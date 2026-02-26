"""Bulk backtest runner for multiple assets and timeframes.

Orchestrates the execution of backtests across all configured symbols and timeframes,
providing a consolidated summary report and leaderboard.
"""

import time
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

from src.backtest.analyzer import export_trade_log_csv
from src.backtest.vbt_runner import run_backtest
from src.config import AppSettings, AssetConfig, StrategyConfig, TimeframeConfig
from src.data_loader import get_connection, query_ohlcv
from src.fetchers.orchestrator import fetch_all_assets
from src.signals.cycles import detect_dominant_cycle_filtered
from src.signals.filters import calculate_atr_zscore_series
from src.signals.fractals import calculate_chop, calculate_rolling_hurst


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
    conn = get_connection(settings, read_only=True)

    # Group by Timeframe, NOT by Symbol
    for tf in tfs:
        logger.info(f"Processing timeframe: {tf}")

        close_dict, high_dict, low_dict = {}, {}, {}
        atr_dict, phase_dict, hurst_dict = {}, {}, {}
        ltf_dict, htf_dict, vol_z_dict, htf_dir_dict = {}, {}, {}, {}

        # 1. Fetch and calculate indicators for all symbols
        for sym in symbols:
            df = query_ohlcv(conn, sym, tf)
            if df.empty or len(df) < strategy.hurst_min_data_points:
                continue

            cycle_result = detect_dominant_cycle_filtered(df, cutoff=strategy.cycle_lowpass_cutoff)
            if not cycle_result:
                continue

            df_time = df.copy()
            df_time["timestamp"] = pd.to_datetime(df_time["timestamp"])
            df_time.set_index("timestamp", inplace=True)

            rolling_hurst = calculate_rolling_hurst(df_time, window=100).shift(1).ffill()

            close_dict[sym] = df_time["close_price"]
            high_dict[sym] = df_time["high_price"]
            low_dict[sym] = df_time["low_price"]

            atr_dict[sym] = _calculate_atr_series(df_time, period=14)
            phase_dict[sym] = pd.Series(cycle_result["phase_array"], index=df_time.index)
            hurst_dict[sym] = rolling_hurst

            # LTF metrics
            ltf_dict[sym] = calculate_chop(df_time)
            vol_z_dict[sym] = calculate_atr_zscore_series(df_time)

            # HTF metrics
            daily_df = df_time.resample("1D").agg({
                "open_price": "first",
                "high_price": "max",
                "low_price": "min",
                "close_price": "last",
                "volume": "sum"
            }).dropna()

            if not daily_df.empty:
                daily_chop = calculate_chop(daily_df, period=30)
                safe_daily_chop = daily_chop.shift(1)

                daily_sma = daily_df["close_price"].rolling(window=50).mean()
                daily_direction = np.where(daily_df["close_price"] > daily_sma, 1, -1)
                safe_daily_dir = pd.Series(daily_direction, index=daily_df.index).shift(1)

                htf_dict[sym] = safe_daily_chop.reindex(df_time.index).ffill().fillna(50.0)
                htf_dir_dict[sym] = safe_daily_dir.reindex(df_time.index).ffill().fillna(0)
            else:
                htf_dict[sym] = pd.Series(50.0, index=df_time.index)
                htf_dir_dict[sym] = pd.Series(0.0, index=df_time.index)

        if not close_dict:
            continue

        # 2. Build the 2D Matrices
        matrix_close = pd.DataFrame(close_dict).ffill().bfill()
        matrix_high = pd.DataFrame(high_dict).reindex(matrix_close.index).ffill().bfill()
        matrix_low = pd.DataFrame(low_dict).reindex(matrix_close.index).ffill().bfill()
        matrix_atr = pd.DataFrame(atr_dict).reindex(matrix_close.index).ffill().fillna(0.0)
        matrix_phase = pd.DataFrame(phase_dict).reindex(matrix_close.index).ffill().fillna(0.0)

        matrix_ltf = pd.DataFrame(ltf_dict).reindex(matrix_close.index).ffill().fillna(100.0)
        matrix_htf = pd.DataFrame(htf_dict).reindex(matrix_close.index).ffill().fillna(50.0)
        matrix_vol_z = pd.DataFrame(vol_z_dict).reindex(matrix_close.index).ffill().fillna(0.0)
        matrix_htf_dir = pd.DataFrame(htf_dir_dict).reindex(matrix_close.index).ffill().fillna(0.0)

        # Volatility-Adjusted Momentum Ranking
        lookback = 24
        momentum = matrix_close.diff(lookback)
        volatility_adjusted_momentum = momentum / matrix_atr
        matrix_rank = volatility_adjusted_momentum.fillna(0).replace([np.inf, -np.inf], 0)

        matrix_hurst_df = pd.DataFrame(hurst_dict).reindex(matrix_close.index).ffill().fillna(strategy.hurst_threshold)
        matrix_hurst = matrix_hurst_df.values

        # 3. Call the Engine EXACTLY ONCE with the full StrategyConfig
        freq_str = tf.replace("m", "min")
        res = run_backtest(
            close=matrix_close,
            high=matrix_high,
            low=matrix_low,
            atr=matrix_atr,
            phase_array=matrix_phase.values,
            hurst_value=matrix_hurst,
            ltf_metric=matrix_ltf.values,
            htf_metric=matrix_htf.values,
            volatility_zscore=matrix_vol_z.values,
            htf_direction=matrix_htf_dir.values,
            rank_metric=matrix_rank.values,
            macro_filter_type=strategy.macro_filter_type,
            htf_threshold=strategy.htf_threshold,
            ltf_threshold=strategy.ltf_threshold,
            veto_threshold=strategy.veto_threshold,
            hurst_threshold=strategy.hurst_threshold,
            trailing_multiplier=strategy.trailing_atr_multiplier,
            breakeven_threshold=strategy.breakeven_atr_threshold,
            max_concurrent_trades=strategy.max_concurrent_trades,
            risk_per_trade=strategy.risk_per_trade,
            initial_capital=strategy.backtest_initial_capital,
            commission=strategy.backtest_commission,
            freq=freq_str
        )

        if res:
            res["timeframe"] = tf
            res["symbol"] = "PORTFOLIO"
            res["best_hurst_threshold"] = strategy.hurst_threshold
            results.append(res)

            # Export trade log for this timeframe
            output_dir = Path(strategy.backtest_output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            csv_path = output_dir / f"trades_PORTFOLIO_{tf}.csv"
            export_trade_log_csv(res["portfolio"], str(csv_path), symbol="PORTFOLIO")

    conn.close()

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
