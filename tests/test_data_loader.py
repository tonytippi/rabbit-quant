"""Tests for src/data_loader.py — DuckDB schema and upsert operations."""

import pandas as pd
import pytest

from src.config import AppSettings
from src.data_loader import (
    OHLCV_COLUMNS,
    count_rows,
    get_connection,
    get_latest_timestamp,
    query_ohlcv,
    upsert_ohlcv,
)


@pytest.fixture
def db_conn(tmp_path):
    """Create an in-memory DuckDB connection with schema initialized."""
    settings = AppSettings(
        duckdb_path=str(tmp_path / "test.duckdb"),
        database_host="", database_name="", database_user=""
    )
    conn = get_connection(settings)
    yield conn
    conn.close()


@pytest.fixture
def sample_ohlcv_df():
    """Sample OHLCV DataFrame for testing."""
    return pd.DataFrame({
        "symbol": ["AAPL"] * 3,
        "timeframe": ["1h"] * 3,
        "timestamp": pd.to_datetime(["2026-01-01 09:00", "2026-01-01 10:00", "2026-01-01 11:00"]),
        "open_price": [150.0, 151.0, 152.0],
        "high_price": [151.0, 152.0, 153.0],
        "low_price": [149.0, 150.0, 151.0],
        "close_price": [150.5, 151.5, 152.5],
        "volume": [1000.0, 1100.0, 1200.0],
    })


class TestGetConnection:
    def test_creates_database_file(self, tmp_path):
        settings = AppSettings(
            duckdb_path=str(tmp_path / "new.duckdb"),
            database_host="", database_name="", database_user=""
        )
        conn = get_connection(settings)
        assert (tmp_path / "new.duckdb").exists()
        conn.close()

    def test_creates_ohlcv_table(self, db_conn):
        tables = db_conn.execute("SHOW TABLES").fetchdf()
        assert "ohlcv" in tables["name"].values

    def test_ohlcv_table_has_correct_columns(self, db_conn):
        columns = db_conn.execute("DESCRIBE ohlcv").fetchdf()
        col_names = columns["column_name"].tolist()
        for expected in OHLCV_COLUMNS:
            assert expected in col_names

    def test_creates_parent_directories(self, tmp_path):
        settings = AppSettings(
            duckdb_path=str(tmp_path / "subdir" / "deep" / "test.duckdb"),
            database_host="", database_name="", database_user=""
        )
        conn = get_connection(settings)
        assert (tmp_path / "subdir" / "deep" / "test.duckdb").exists()
        conn.close()

    def test_idempotent_table_creation(self, tmp_path):
        """Calling get_connection twice should not fail."""
        settings = AppSettings(
            duckdb_path=str(tmp_path / "test.duckdb"),
            database_host="", database_name="", database_user=""
        )
        conn1 = get_connection(settings)
        conn1.close()
        conn2 = get_connection(settings)
        tables = conn2.execute("SHOW TABLES").fetchdf()
        assert "ohlcv" in tables["name"].values
        conn2.close()


