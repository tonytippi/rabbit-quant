"""Tests for src/fetchers/stock_fetcher.py — stock data fetching and transformation."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.fetchers.stock_fetcher import _resample_to_4h, fetch_stock_ohlcv


@pytest.fixture
def mock_yf_history():
    """Mock yfinance ticker history response."""
    df = pd.DataFrame({
        "Open": [150.0, 151.0, 152.0],
        "High": [151.0, 152.0, 153.0],
        "Low": [149.0, 150.0, 151.0],
        "Close": [150.5, 151.5, 152.5],
        "Volume": [1000, 1100, 1200],
    }, index=pd.to_datetime(["2026-01-02 09:00", "2026-01-02 10:00", "2026-01-02 11:00"]))
    df.index.name = "Datetime"
    return df


class TestFetchStockOhlcv:
    @patch("src.fetchers.stock_fetcher.yf.Ticker")
    def test_returns_standardized_dataframe(self, mock_ticker_cls, mock_yf_history):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_yf_history
        mock_ticker_cls.return_value = mock_ticker

        df = fetch_stock_ohlcv("AAPL", "1h", "1h")

        assert df is not None
        assert len(df) == 3
        assert "symbol" in df.columns
        assert "timeframe" in df.columns
        assert df["symbol"].iloc[0] == "AAPL"
        assert df["timeframe"].iloc[0] == "1h"
        assert "open_price" in df.columns
        assert "close_price" in df.columns

    @patch("src.fetchers.stock_fetcher.yf.Ticker")
    def test_returns_none_on_empty_data(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        result = fetch_stock_ohlcv("INVALID", "1h", "1h")
        assert result is None

    @patch("src.fetchers.stock_fetcher.yf.Ticker")
    def test_handles_api_error_gracefully(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = Exception("API error")
        mock_ticker_cls.return_value = mock_ticker

        result = fetch_stock_ohlcv("AAPL", "1h", "1h")
        assert result is None

    @patch("src.fetchers.stock_fetcher.yf.Ticker")
    def test_removes_timezone_from_timestamps(self, mock_ticker_cls, mock_yf_history):
        # Add timezone info to simulate real yfinance output
        mock_yf_history.index = mock_yf_history.index.tz_localize("US/Eastern")
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_yf_history
        mock_ticker_cls.return_value = mock_ticker

        df = fetch_stock_ohlcv("AAPL", "1h", "1h")
        assert df is not None
        assert df["timestamp"].dt.tz is None


class TestResampleTo4h:
    def test_resamples_1h_to_4h(self):
        timestamps = pd.date_range("2026-01-02 00:00", periods=8, freq="1h")
        df = pd.DataFrame({
            "timestamp": timestamps,
            "open_price": [100, 101, 102, 103, 104, 105, 106, 107],
            "high_price": [101, 102, 103, 104, 105, 106, 107, 108],
            "low_price": [99, 100, 101, 102, 103, 104, 105, 106],
            "close_price": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5],
            "volume": [1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700],
        })

        result = _resample_to_4h(df)
        assert result is not None
        assert len(result) == 2  # 8 hours / 4h = 2 bars

        # First 4h bar: open=first, high=max, low=min, close=last, volume=sum
        assert result["open_price"].iloc[0] == 100
        assert result["high_price"].iloc[0] == 104
        assert result["low_price"].iloc[0] == 99
        assert result["close_price"].iloc[0] == 103.5
        assert result["volume"].iloc[0] == 4600  # 1000+1100+1200+1300

    def test_handles_empty_dataframe(self):
        df = pd.DataFrame(columns=["timestamp", "open_price", "high_price", "low_price", "close_price", "volume"])
        result = _resample_to_4h(df)
        assert result is not None
        assert len(result) == 0
