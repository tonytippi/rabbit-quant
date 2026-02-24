"""Rabbit-Quant: Local Quantitative Trading Workstation.

Entry point with CLI commands: fetch, backtest, dashboard.
"""

import argparse
import asyncio
import sys
import numpy as np

from loguru import logger

from src.config import AppSettings, AssetConfig, StrategyConfig, TimeframeConfig, PaperConfig, load_config
from src.data_loader import get_connection
from src.fetchers.orchestrator import fetch_all_assets

# Store config globally after load_config() so subcommands can access them
_settings: AppSettings
_assets: AssetConfig
_strategy: StrategyConfig
_timeframes: TimeframeConfig
_paper: PaperConfig


def cmd_fetch(args: argparse.Namespace) -> None:
    """Fetch OHLCV data for configured assets."""
    logger.info("Starting data fetch...")
    import time
    conn = get_connection(_settings)
    try:
        while True:
            result = asyncio.run(fetch_all_assets(conn, _assets, _timeframes))
            print(f"\nFetch Summary: {result.success}/{result.total} succeeded, "
                  f"{result.rows_upserted} rows upserted in {result.elapsed_seconds:.1f}s")
            if result.failed > 0:
                print(f"Failed: {result.failed} symbol/timeframe combinations")
            
            if not getattr(args, "continuous", False):
                break
                
            logger.info(f"Waiting {args.interval} minutes before next fetch...")
            time.sleep(args.interval * 60)
    except KeyboardInterrupt:
        logger.info("Continuous fetch stopped by user.")
    finally:
        conn.close()


