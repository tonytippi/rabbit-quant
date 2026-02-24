"""Data loader module for Rabbit-Quant.

Handles database connections (DuckDB or PostgreSQL) and OHLCV data operations.
Supports switching backend based on configuration.
"""

from pathlib import Path
from typing import Union, Any

import duckdb
import pandas as pd
from loguru import logger
from sqlalchemy import create_engine, text, Table, Column, String, Float, DateTime, MetaData, UniqueConstraint, Boolean
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection as AlchemyConnection

from src.config import PROJECT_ROOT, AppSettings

# Type alias for our DB connection
DBConnection = Union[duckdb.DuckDBPyConnection, AlchemyConnection]

# Expected OHLCV DataFrame columns for insert
OHLCV_COLUMNS = ["symbol", "timeframe", "timestamp", "open_price", "high_price", "low_price", "close_price", "volume"]

# DuckDB SQL
DUCKDB_CREATE_SQL = """
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
);

CREATE TABLE IF NOT EXISTS portfolio_state (
    id              INTEGER PRIMARY KEY,
    current_balance DOUBLE NOT NULL,
    initial_balance DOUBLE NOT NULL,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS paper_trades (
    id          INTEGER PRIMARY KEY,
    symbol      VARCHAR NOT NULL,
    timeframe   VARCHAR NOT NULL,
    side        VARCHAR NOT NULL,
    entry_price DOUBLE NOT NULL,
    quantity    DOUBLE NOT NULL,
    tp          DOUBLE NOT NULL,
    sl          DOUBLE NOT NULL,
    status      VARCHAR NOT NULL,
    ltf_hurst   DOUBLE,
    htf_hurst   DOUBLE,
    veto_z      DOUBLE,
    highest_price DOUBLE,
    lowest_price  DOUBLE,
    is_breakeven  BOOLEAN DEFAULT FALSE,
    exit_price  DOUBLE,
    pnl         DOUBLE,
    entry_time  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    exit_time   TIMESTAMP
);
CREATE SEQUENCE IF NOT EXISTS seq_paper_trades_id START 1;
"""

DUCKDB_UPSERT_SQL = """
INSERT OR REPLACE INTO ohlcv (symbol, timeframe, timestamp, open_price, high_price, low_price, close_price, volume)
SELECT symbol, timeframe, timestamp, open_price, high_price, low_price, close_price, volume
FROM df_stage
"""

# SQLAlchemy Metadata for Postgres
metadata = MetaData()
ohlcv_table = Table(
    "ohlcv", metadata,
    Column("symbol", String, nullable=False),
    Column("timeframe", String, nullable=False),
    Column("timestamp", DateTime, nullable=False),
    Column("open_price", Float, nullable=False),
    Column("high_price", Float, nullable=False),
    Column("low_price", Float, nullable=False),
    Column("close_price", Float, nullable=False),
    Column("volume", Float, nullable=False),
    UniqueConstraint("symbol", "timeframe", "timestamp", name="uq_ohlcv_candle")
)

portfolio_table = Table(
    "portfolio_state", metadata,
    Column("id", String, primary_key=True), # Singleton row 'main'
    Column("current_balance", Float, nullable=False),
    Column("initial_balance", Float, nullable=False),
    Column("updated_at", DateTime, nullable=False)
)

trades_table = Table(
    "paper_trades", metadata,
    Column("id", String, primary_key=True), # UUID or Int
    Column("symbol", String, nullable=False),
    Column("timeframe", String, nullable=False),
    Column("side", String, nullable=False),
    Column("entry_price", Float, nullable=False),
    Column("quantity", Float, nullable=False),
    Column("tp", Float, nullable=False),
    Column("sl", Float, nullable=False),
    Column("status", String, nullable=False), # OPEN, CLOSED
    Column("ltf_hurst", Float, nullable=True),
    Column("htf_hurst", Float, nullable=True),
    Column("veto_z", Float, nullable=True),
    Column("highest_price", Float, nullable=True),
    Column("lowest_price", Float, nullable=True),
    Column("is_breakeven", Boolean, default=False),
    Column("exit_price", Float, nullable=True),
    Column("pnl", Float, nullable=True),
    Column("entry_time", DateTime, nullable=False),
    Column("exit_time", DateTime, nullable=True)
)


