"""Rabbit-Quant: Local Quantitative Trading Workstation.

Entry point with CLI commands: fetch, backtest, dashboard.
"""

import argparse
import sys

from loguru import logger

from src.config import load_config


def cmd_fetch(args: argparse.Namespace) -> None:
    """Fetch OHLCV data for configured assets."""
    logger.info("Starting data fetch...")
    # TODO: Implement in Epic 1 Story 1.3/1.4
    logger.info("Data fetch not yet implemented")


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
    settings, assets, strategy, timeframes = load_config()

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
