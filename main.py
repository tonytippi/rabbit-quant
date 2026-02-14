"""Rabbit-Quant: Local Quantitative Trading Workstation.

Entry point with CLI commands: fetch, backtest, dashboard.
"""

import argparse
import asyncio
import sys

from loguru import logger

from src.config import AppSettings, AssetConfig, StrategyConfig, TimeframeConfig, load_config
from src.data_loader import get_connection
from src.fetchers.orchestrator import fetch_all_assets

# Store config globally after load_config() so subcommands can access them
_settings: AppSettings
_assets: AssetConfig
_strategy: StrategyConfig
_timeframes: TimeframeConfig


def cmd_fetch(args: argparse.Namespace) -> None:
    """Fetch OHLCV data for configured assets."""
    logger.info("Starting data fetch...")
    conn = get_connection(_settings)
    try:
        result = asyncio.run(fetch_all_assets(conn, _assets, _timeframes))
        print(f"\nFetch Summary: {result.success}/{result.total} succeeded, "
              f"{result.rows_upserted} rows upserted in {result.elapsed_seconds:.1f}s")
        if result.failed > 0:
            print(f"Failed: {result.failed} symbol/timeframe combinations")
    finally:
        conn.close()


def cmd_backtest(args: argparse.Namespace) -> None:
    """Run backtesting with configured strategy."""
    from pathlib import Path

    from src.backtest.analyzer import export_trade_log_csv, find_best_params, recommend_config
    from src.backtest.vbt_runner import run_backtest, run_parameter_sweep
    from src.data_loader import query_ohlcv
    from src.signals.cycles import detect_dominant_cycle_filtered
    from src.signals.fractals import calculate_hurst

    logger.info("Starting backtest...")
    conn = get_connection(_settings)

    try:
        symbol = args.symbol
        timeframe = args.timeframe

        df = query_ohlcv(conn, symbol, timeframe)
        if df.empty:
            print(f"No data for {symbol}/{timeframe}. Run 'fetch' first.")
            return

        # Compute signals
        cycle_result = detect_dominant_cycle_filtered(df, cutoff=_strategy.cycle_lowpass_cutoff)
        hurst_value = calculate_hurst(df)

        if cycle_result is None:
            print(f"Could not detect cycle for {symbol}/{timeframe}")
            return

        close = df.set_index("timestamp")["close_price"]
        phase_array = cycle_result["phase_array"]

        if args.sweep:
            # Parameter sweep mode
            sweep_df = run_parameter_sweep(
                close, phase_array, hurst_value,
                hurst_range=_strategy.backtest_hurst_range,
                phase_long_range=_strategy.backtest_phase_long_range,
                phase_short_range=_strategy.backtest_phase_short_range,
                initial_capital=_strategy.backtest_initial_capital,
                commission=_strategy.backtest_commission,
            )

            # Show top results
            top = find_best_params(sweep_df, top_n=3)
            print(f"\nParameter Sweep Results ({len(sweep_df)} combinations):")
            print("Top 3 by Sharpe Ratio:")
            for i, row in top.iterrows():
                marker = " ← RECOMMENDED" if i == 0 else ""
                print(f"  #{i + 1}: Hurst≥{row['hurst_threshold']:.2f}, "
                      f"PhaseLong={row['phase_long']:.3f}, PhaseShort={row['phase_short']:.3f} | "
                      f"Sharpe={row['sharpe_ratio']:.4f}, Return={row['total_return']:.2f}%, "
                      f"MaxDD={row['max_drawdown']:.2f}%, WinRate={row['win_rate']:.1f}%{marker}")

            # Save sweep results
            output_dir = Path(_strategy.backtest_output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            sweep_path = output_dir / f"sweep_{symbol}_{timeframe}.csv"
            sweep_df.to_csv(sweep_path, index=False)
            print(f"\nFull results saved: {sweep_path}")

            # Show recommendation
            rec = recommend_config(sweep_df)
            if rec:
                print(f"\nRecommended config: hurst_threshold={rec['hurst_threshold']}")

        else:
            # Single backtest mode
            result = run_backtest(
                close, phase_array, hurst_value,
                hurst_threshold=_strategy.hurst_threshold,
                initial_capital=_strategy.backtest_initial_capital,
                commission=_strategy.backtest_commission,
            )

            if result is None:
                print("Backtest failed.")
                return

            print(f"\nBacktest Results for {symbol}/{timeframe}:")
            print(f"  Total Return: {result['total_return']:.2f}%")
            print(f"  Sharpe Ratio: {result['sharpe_ratio']:.4f}")
            print(f"  Max Drawdown: {result['max_drawdown']:.2f}%")
            print(f"  Win Rate:     {result['win_rate']:.1f}%")
            print(f"  Total Trades: {result['total_trades']}")

            # Export trade log
            output_dir = Path(_strategy.backtest_output_dir)
            csv_path = output_dir / f"trades_{symbol}_{timeframe}.csv"
            export_trade_log_csv(result["portfolio"], str(csv_path), symbol=symbol)

    finally:
        conn.close()


def cmd_dashboard(args: argparse.Namespace) -> None:
    """Launch Streamlit dashboard."""
    import subprocess

    logger.info("Launching dashboard...")
    subprocess.run([sys.executable, "-m", "streamlit", "run", "src/dashboard/app.py"], check=False)


def main() -> None:
    """Main entry point with CLI argument parsing."""
    global _settings, _assets, _strategy, _timeframes
    _settings, _assets, _strategy, _timeframes = load_config()

    parser = argparse.ArgumentParser(
        prog="rabbit-quant",
        description="Quant-Rabbit Local Core — High-performance quantitative trading workstation",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # fetch command
    fetch_parser = subparsers.add_parser("fetch", help="Fetch OHLCV data for configured assets")
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

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