def _resolve_db_path(settings: AppSettings) -> Path:
    """Resolve the DuckDB path relative to project root."""
    db_path = Path(settings.duckdb_path)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def get_connection(settings: AppSettings, read_only: bool = False) -> DBConnection:
    """Get a database connection (DuckDB or Postgres)."""
    
    if settings.use_postgres:
        # PostgreSQL Connection
        try:
            engine = create_engine(settings.database_url)
            conn = engine.connect()
            
            # Ensure schema exists (if not read_only, though 'create_all' is safe)
            if not read_only:
                metadata.create_all(conn)
                # Init portfolio if empty
                _init_postgres_portfolio(conn)
                
            logger.debug(f"Postgres connected: {settings.database_host}")
            return conn
        except Exception as e:
            logger.error(f"Postgres connection failed: {e}")
            raise

    else:
        # DuckDB Connection
        db_path = _resolve_db_path(settings)
        try:
            conn = duckdb.connect(str(db_path), read_only=read_only)
            if not read_only:
                conn.execute(DUCKDB_CREATE_SQL)
                _init_duckdb_portfolio(conn)
            logger.debug(f"DuckDB connected: {db_path} (read_only={read_only})")
            return conn
        except Exception as e:
            logger.error(f"DuckDB connection failed: {e}")
            raise


def _init_duckdb_portfolio(conn: duckdb.DuckDBPyConnection) -> None:
    """Initialize portfolio state if empty."""
    res = conn.execute("SELECT COUNT(*) FROM portfolio_state").fetchone()
    if res and res[0] == 0:
        conn.execute("INSERT INTO portfolio_state (id, current_balance, initial_balance) VALUES (1, 10000.0, 10000.0)")


def _init_postgres_portfolio(conn: AlchemyConnection) -> None:
    """Initialize portfolio state if empty."""
    from sqlalchemy import select, insert, func
    res = conn.execute(select(func.count()).select_from(portfolio_table)).scalar()
    if res == 0:
        conn.execute(insert(portfolio_table).values(
            id="main", 
            current_balance=10000.0, 
            initial_balance=10000.0,
            updated_at=pd.Timestamp.utcnow()
        ))
        conn.commit()


def reset_portfolio(conn: DBConnection, initial_balance: float = 10000.0) -> None:
    """Reset paper trading portfolio."""
    try:
        if isinstance(conn, duckdb.DuckDBPyConnection):
            conn.execute("DELETE FROM paper_trades")
            conn.execute("DELETE FROM portfolio_state")
            conn.execute(f"INSERT INTO portfolio_state (id, current_balance, initial_balance) VALUES (1, {initial_balance}, {initial_balance})")
            logger.info("Portfolio reset (DuckDB)")
        else:
            from sqlalchemy import delete, insert
            conn.execute(delete(trades_table))
            conn.execute(delete(portfolio_table))
            conn.execute(insert(portfolio_table).values(
                id="main",
                current_balance=initial_balance,
                initial_balance=initial_balance,
                updated_at=pd.Timestamp.utcnow()
            ))
            conn.commit()
            logger.info("Portfolio reset (Postgres)")
    except Exception as e:
        logger.error(f"Failed to reset portfolio: {e}")


def upsert_ohlcv(conn: DBConnection, df: pd.DataFrame) -> int:
    """Upsert OHLCV data into the database."""
    if df is None or df.empty:
        logger.warning("Empty DataFrame passed to upsert_ohlcv, skipping")
        return 0

    missing = set(OHLCV_COLUMNS) - set(df.columns)
    if missing:
        logger.error(f"DataFrame missing required columns: {missing}")
        return 0

    df_stage = df[OHLCV_COLUMNS].copy()
    df_stage["timestamp"] = pd.to_datetime(df_stage["timestamp"])
    row_count = len(df_stage)

    try:
        # Check connection type
        if isinstance(conn, duckdb.DuckDBPyConnection):
            # DuckDB Path
            conn.execute(DUCKDB_UPSERT_SQL)
            logger.info(f"Upserted {row_count} rows (DuckDB) for {df_stage['symbol'].iloc[0]}")
            
        else:
            # Postgres Path (SQLAlchemy)
            # Convert DataFrame to list of dicts
            records = df_stage.to_dict(orient="records")
            
            # Postgres Insert with ON CONFLICT
            stmt = pg_insert(ohlcv_table).values(records)
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol", "timeframe", "timestamp"],
                set_={
                    "open_price": stmt.excluded.open_price,
                    "high_price": stmt.excluded.high_price,
                    "low_price": stmt.excluded.low_price,
                    "close_price": stmt.excluded.close_price,
                    "volume": stmt.excluded.volume,
                }
            )
            conn.execute(stmt)
            conn.commit()
            logger.info(f"Upserted {row_count} rows (Postgres) for {df_stage['symbol'].iloc[0]}")

        return row_count

    except Exception as e:
        logger.error(f"Upsert failed: {e}")
        return 0