def cmd_backtest(args: argparse.Namespace) -> None:
    """Run backtesting with configured strategy."""
    from pathlib import Path

    from src.backtest.analyzer import export_trade_log_csv, find_best_params, recommend_config, update_strategy_config
    from src.backtest.vbt_runner import run_backtest, run_parameter_sweep
    from src.data_loader import query_ohlcv
    from src.signals.cycles import detect_dominant_cycle_filtered
    from src.signals.fractals import calculate_hurst, calculate_chop
    from src.signals.filters import calculate_atr_zscore_series
    import pandas as pd

    logger.info("Starting backtest...")
    conn = get_connection(_settings)

    try:
        symbols = [s.strip() for s in args.symbol.split(",")]
        timeframe = args.timeframe
        vbt_freq = timeframe.replace("m", "min")

        # Dictionaries to hold series for each symbol
        closes = {}
        highs = {}
        lows = {}
        atrs = {}
        ltf_metrics = {}
        htf_metrics = {}
        volatility_zscores = {}
        htf_directions = {}
        phase_arrays = {}
        hurst_values = {} # We'll just take the mean for legacy or drop it

        for sym in symbols:
            df = query_ohlcv(conn, sym, timeframe)
            if df.empty:
                logger.warning(f"No data for {sym}/{timeframe}. Skipping.")
                continue

            df_time = df.copy()
            df_time["timestamp"] = pd.to_datetime(df_time["timestamp"])
            df_time.set_index("timestamp", inplace=True)
            
            # Basic Price
            closes[sym] = df_time["close_price"]
            highs[sym] = df_time["high_price"]
            lows[sym] = df_time["low_price"]
            
            # ATR
            tr1 = highs[sym] - lows[sym]
            tr2 = (highs[sym] - closes[sym].shift(1)).abs()
            tr3 = (lows[sym] - closes[sym].shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atrs[sym] = tr.rolling(window=14).mean().fillna(0.0)
            
            # LTF Metrics
            ltf_metrics[sym] = calculate_chop(df_time)
            volatility_zscores[sym] = calculate_atr_zscore_series(df_time)
            
            # HTF Metrics
            daily_df = df_time.resample("1D").agg({
                "open_price": "first",
                "high_price": "max",
                "low_price": "min",
                "close_price": "last",
                "volume": "sum"
            }).dropna()
            
            daily_chop = calculate_chop(daily_df)
            safe_daily_chop = daily_chop.shift(1)
            
            daily_sma = daily_df["close_price"].rolling(window=50).mean()
            daily_direction = np.where(daily_df["close_price"] > daily_sma, 1, -1)
            safe_daily_dir = pd.Series(daily_direction, index=daily_df.index).shift(1)
            
            htf_metrics[sym] = safe_daily_chop.reindex(df_time.index).ffill().fillna(50.0)
            htf_directions[sym] = safe_daily_dir.reindex(df_time.index).ffill().fillna(0)

            # Cycle
            cycle_result = detect_dominant_cycle_filtered(df, cutoff=_strategy.cycle_lowpass_cutoff)
            if cycle_result is None:
                logger.warning(f"No cycle found for {sym}")
                continue
            phase_arrays[sym] = pd.Series(cycle_result["phase_array"], index=df_time.index)
            hurst_values[sym] = calculate_hurst(df)

        if not closes:
            print("No valid data available for any provided symbols.")
            return

        # Combine into 2D DataFrames
        close_df = pd.DataFrame(closes).ffill().fillna(method='bfill')
        high_df = pd.DataFrame(highs).ffill().fillna(method='bfill')
        low_df = pd.DataFrame(lows).ffill().fillna(method='bfill')
        atr_df = pd.DataFrame(atrs).fillna(0.0)
        ltf_metric_df = pd.DataFrame(ltf_metrics).fillna(100.0)
        htf_metric_df = pd.DataFrame(htf_metrics).fillna(50.0)
        vol_z_df = pd.DataFrame(volatility_zscores).fillna(0.0)
        htf_dir_df = pd.DataFrame(htf_directions).fillna(0.0)
        phase_df = pd.DataFrame(phase_arrays).fillna(0.0)
        
        # Volatility-Adjusted Momentum Ranking (Phase 3.5)
        # 24-period lookback (e.g. 4 days on a 4H chart)
        lookback = 24
        momentum = close_df.diff(lookback)
        volatility_adjusted_momentum = momentum / atr_df
        # Clean NaNs and Infs for Numba compatibility
        rank_metric_df = volatility_adjusted_momentum.fillna(0).replace([np.inf, -np.inf], 0)
        
        avg_hurst = np.mean(list(hurst_values.values()))

        if args.sweep:
            # Parameter sweep mode
            sweep_df = run_parameter_sweep(
                close_df, high=high_df, low=low_df, atr=atr_df, phase_array=phase_df.values, hurst_value=avg_hurst,
                ltf_metric=ltf_metric_df.values, htf_metric=htf_metric_df.values, volatility_zscore=vol_z_df.values,
                htf_direction=htf_dir_df.values, rank_metric=rank_metric_df.values,
                hurst_range=_strategy.backtest_hurst_range,
                phase_long_range=_strategy.backtest_phase_long_range,
                phase_short_range=_strategy.backtest_phase_short_range,
                trailing_multiplier_range=_strategy.backtest_trailing_atr_multiplier_range,
                breakeven_threshold=_strategy.breakeven_atr_threshold,
                max_concurrent_trades=_strategy.max_concurrent_trades,
                risk_per_trade=_strategy.risk_per_trade,
                initial_capital=_strategy.backtest_initial_capital,
                commission=_strategy.backtest_commission,
                freq=vbt_freq,
            )

            # Show top results
            top = find_best_params(sweep_df, top_n=3)
            print(f"\nParameter Sweep Results ({len(sweep_df)} combinations):")
            print("Top 3 by Sharpe Ratio:")
            for i, row in top.iterrows():
                marker = " ← RECOMMENDED" if i == 0 else ""
                print(f"  #{i + 1}: Hurst≥{row['hurst_threshold']:.2f}, "
                      f"PhaseLong={row['phase_long']:.3f}, PhaseShort={row['phase_short']:.3f}, "
                      f"Trail={row['trailing_multiplier']:.1f}xATR | "
                      f"Sharpe={row['sharpe_ratio']:.4f}, Return={row['total_return']:.2f}%, "
                      f"MaxDD={row['max_drawdown']:.2f}%, WinRate={row['win_rate']:.1f}%{marker}")

            # Save sweep results
            output_dir = Path(_strategy.backtest_output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            sym_label = "PORTFOLIO" if len(symbols) > 1 else symbols[0]
            safe_symbol = sym_label.replace("/", "_")
            sweep_path = output_dir / f"sweep_{safe_symbol}_{timeframe}.csv"
            sweep_df.to_csv(sweep_path, index=False)
            print(f"\nFull results saved: {sweep_path}")

            # Show recommendation and prompt user to apply
            rec = recommend_config(sweep_df)
            if rec:
                print(f"\nRecommended config:")
                print(f"  hurst_threshold     = {rec['hurst_threshold']}")
                print(f"  phase_long          = {rec['phase_long']}")
                print(f"  phase_short         = {rec['phase_short']}")
                print(f"  trailing_multiplier = {rec['trailing_multiplier']}")
                print(f"  (Sharpe={rec['sharpe_ratio']:.4f}, "
                      f"Return={rec['total_return']:.2f}%, "
                      f"MaxDD={rec['max_drawdown']:.2f}%)")

                try:
                    answer = input("\nApply these parameters to strategy.toml? [y/N]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    answer = "n"

                if answer == "y":
                    if update_strategy_config(rec):
                        print("Strategy config updated successfully.")
                    else:
                        print("Failed to update config. Check logs for details.")
                else:
                    print("Skipped config update.")

        else:
            # Single backtest mode
            result = run_backtest(
                close_df, high=high_df, low=low_df, atr=atr_df, phase_array=phase_df.values, hurst_value=avg_hurst,
                ltf_metric=ltf_metric_df.values, htf_metric=htf_metric_df.values, volatility_zscore=vol_z_df.values,
                htf_direction=htf_dir_df.values, rank_metric=rank_metric_df.values,
                hurst_threshold=_strategy.hurst_threshold,
                trailing_multiplier=_strategy.trailing_atr_multiplier,
                breakeven_threshold=_strategy.breakeven_atr_threshold,
                max_concurrent_trades=_strategy.max_concurrent_trades,
                risk_per_trade=_strategy.risk_per_trade,
                initial_capital=_strategy.backtest_initial_capital,
                commission=_strategy.backtest_commission,
                freq=vbt_freq,
            )

            if result is None:
                print("Backtest failed.")
                return

            sym_label = "PORTFOLIO" if len(symbols) > 1 else symbols[0]
            print(f"\nBacktest Results for {sym_label}/{timeframe}:")
            print(f"  Total Return: {result['total_return']:.2f}%")
            print(f"  Sharpe Ratio: {result['sharpe_ratio']:.4f}")
            print(f"  Max Drawdown: {result['max_drawdown']:.2f}%")
            print(f"  Win Rate:     {result['win_rate']:.1f}%")
            print(f"  Total Trades: {result['total_trades']}")

            # Export trade log
            output_dir = Path(_strategy.backtest_output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            safe_symbol = sym_label.replace("/", "_")
            csv_path = output_dir / f"trades_{safe_symbol}_{timeframe}.csv"
            export_trade_log_csv(result["portfolio"], str(csv_path), symbol=sym_label)

    finally:
        conn.close()


def cmd_dashboard(args: argparse.Namespace) -> None:
    """Launch Streamlit dashboard."""
    import subprocess

    logger.info("Launching dashboard...")
    subprocess.run([sys.executable, "-m", "streamlit", "run", "src/dashboard/app.py"], check=False)


def main() -> None:
    """Main entry point with CLI argument parsing."""
    global _settings, _assets, _strategy, _timeframes, _paper
    _settings, _assets, _strategy, _timeframes, _paper = load_config()

    parser = argparse.ArgumentParser(
        prog="rabbit-quant",
        description="Quant-Rabbit Local Core — High-performance quantitative trading workstation",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # fetch command
    fetch_parser = subparsers.add_parser("fetch", help="Fetch OHLCV data for configured assets")
    fetch_parser.add_argument("--continuous", "-c", action="store_true", help="Run continuously in the background")
    fetch_parser.add_argument("--interval", "-i", type=int, default=5, help="Interval in minutes between fetches (default: 5)")
    fetch_parser.set_defaults(func=cmd_fetch)

    # backtest command
    backtest_parser = subparsers.add_parser("backtest", help="Run backtesting with configured strategy")
    backtest_parser.add_argument("--symbol", "-s", required=True, help="Symbol to backtest (e.g., AAPL)")
    backtest_parser.add_argument("--timeframe", "-t", default="1d", help="Timeframe (default: 1d)")
    backtest_parser.add_argument("--sweep", action="store_true", help="Run parameter sweep instead of single backtest")
    backtest_parser.set_defaults(func=cmd_backtest)

    # dashboard command
    dashboard_parser = subparsers.add_parser("dashboard", help="Launch Streamlit dashboard")
    dashboard_parser.set_defaults(func=cmd_dashboard)

    # backtest-all command
    bulk_parser = subparsers.add_parser("backtest-all", help="Run bulk backtest across all assets and timeframes")
    bulk_parser.add_argument("--type", default="crypto", choices=["crypto", "stocks"], help="Asset type (default: crypto)")
    bulk_parser.add_argument("--sweep", action="store_true", help="Run parameter sweep for optimization")
    bulk_parser.add_argument("--fetch", action="store_true", help="Fetch latest data before running")
    bulk_parser.set_defaults(func=cmd_backtest_all)

    # run-scheduler command
    scheduler_parser = subparsers.add_parser("run-scheduler", help="Run background data ingestion scheduler (Writer Service)")
    scheduler_parser.add_argument("--interval", "-i", type=int, default=5, help="Fetch interval in minutes (default: 5)")
    scheduler_parser.set_defaults(func=cmd_run_scheduler)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    args.func(args)


def cmd_run_scheduler(args: argparse.Namespace) -> None:
    """Run the Writer Service scheduler."""
    from src.services.scheduler import run_scheduler_service

    logger.info(f"Launching Writer Service with {args.interval}m interval...")
    asyncio.run(run_scheduler_service(_settings, _assets, _timeframes, _paper, interval=args.interval))


def cmd_backtest_all(args: argparse.Namespace) -> None:
    """Run bulk backtest command."""
    from src.backtest.bulk_runner import run_bulk_backtest

    # Run async function
    asyncio.run(run_bulk_backtest(
        _settings,
        _assets,
        _strategy,
        _timeframes,
        asset_type=args.type,
        sweep=args.sweep,
        fetch=args.fetch
    ))


if __name__ == "__main__":
    main()
