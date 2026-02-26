"""Performance metrics, trade log export, and auto-discovery.

Story 3.3 — Sharpe, Max Drawdown, Win Rate, Total Return calculation.
Story 3.4 — CSV trade log export.
Story 3.5 — Auto-discovery of best params and config recommendation.

Architecture boundary: reads backtest results, computes metrics, exports CSV.
Does NOT own backtesting execution or data fetching.
"""

from pathlib import Path

import pandas as pd
from loguru import logger

# Project root for config file updates
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"


def extract_trade_log(portfolio) -> pd.DataFrame:
    """Extract detailed trade log from VectorBT portfolio.

    Args:
        portfolio: VectorBT Portfolio object.

    Returns:
        DataFrame with columns: symbol, entry_time, exit_time, direction,
        size, entry_price, entry_value_usdt, exit_price, pnl, return_pct.
    """
    try:
        trades = portfolio.trades.records_readable
        if trades.empty:
            return pd.DataFrame(columns=[
                "symbol", "entry_time", "exit_time", "direction",
                "size", "entry_price", "entry_value_usdt", "exit_price", "pnl", "return_pct",
            ])

        log = pd.DataFrame({
            "symbol": trades["Column"].values,
            "entry_time": trades["Entry Timestamp"].values,
            "exit_time": trades["Exit Timestamp"].values,
            "direction": trades["Direction"].values,
            "size": trades["Size"].values,
            "entry_price": trades["Avg Entry Price"].values,
            "entry_value_usdt": trades["Size"].values * trades["Avg Entry Price"].values,
            "exit_price": trades["Avg Exit Price"].values,
            "pnl": trades["PnL"].values,
            "return_pct": trades["Return"].values * 100,
        })
        return log

    except Exception as e:
        logger.error(f"Trade log extraction failed: {e}")
        return pd.DataFrame()


def export_trade_log_csv(portfolio, output_path: str, symbol: str = "") -> str | None:
    """Export trade log to CSV file.

    Args:
        portfolio: VectorBT Portfolio object.
        output_path: Path for the CSV file.
        symbol: Fallback symbol name if not a multi-asset portfolio.

    Returns:
        Path to the saved CSV, or None on failure.
    """
    try:
        log = extract_trade_log(portfolio)

        # If the log only has one generic symbol or is empty, we can label it
        if symbol and (log.empty or (len(log['symbol'].unique()) == 1 and log['symbol'].iloc[0] == 0)):
             log['symbol'] = symbol

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        log.to_csv(path, index=False)
        logger.info(f"Trade log exported: {path} ({len(log)} trades)")
        return str(path)

    except Exception as e:
        logger.error(f"CSV export failed: {e}")
        return None


def compute_metrics(portfolio) -> dict:
    """Compute performance metrics from VectorBT portfolio.

    Returns:
        Dict with total_return, sharpe_ratio, max_drawdown, win_rate, total_trades.
    """
    try:
        stats = portfolio.stats()
        return {
            "total_return": float(stats.get("Total Return [%]", 0.0)),
            "sharpe_ratio": float(stats.get("Sharpe Ratio", 0.0)),
            "max_drawdown": float(stats.get("Max Drawdown [%]", 0.0)),
            "win_rate": float(stats.get("Win Rate [%]", 0.0)),
            "total_trades": int(stats.get("Total Trades", 0)),
        }
    except Exception as e:
        logger.error(f"Metrics computation failed: {e}")
        return {
            "total_return": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
        }


def find_best_params(sweep_results: pd.DataFrame, top_n: int = 3) -> pd.DataFrame:
    """Rank parameter sweep results by Sharpe Ratio.

    Args:
        sweep_results: DataFrame from run_parameter_sweep().
        top_n: Number of top results to return.

    Returns:
        DataFrame with top_n rows sorted by Sharpe Ratio descending.
    """
    if sweep_results.empty:
        return sweep_results

    # Filter out zero-trade results
    active = sweep_results[sweep_results["total_trades"] > 0]
    if active.empty:
        logger.warning("No parameter combinations produced trades")
        return sweep_results.head(top_n)

    ranked = active.sort_values("sharpe_ratio", ascending=False).head(top_n)
    return ranked.reset_index(drop=True)


def recommend_config(sweep_results: pd.DataFrame) -> dict | None:
    """Get recommended config from sweep results."""
    best = find_best_params(sweep_results, top_n=1)
    if best.empty:
        return None

    row = best.iloc[0]
    return {
        "hurst_threshold": float(row["hurst_threshold"]),
        "phase_long": float(row["phase_long"]),
        "phase_short": float(row["phase_short"]),
        "trailing_multiplier": float(row["trailing_multiplier"]) if "trailing_multiplier" in row else 2.0,
        "sharpe_ratio": float(row["sharpe_ratio"]),
        "max_drawdown": float(row["max_drawdown"]),
        "win_rate": float(row["win_rate"]),
        "total_return": float(row["total_return"]),
    }


def update_strategy_config(recommendation: dict) -> bool:
    """Update config/strategy.toml with recommended parameters."""
    config_path = CONFIG_DIR / "strategy.toml"

    try:
        if not config_path.exists():
            logger.error(f"Strategy config not found: {config_path}")
            return False

        content = config_path.read_text()

        # Update threshold value in TOML
        lines = content.split("\n")
        updated_lines = []
        current_section = ""

        for line in lines:
            trimmed = line.strip()
            if trimmed.startswith("[") and trimmed.endswith("]"):
                current_section = trimmed

            if current_section == "[hurst]" and trimmed.startswith("threshold"):
                updated_lines.append(f"threshold = {recommendation['hurst_threshold']}")
            elif current_section == "[risk]" and trimmed.startswith("trailing_atr_multiplier"):
                updated_lines.append(f"trailing_atr_multiplier = {recommendation['trailing_multiplier']}")
            elif current_section == "[cycle]" and trimmed.startswith("phase_long"): # if we added it
                 updated_lines.append(line) # keep as is or update if we add to toml
            else:
                updated_lines.append(line)

        config_path.write_text("\n".join(updated_lines))
        logger.info(f"Strategy config updated: {config_path}")
        return True

    except Exception as e:
        logger.error(f"Config update failed: {e}")
        return False