class TestUpsertOhlcv:
    def test_insert_new_rows(self, db_conn, sample_ohlcv_df):
        count = upsert_ohlcv(db_conn, sample_ohlcv_df)
        assert count == 3
        assert count_rows(db_conn) == 3

    def test_upsert_updates_existing_rows(self, db_conn, sample_ohlcv_df):
        upsert_ohlcv(db_conn, sample_ohlcv_df)

        # Modify close_price and re-upsert
        updated_df = sample_ohlcv_df.copy()
        updated_df["close_price"] = [200.0, 201.0, 202.0]
        upsert_ohlcv(db_conn, updated_df)

        # Should still be 3 rows (updated, not duplicated)
        assert count_rows(db_conn) == 3

        # Verify values were updated
        result = db_conn.execute(
            "SELECT close_price FROM ohlcv WHERE symbol = 'AAPL' ORDER BY timestamp"
        ).fetchdf()
        assert result["close_price"].tolist() == [200.0, 201.0, 202.0]

    def test_upsert_mixed_new_and_existing(self, db_conn, sample_ohlcv_df):
        upsert_ohlcv(db_conn, sample_ohlcv_df)

        # Add one new row + one overlapping
        mixed_df = pd.DataFrame({
            "symbol": ["AAPL", "AAPL"],
            "timeframe": ["1h", "1h"],
            "timestamp": pd.to_datetime(["2026-01-01 11:00", "2026-01-01 12:00"]),
            "open_price": [999.0, 153.0],
            "high_price": [999.0, 154.0],
            "low_price": [999.0, 152.0],
            "close_price": [999.0, 153.5],
            "volume": [9999.0, 1300.0],
        })
        upsert_ohlcv(db_conn, mixed_df)

        assert count_rows(db_conn) == 4  # 3 original + 1 new

    def test_no_duplicates_after_upsert(self, db_conn, sample_ohlcv_df):
        upsert_ohlcv(db_conn, sample_ohlcv_df)
        upsert_ohlcv(db_conn, sample_ohlcv_df)
        upsert_ohlcv(db_conn, sample_ohlcv_df)
        assert count_rows(db_conn) == 3

    def test_empty_dataframe_returns_zero(self, db_conn):
        empty_df = pd.DataFrame(columns=OHLCV_COLUMNS)
        assert upsert_ohlcv(db_conn, empty_df) == 0

    def test_none_dataframe_returns_zero(self, db_conn):
        assert upsert_ohlcv(db_conn, None) == 0

    def test_missing_columns_returns_zero(self, db_conn):
        bad_df = pd.DataFrame({"symbol": ["AAPL"], "timeframe": ["1h"]})
        assert upsert_ohlcv(db_conn, bad_df) == 0


class TestQueryOhlcv:
    def test_query_returns_matching_data(self, db_conn, sample_ohlcv_df):
        upsert_ohlcv(db_conn, sample_ohlcv_df)
        result = query_ohlcv(db_conn, "AAPL", "1h")
        assert len(result) == 3
        assert result["symbol"].iloc[0] == "AAPL"

    def test_query_returns_empty_for_missing_symbol(self, db_conn, sample_ohlcv_df):
        upsert_ohlcv(db_conn, sample_ohlcv_df)
        result = query_ohlcv(db_conn, "MSFT", "1h")
        assert len(result) == 0

    def test_query_with_limit(self, db_conn, sample_ohlcv_df):
        upsert_ohlcv(db_conn, sample_ohlcv_df)
        result = query_ohlcv(db_conn, "AAPL", "1h", limit=2)
        assert len(result) == 2

    def test_query_ordered_by_timestamp(self, db_conn, sample_ohlcv_df):
        upsert_ohlcv(db_conn, sample_ohlcv_df)
        result = query_ohlcv(db_conn, "AAPL", "1h")
        timestamps = result["timestamp"].tolist()
        assert timestamps == sorted(timestamps)


class TestGetLatestTimestamp:
    def test_returns_none_when_empty(self, db_conn):
        assert get_latest_timestamp(db_conn, "AAPL", "1h") is None

    def test_returns_max_timestamp(self, db_conn, sample_ohlcv_df):
        upsert_ohlcv(db_conn, sample_ohlcv_df)
        latest = get_latest_timestamp(db_conn, "AAPL", "1h")
        assert latest == pd.Timestamp("2026-01-01 11:00")

class TestCountRows:
    def test_count_all_rows(self, db_conn, sample_ohlcv_df):
        upsert_ohlcv(db_conn, sample_ohlcv_df)
        assert count_rows(db_conn) == 3

    def test_count_by_symbol(self, db_conn, sample_ohlcv_df):
        upsert_ohlcv(db_conn, sample_ohlcv_df)
        assert count_rows(db_conn, "AAPL") == 3
        assert count_rows(db_conn, "MSFT") == 0

    def test_count_empty_table(self, db_conn):
        assert count_rows(db_conn) == 0
