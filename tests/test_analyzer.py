"""Tests for src/backtest/analyzer.py — metrics, CSV export, auto-discovery."""

import numpy as np
import pandas as pd

from src.backtest.analyzer import (
    compute_metrics,
    export_trade_log_csv,
    extract_trade_log,
    find_best_params,
    recommend_config,
)
from src.backtest.vbt_runner import run_backtest


def _run_sample_backtest():
    """Helper: run a backtest that produces trades."""
    t = np.arange(500, dtype=np.float64)
    prices = 100.0 + 10.0 * np.sin(2.0 * np.pi * t / 50)
    dates = pd.date_range("2020-01-01", periods=500, freq="D")
    close = pd.Series(prices, index=dates)
    phase = (2.0 * np.pi * t / 50) % (2.0 * np.pi)

    return run_backtest(close, phase, 0.7, hurst_threshold=0.5)


class TestExtractTradeLog:
    def test_returns_dataframe(self):
        result = _run_sample_backtest()
        assert result is not None
        log = extract_trade_log(result["portfolio"])
        assert isinstance(log, pd.DataFrame)

    def test_has_required_columns(self):
        result = _run_sample_backtest()
        assert result is not None
        log = extract_trade_log(result["portfolio"])
        if not log.empty:
            assert "entry_time" in log.columns
            assert "exit_time" in log.columns
            assert "pnl" in log.columns
            assert "return_pct" in log.columns


class TestExportTradeLogCsv:
    def test_creates_csv_file(self, tmp_path):
        result = _run_sample_backtest()
        assert result is not None
        csv_path = str(tmp_path / "trades.csv")
        saved = export_trade_log_csv(result["portfolio"], csv_path, symbol="TEST")
        assert saved is not None
        assert (tmp_path / "trades.csv").exists()

    def test_csv_contains_symbol_column(self, tmp_path):
        result = _run_sample_backtest()
        assert result is not None
        csv_path = str(tmp_path / "trades.csv")
        export_trade_log_csv(result["portfolio"], csv_path, symbol="AAPL")
        df = pd.read_csv(csv_path)
        if not df.empty:
            assert "symbol" in df.columns
            assert df["symbol"].iloc[0] == "AAPL"

    def test_creates_parent_directories(self, tmp_path):
        result = _run_sample_backtest()
        assert result is not None
        csv_path = str(tmp_path / "subdir" / "deep" / "trades.csv")
        saved = export_trade_log_csv(result["portfolio"], csv_path)
        assert saved is not None


class TestComputeMetrics:
    def test_returns_dict_with_keys(self):
        result = _run_sample_backtest()
        assert result is not None
        metrics = compute_metrics(result["portfolio"])
        assert "total_return" in metrics
        assert "sharpe_ratio" in metrics
        assert "max_drawdown" in metrics
        assert "win_rate" in metrics
        assert "total_trades" in metrics


class TestFindBestParams:
    def test_returns_top_n(self):
        sweep = pd.DataFrame({
            "hurst_threshold": [0.5, 0.6, 0.7, 0.8],
            "phase_long": [4.712] * 4,
            "phase_short": [1.571] * 4,
            "total_return": [10, 20, 15, 5],
            "sharpe_ratio": [0.5, 1.2, 0.8, 0.3],
            "max_drawdown": [10, 5, 8, 15],
            "win_rate": [55, 60, 58, 45],
            "total_trades": [10, 15, 12, 8],
        })
        top = find_best_params(sweep, top_n=2)
        assert len(top) == 2
        assert top.iloc[0]["sharpe_ratio"] == 1.2  # best Sharpe first

    def test_empty_input(self):
        empty = pd.DataFrame()
        result = find_best_params(empty)
        assert result.empty

    def test_filters_zero_trade_results(self):
        sweep = pd.DataFrame({
            "hurst_threshold": [0.5, 0.6],
            "phase_long": [4.712, 4.712],
            "phase_short": [1.571, 1.571],
            "total_return": [0, 10],
            "sharpe_ratio": [0, 0.8],
            "max_drawdown": [0, 5],
            "win_rate": [0, 60],
            "total_trades": [0, 5],
        })
        top = find_best_params(sweep, top_n=3)
        assert len(top) == 1
        assert top.iloc[0]["total_trades"] == 5


class TestRecommendConfig:
    def test_returns_best_params(self):
        sweep = pd.DataFrame({
            "hurst_threshold": [0.5, 0.6, 0.7],
            "phase_long": [4.712, 4.4, 5.0],
            "phase_short": [1.571, 1.3, 1.8],
            "total_return": [10, 25, 15],
            "sharpe_ratio": [0.5, 1.5, 0.9],
            "max_drawdown": [10, 3, 7],
            "win_rate": [55, 65, 58],
            "total_trades": [10, 20, 15],
        })
        rec = recommend_config(sweep)
        assert rec is not None
        assert rec["hurst_threshold"] == 0.6
        assert rec["sharpe_ratio"] == 1.5

    def test_returns_none_for_empty(self):
        assert recommend_config(pd.DataFrame()) is None
