"""Data loader module for Rabbit-Quant.

Handles DuckDB schema initialization and OHLCV data upsert operations.
This is the ONLY module that writes to the database (per Architecture doc).
"""

from pathlib import Path

import duckdb
import pandas as pd
from loguru import logger

from src.config import PROJECT_ROOT, AppSettings

# Expected OHLCV DataFrame columns for insert
OHLCV_COLUMNS = ["symbol", "timeframe", "timestamp", "open_price", "high_price", "low_price", "close_price", "volume"]

# SQL for creating the ohlcv table
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ohlcv (
    symbol      VARCHAR NOT NULL,
    timeframe   VARCHAR NOT NULL,
    timestamp   TIMESTAMP NOT NULL,
    open_price  DOUBLE NOT NULL,
    high_price  DOUBLE NOT NULL,
    low_price   DOUBLE NOT NULL,
    close_price DOUBLE NOT NULL,
    volume      DOUBLE NOT NULL,
    UNIQUE (symbol, timeframe, timestamp)
)
"""

# SQL for upserting data — insert or replace on conflict
UPSERT_SQL = """
INSERT OR REPLACE INTO ohlcv (symbol, timeframe, timestamp, open_price, high_price, low_price, close_price, volume)
SELECT symbol, timeframe, timestamp, open_price, high_price, low_price, close_price, volume
FROM df_stage
"""


def _resolve_db_path(settings: AppSettings) -> Path:
    """Resolve the DuckDB path relative to project root."""
    db_path = Path(settings.duckdb_path)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def get_connection(settings: AppSettings, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Get a DuckDB connection, creating the database and table if needed."""
    db_path = _resolve_db_path(settings)
    conn = duckdb.connect(str(db_path), read_only=read_only)
    if not read_only:
        conn.execute(CREATE_TABLE_SQL)
    logger.debug(f"DuckDB connected: {db_path} (read_only={read_only})")
    return conn


def upsert_ohlcv(conn: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Upsert OHLCV data into DuckDB. Returns number of rows upserted.

    Args:
        conn: Active DuckDB connection.
        df: DataFrame with columns matching OHLCV_COLUMNS.

    Returns:
        Number of rows processed. Returns 0 if df is empty or invalid.
    """
    if df is None or df.empty:
        logger.warning("Empty DataFrame passed to upsert_ohlcv, skipping")
        return 0

    # Validate required columns
    missing = set(OHLCV_COLUMNS) - set(df.columns)
    if missing:
        logger.error(f"DataFrame missing required columns: {missing}")
        return 0

    # Select only required columns in correct order
    df_stage = df[OHLCV_COLUMNS].copy()

    # Ensure timestamp is datetime
    df_stage["timestamp"] = pd.to_datetime(df_stage["timestamp"])

    row_count = len(df_stage)
    conn.execute(UPSERT_SQL)
    logger.info(f"Upserted {row_count} rows for {df_stage['symbol'].iloc[0]}/{df_stage['timeframe'].iloc[0]}")
    return row_count


def query_ohlcv(
    conn: duckdb.DuckDBPyConnection,
    symbol: str,
    timeframe: str,
    limit: int | None = None,
) -> pd.DataFrame:
    """Query OHLCV data from DuckDB.

    Args:
        conn: Active DuckDB connection.
        symbol: Asset symbol (e.g., "AAPL", "BTC/USDT").
        timeframe: Timeframe string (e.g., "1h", "4h").
        limit: Optional row limit (most recent first).

    Returns:
        DataFrame with OHLCV data, or empty DataFrame on error.
    """
    try:
        query = "SELECT * FROM ohlcv WHERE symbol = ? AND timeframe = ? ORDER BY timestamp"
        params = [symbol, timeframe]
        if limit:
            query += " DESC LIMIT ?"
            params.append(limit)
        result = conn.execute(query, params).fetchdf()
        if limit:
            result = result.sort_values("timestamp").reset_index(drop=True)
        return result
    except Exception as e:
        logger.error(f"Failed to query OHLCV for {symbol}/{timeframe}: {e}")
        return pd.DataFrame()


def count_rows(conn: duckdb.DuckDBPyConnection, symbol: str | None = None) -> int:
    """Count rows in ohlcv table, optionally filtered by symbol."""
    try:
        if symbol:
            result = conn.execute("SELECT COUNT(*) FROM ohlcv WHERE symbol = ?", [symbol]).fetchone()
        else:
            result = conn.execute("SELECT COUNT(*) FROM ohlcv").fetchone()
        return result[0] if result else 0
    except Exception as e:
        logger.error(f"Failed to count rows: {e}")
        return 0
