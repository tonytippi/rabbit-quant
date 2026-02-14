"""Tests for src/fetchers/crypto_fetcher.py — crypto data fetching and transformation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.fetchers.crypto_fetcher import fetch_crypto_ohlcv


@pytest.fixture
def mock_ohlcv_data():
    """Sample OHLCV data as ccxt returns it (list of lists)."""
    return [
        [1704153600000, 42000.0, 42500.0, 41800.0, 42300.0, 100.5],  # 2024-01-02 00:00
        [1704157200000, 42300.0, 42800.0, 42100.0, 42600.0, 110.2],  # 2024-01-02 01:00
        [1704160800000, 42600.0, 43000.0, 42400.0, 42900.0, 95.8],   # 2024-01-02 02:00
    ]


class TestFetchCryptoOhlcv:
    @pytest.mark.asyncio
    @patch("src.fetchers.crypto_fetcher.ccxt_async")
    async def test_returns_standardized_dataframe(self, mock_ccxt, mock_ohlcv_data):
        mock_exchange = AsyncMock()
        mock_exchange.fetch_ohlcv = AsyncMock(return_value=mock_ohlcv_data)
        mock_exchange.close = AsyncMock()

        mock_exchange_cls = MagicMock(return_value=mock_exchange)
        mock_ccxt.binance = mock_exchange_cls

        df = await fetch_crypto_ohlcv("BTC/USDT", "1h", "1h", "binance")

        assert df is not None
        assert len(df) == 3
        assert df["symbol"].iloc[0] == "BTC/USDT"
        assert df["timeframe"].iloc[0] == "1h"
        assert "open_price" in df.columns
        assert "close_price" in df.columns
        assert "volume" in df.columns

    @pytest.mark.asyncio
    @patch("src.fetchers.crypto_fetcher.ccxt_async")
    async def test_returns_none_on_empty_data(self, mock_ccxt):
        mock_exchange = AsyncMock()
        mock_exchange.fetch_ohlcv = AsyncMock(return_value=[])
        mock_exchange.close = AsyncMock()

        mock_exchange_cls = MagicMock(return_value=mock_exchange)
        mock_ccxt.binance = mock_exchange_cls

        result = await fetch_crypto_ohlcv("BTC/USDT", "1h", "1h", "binance")
        assert result is None

    @pytest.mark.asyncio
    @patch("src.fetchers.crypto_fetcher.ccxt_async")
    async def test_handles_unsupported_exchange(self, mock_ccxt):
        mock_ccxt.nonexistent = None
        delattr(mock_ccxt, "nonexistent")

        result = await fetch_crypto_ohlcv("BTC/USDT", "1h", "1h", "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    @patch("src.fetchers.crypto_fetcher.ccxt_async")
    async def test_handles_api_error_gracefully(self, mock_ccxt):
        mock_exchange = AsyncMock()
        mock_exchange.fetch_ohlcv = AsyncMock(side_effect=Exception("Connection refused"))
        mock_exchange.close = AsyncMock()

        mock_exchange_cls = MagicMock(return_value=mock_exchange)
        mock_ccxt.binance = mock_exchange_cls

        result = await fetch_crypto_ohlcv("BTC/USDT", "1h", "1h", "binance")
        assert result is None

    @pytest.mark.asyncio
    @patch("src.fetchers.crypto_fetcher.ccxt_async")
    async def test_closes_exchange_on_success(self, mock_ccxt, mock_ohlcv_data):
        mock_exchange = AsyncMock()
        mock_exchange.fetch_ohlcv = AsyncMock(return_value=mock_ohlcv_data)
        mock_exchange.close = AsyncMock()

        mock_exchange_cls = MagicMock(return_value=mock_exchange)
        mock_ccxt.binance = mock_exchange_cls

        await fetch_crypto_ohlcv("BTC/USDT", "1h", "1h", "binance")
        mock_exchange.close.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.fetchers.crypto_fetcher.ccxt_async")
    async def test_closes_exchange_on_error(self, mock_ccxt):
        mock_exchange = AsyncMock()
        mock_exchange.fetch_ohlcv = AsyncMock(side_effect=Exception("fail"))
        mock_exchange.close = AsyncMock()

        mock_exchange_cls = MagicMock(return_value=mock_exchange)
        mock_ccxt.binance = mock_exchange_cls

        await fetch_crypto_ohlcv("BTC/USDT", "1h", "1h", "binance")
        mock_exchange.close.assert_called_once()
