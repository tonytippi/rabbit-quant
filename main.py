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
    logger.info("Starting backtest...")
    # TODO: Implement in Epic 3
    logger.info("Backtest not yet implemented")


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