def query_ohlcv(
    conn: DBConnection,
    symbol: str,
    timeframe: str,
    limit: int | None = None,
) -> pd.DataFrame:
    """Query OHLCV data."""
    try:
        if isinstance(conn, duckdb.DuckDBPyConnection):
            # DuckDB
            query = "SELECT * FROM ohlcv WHERE symbol = ? AND timeframe = ? ORDER BY timestamp"
            params = [symbol, timeframe]
            if limit:
                query += " DESC LIMIT ?"
                params.append(limit)
            
            result = conn.execute(query, params).fetchdf()
            if limit:
                result = result.sort_values("timestamp").reset_index(drop=True)
            return result
            
        else:
            # Postgres (SQLAlchemy)
            # We construct a select statement
            query = ohlcv_table.select().where(
                ohlcv_table.c.symbol == symbol,
                ohlcv_table.c.timeframe == timeframe
            ).order_by(ohlcv_table.c.timestamp)
            
            # Since we can't easily do 'DESC LIMIT' then resort in pure SQL without subquery, 
            # we'll fetch all or handle limit efficiently.
            # Postgres optimization: if limit is small, maybe order desc limit X?
            
            if limit:
                # Fetch recent: Order DESC, Limit X
                query = ohlcv_table.select().where(
                    ohlcv_table.c.symbol == symbol,
                    ohlcv_table.c.timeframe == timeframe
                ).order_by(ohlcv_table.c.timestamp.desc()).limit(limit)
            
            result = pd.read_sql(query, conn)
            
            if limit:
                # Sort back to ASC
                result = result.sort_values("timestamp").reset_index(drop=True)
                
            return result

    except Exception as e:
        logger.error(f"Failed to query OHLCV for {symbol}/{timeframe}: {e}")
        return pd.DataFrame()


def get_latest_timestamp(conn: DBConnection, symbol: str, timeframe: str) -> pd.Timestamp | None:
    """Get the latest timestamp for a given symbol and timeframe."""
    try:
        if isinstance(conn, duckdb.DuckDBPyConnection):
            # DuckDB
            query = "SELECT MAX(timestamp) FROM ohlcv WHERE symbol = ? AND timeframe = ?"
            res = conn.execute(query, [symbol, timeframe]).fetchone()
            if res and res[0]:
                return pd.Timestamp(res[0])
            return None
        else:
            # Postgres
            from sqlalchemy import func, select
            stmt = select(func.max(ohlcv_table.c.timestamp)).where(
                ohlcv_table.c.symbol == symbol,
                ohlcv_table.c.timeframe == timeframe
            )
            res = conn.scalar(stmt)
            if res:
                return pd.Timestamp(res)
            return None
    except Exception as e:
        logger.error(f"Failed to get latest timestamp for {symbol}/{timeframe}: {e}")
        return None


def count_rows(conn: DBConnection, symbol: str | None = None) -> int:
    """Count rows in ohlcv table."""
    try:
        if isinstance(conn, duckdb.DuckDBPyConnection):
            if symbol:
                res = conn.execute("SELECT COUNT(*) FROM ohlcv WHERE symbol = ?", [symbol]).fetchone()
            else:
                res = conn.execute("SELECT COUNT(*) FROM ohlcv").fetchone()
            return res[0] if res else 0
        else:
            # Postgres
            from sqlalchemy import func, select
            if symbol:
                stmt = select(func.count()).where(ohlcv_table.c.symbol == symbol)
            else:
                stmt = select(func.count()).select_from(ohlcv_table)
            
            return conn.scalar(stmt) or 0
            
    except Exception as e:
        logger.error(f"Failed to count rows: {e}")
        return 0
