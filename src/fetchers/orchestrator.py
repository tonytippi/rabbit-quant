"""Concurrent data ingestion orchestrator.

Coordinates async fetching of stocks and crypto across all configured
symbols and timeframes, storing results via DuckDB upsert.
"""

import asyncio
import time
from dataclasses import dataclass, field

from loguru import logger

from src.config import AssetConfig, TimeframeConfig
from src.data_loader import DBConnection, get_latest_timestamp, upsert_ohlcv
from src.fetchers.crypto_fetcher import fetch_crypto_ohlcv
from src.fetchers.stock_fetcher import fetch_stock_ohlcv

# Max concurrent fetch tasks to avoid overwhelming APIs
MAX_CONCURRENT_TASKS = 10


@dataclass
class FetchResult:
    """Summary of a data fetch run."""

    total: int = 0
    success: int = 0
    failed: int = 0
    rows_upserted: int = 0
    elapsed_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


async def _fetch_stock_task(
    symbol: str,
    timeframe: str,
    yf_interval: str,
    conn: DBConnection,
    result: FetchResult,
    semaphore: asyncio.Semaphore,
    latest_timestamp=None,
) -> None:
    """Async wrapper for stock fetching (yfinance is sync, run in executor)."""
    async with semaphore:
        try:
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(None, fetch_stock_ohlcv, symbol, timeframe, yf_interval, latest_timestamp)
            if df is not None and not df.empty:
                rows = upsert_ohlcv(conn, df)
                result.rows_upserted += rows
                result.success += 1
            else:
                result.failed += 1
                result.errors.append(f"{symbol}/{timeframe}: no data returned")
        except Exception as e:
            result.failed += 1
            result.errors.append(f"{symbol}/{timeframe}: {e}")
            logger.error(f"Stock fetch failed {symbol}/{timeframe}: {e}")


async def _fetch_crypto_task(
    symbol: str,
    timeframe: str,
    ccxt_interval: str,
    exchange_id: str,
    conn: DBConnection,
    result: FetchResult,
    semaphore: asyncio.Semaphore,
    latest_timestamp=None,
) -> None:
    """Async task for crypto fetching."""
    async with semaphore:
        try:
            df = await fetch_crypto_ohlcv(symbol, timeframe, ccxt_interval, exchange_id, latest_timestamp)
            if df is not None and not df.empty:
                rows = upsert_ohlcv(conn, df)
                result.rows_upserted += rows
                result.success += 1
            else:
                result.failed += 1
                result.errors.append(f"{symbol}/{timeframe}: no data returned")
        except Exception as e:
            result.failed += 1
            result.errors.append(f"{symbol}/{timeframe}: {e}")
            logger.error(f"Crypto fetch failed {symbol}/{timeframe}: {e}")


async def fetch_all_assets(
    conn: DBConnection,
    assets: AssetConfig,
    timeframes: TimeframeConfig,
) -> FetchResult:
    """Fetch OHLCV data for all configured assets concurrently.

    Args:
        conn: Active DuckDB connection.
        assets: Asset configuration with stock and crypto symbols.
        timeframes: Timeframe configuration with mappings.

    Returns:
        FetchResult with success/failure counts and timing.
    """
    result = FetchResult()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    tasks = []

    start_time = time.monotonic()

    # Build stock fetch tasks
    for symbol in assets.stock_symbols:
        for tf in timeframes.default_timeframes:
            latest_ts = get_latest_timestamp(conn, symbol, tf)
            yf_interval = timeframes.yfinance_mapping.get(tf, tf)
            tasks.append(_fetch_stock_task(symbol, tf, yf_interval, conn, result, semaphore, latest_ts))
            result.total += 1

    # Build crypto fetch tasks
    for symbol in assets.crypto_symbols:
        for tf in timeframes.default_timeframes:
            latest_ts = get_latest_timestamp(conn, symbol, tf)
            ccxt_interval = timeframes.ccxt_mapping.get(tf, tf)
            tasks.append(_fetch_crypto_task(symbol, tf, ccxt_interval, assets.crypto_exchange, conn, result, semaphore, latest_ts))
            result.total += 1

    logger.info(f"Starting fetch for {result.total} symbol/timeframe combinations...")

    # Execute all tasks concurrently
    await asyncio.gather(*tasks, return_exceptions=True)

    result.elapsed_seconds = time.monotonic() - start_time

    # Log summary
    logger.info(
        f"Fetch complete: {result.success}/{result.total} succeeded, "
        f"{result.failed} failed, {result.rows_upserted} rows upserted "
        f"in {result.elapsed_seconds:.1f}s"
    )
    if result.errors:
        for err in result.errors[:10]:  # Show first 10 errors
            logger.warning(f"  - {err}")
        if len(result.errors) > 10:
            logger.warning(f"  ... and {len(result.errors) - 10} more errors")

    return result
