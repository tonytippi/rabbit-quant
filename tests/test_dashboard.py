"""Tests for src/dashboard/app.py — scanner data loading."""

import duckdb
import numpy as np
import pandas as pd

from src.dashboard.app import _bg_cache, _load_scanner_data


def _seed_db(db_path: str, symbol: str = "AAPL", timeframe: str = "1d", n: int = 500) -> None:
    """Insert sample OHLCV data into a test database."""
    conn = duckdb.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ohlcv (
            symbol VARCHAR,
            timeframe VARCHAR,
            timestamp TIMESTAMP,
            open_price DOUBLE,
            high_price DOUBLE,
            low_price DOUBLE,
            close_price DOUBLE,
            volume BIGINT,
            UNIQUE (symbol, timeframe, timestamp)
        )
    """)

    t = np.arange(n, dtype=np.float64)
    prices = 100.0 + 10.0 * np.sin(2.0 * np.pi * t / 50)
    dates = pd.date_range("2020-01-01", periods=n, freq="D")

    data = pd.DataFrame({
        "symbol": symbol,
        "timeframe": timeframe,
        "timestamp": dates,
        "open_price": prices - 0.5,
        "high_price": prices + 1.0,
        "low_price": prices - 1.0,
        "close_price": prices,
        "volume": np.random.default_rng(42).integers(1000, 10000, n),
    })

    conn.register("data_view", data)
    conn.execute("INSERT INTO ohlcv SELECT * FROM data_view")
    conn.close()


def _clear_bg_cache():
    """Clear the background cache for test isolation."""
    _bg_cache.clear()


class TestLoadScannerData:
    def test_returns_dataframe(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        _seed_db(db_path)

        _clear_bg_cache()
        result = _load_scanner_data(db_path)
        assert isinstance(result, pd.DataFrame)
        assert not result.empty

    def test_has_required_columns(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        _seed_db(db_path)

        _clear_bg_cache()
        result = _load_scanner_data(db_path)
        assert "Symbol" in result.columns
        assert "Hurst" in result.columns
        assert "Signal" in result.columns
        assert "Dominant Cycle" in result.columns

    def test_multiple_symbols(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        _seed_db(db_path, symbol="AAPL")
        _seed_db(db_path, symbol="MSFT")

        _clear_bg_cache()
        result = _load_scanner_data(db_path)
        assert len(result) == 2
        symbols = result["Symbol"].tolist()
        assert "AAPL" in symbols
        assert "MSFT" in symbols

    def test_empty_database(self, tmp_path):
        db_path = str(tmp_path / "empty.duckdb")
        conn = duckdb.connect(db_path)
        conn.execute("""
            CREATE TABLE ohlcv (
                symbol VARCHAR, timeframe VARCHAR, timestamp TIMESTAMP,
                open_price DOUBLE, high_price DOUBLE, low_price DOUBLE,
                close_price DOUBLE, volume BIGINT
            )
        """)
        conn.close()

        _clear_bg_cache()
        result = _load_scanner_data(db_path)
        assert result.empty

    def test_signal_values_are_valid(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        _seed_db(db_path)

        _clear_bg_cache()
        result = _load_scanner_data(db_path)
        valid_signals = {"LONG", "SHORT", "NEUTRAL"}
        for sig in result["Signal"]:
            assert sig in valid_signals

    def test_hurst_in_valid_range(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        _seed_db(db_path)

        _clear_bg_cache()
        result = _load_scanner_data(db_path)
        for h in result["Hurst"]:
            assert 0.0 <= h <= 1.0
