"""Tests for src/fetchers/orchestrator.py — concurrent fetch orchestration."""

from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from src.config import AppSettings, AssetConfig, TimeframeConfig
from src.data_loader import get_connection
from src.fetchers.orchestrator import fetch_all_assets


@pytest.fixture
def db_conn(tmp_path):
    settings = AppSettings(duckdb_path=str(tmp_path / "test.duckdb"))
    conn = get_connection(settings)
    yield conn
    conn.close()


@pytest.fixture
def mock_assets():
    """Minimal asset config for testing."""
    config = AssetConfig.__new__(AssetConfig)
    config.stock_symbols = ["AAPL"]
    config.crypto_symbols = ["BTC/USDT"]
    config.crypto_exchange = "binance"
    return config


@pytest.fixture
def mock_timeframes():
    """Minimal timeframe config for testing."""
    config = TimeframeConfig.__new__(TimeframeConfig)
    config.default_timeframes = ["1h"]
    config.yfinance_mapping = {"1h": "1h"}
    config.ccxt_mapping = {"1h": "1h"}
    return config


def _make_stock_df(symbol="AAPL", timeframe="1h"):
    return pd.DataFrame({
        "symbol": [symbol],
        "timeframe": [timeframe],
        "timestamp": pd.to_datetime(["2026-01-02 10:00"]),
        "open_price": [150.0],
        "high_price": [151.0],
        "low_price": [149.0],
        "close_price": [150.5],
        "volume": [1000.0],
    })


def _make_crypto_df(symbol="BTC/USDT", timeframe="1h"):
    return pd.DataFrame({
        "symbol": [symbol],
        "timeframe": [timeframe],
        "timestamp": pd.to_datetime(["2026-01-02 10:00"]),
        "open_price": [42000.0],
        "high_price": [42500.0],
        "low_price": [41800.0],
        "close_price": [42300.0],
        "volume": [100.5],
    })


class TestFetchAllAssets:
    @pytest.mark.asyncio
    @patch("src.fetchers.orchestrator.fetch_crypto_ohlcv", new_callable=AsyncMock)
    @patch("src.fetchers.orchestrator.fetch_stock_ohlcv")
    async def test_fetches_all_symbols(self, mock_stock, mock_crypto, db_conn, mock_assets, mock_timeframes):
        mock_stock.return_value = _make_stock_df()
        mock_crypto.return_value = _make_crypto_df()

        result = await fetch_all_assets(db_conn, mock_assets, mock_timeframes)

        assert result.total == 2  # 1 stock * 1 tf + 1 crypto * 1 tf
        assert result.success == 2
        assert result.failed == 0
        assert result.rows_upserted == 2

    @pytest.mark.asyncio
    @patch("src.fetchers.orchestrator.fetch_crypto_ohlcv", new_callable=AsyncMock)
    @patch("src.fetchers.orchestrator.fetch_stock_ohlcv")
    async def test_handles_partial_failures(self, mock_stock, mock_crypto, db_conn, mock_assets, mock_timeframes):
        mock_stock.return_value = _make_stock_df()
        mock_crypto.return_value = None  # Simulates fetch failure

        result = await fetch_all_assets(db_conn, mock_assets, mock_timeframes)

        assert result.total == 2
        assert result.success == 1
        assert result.failed == 1
        assert len(result.errors) == 1

    @pytest.mark.asyncio
    @patch("src.fetchers.orchestrator.fetch_crypto_ohlcv", new_callable=AsyncMock)
    @patch("src.fetchers.orchestrator.fetch_stock_ohlcv")
    async def test_handles_all_failures(self, mock_stock, mock_crypto, db_conn, mock_assets, mock_timeframes):
        mock_stock.return_value = None
        mock_crypto.return_value = None

        result = await fetch_all_assets(db_conn, mock_assets, mock_timeframes)

        assert result.success == 0
        assert result.failed == 2

    @pytest.mark.asyncio
    @patch("src.fetchers.orchestrator.fetch_crypto_ohlcv", new_callable=AsyncMock)
    @patch("src.fetchers.orchestrator.fetch_stock_ohlcv")
    async def test_records_elapsed_time(self, mock_stock, mock_crypto, db_conn, mock_assets, mock_timeframes):
        mock_stock.return_value = _make_stock_df()
        mock_crypto.return_value = _make_crypto_df()

        result = await fetch_all_assets(db_conn, mock_assets, mock_timeframes)

        assert result.elapsed_seconds >= 0

    @pytest.mark.asyncio
    @patch("src.fetchers.orchestrator.fetch_crypto_ohlcv", new_callable=AsyncMock)
    @patch("src.fetchers.orchestrator.fetch_stock_ohlcv")
    async def test_exception_in_fetcher_doesnt_crash(self, mock_stock, mock_crypto, db_conn, mock_assets, mock_timeframes):
        mock_stock.side_effect = Exception("unexpected error")
        mock_crypto.return_value = _make_crypto_df()

        result = await fetch_all_assets(db_conn, mock_assets, mock_timeframes)

        # Stock failed with exception, crypto succeeded
        assert result.success == 1
        assert result.failed == 1
