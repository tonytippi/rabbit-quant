"""Crypto data fetcher using ccxt.

Fetches OHLCV data for crypto trading pairs and returns standardized DataFrames
ready for DuckDB upsert.
"""

import asyncio

import ccxt.async_support as ccxt_async
import pandas as pd
from loguru import logger

# Max candles per ccxt request (exchange-dependent, 1000 is safe default)
MAX_CANDLES_PER_REQUEST = 1000

# How many candles to fetch per timeframe
TIMEFRAME_CANDLE_LIMIT = {
    "1m": 10000,
    "5m": 5000,
    "15m": 176000,
    "1h": 44000, # 5 years of 1h candles
    "4h": 11000,
    "1d": 2000,
}

# Max retries for rate-limited requests
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 2.0


async def fetch_crypto_ohlcv(
    symbol: str,
    timeframe: str,
    ccxt_interval: str,
    exchange_id: str = "binance",
    latest_timestamp=None,
) -> pd.DataFrame | None:
    """Fetch OHLCV data for a single crypto pair and timeframe.

    Args:
        symbol: Crypto pair (e.g., "BTC/USDT").
        timeframe: Internal timeframe name (e.g., "1h").
        ccxt_interval: ccxt interval string from timeframe mapping.
        exchange_id: Exchange identifier (default: "binance").
        latest_timestamp: Optional pd.Timestamp of the most recent candle.

    Returns:
        Standardized DataFrame with OHLCV columns, or None on failure.
    """
    exchange = None
    try:
        exchange_class = getattr(ccxt_async, exchange_id, None)
        if exchange_class is None:
            logger.error(f"Exchange {exchange_id} not supported by ccxt")
            return None

        exchange = exchange_class({"enableRateLimit": True})

        if latest_timestamp is not None:
            since = int(latest_timestamp.timestamp() * 1000)
            candle_limit = 1000000  # Large limit to fetch all missing candles up to now
        else:
            candle_limit = TIMEFRAME_CANDLE_LIMIT.get(timeframe, 1000)

            # Calculate start time (since) to fetch historical data
            # Mapping timeframe to milliseconds
            tf_ms = {
                "1m": 60 * 1000,
                "5m": 5 * 60 * 1000,
                "15m": 15 * 60 * 1000,
                "1h": 60 * 60 * 1000,
                "4h": 4 * 60 * 60 * 1000,
                "1d": 24 * 60 * 60 * 1000,
            }
            ms_per_candle = tf_ms.get(timeframe, 60 * 1000)
            import time
            since = int(time.time() * 1000) - (candle_limit * ms_per_candle)

        all_ohlcv = await _fetch_with_retry(exchange, symbol, ccxt_interval, candle_limit, since=since)

        if not all_ohlcv:
            logger.warning(f"No data returned for {symbol}/{timeframe}")
            return None

        # Convert to DataFrame
        df = pd.DataFrame(all_ohlcv, columns=["timestamp", "open_price", "high_price", "low_price", "close_price", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df["symbol"] = symbol
        df["timeframe"] = timeframe
        df = df.dropna()

        logger.debug(f"Fetched {len(df)} rows for {symbol}/{timeframe}")
        return df

    except Exception as e:
        logger.error(f"Failed to fetch {symbol}/{timeframe}: {e}")
        return None
    finally:
        if exchange:
            await exchange.close()


async def _fetch_with_retry(exchange, symbol: str, interval: str, limit: int, since: int | None = None) -> list:
    """Fetch OHLCV with pagination and exponential backoff on rate limits."""
    all_candles = []
    remaining = limit

    for attempt in range(MAX_RETRIES):
        try:
            while remaining > 0:
                batch_size = min(remaining, MAX_CANDLES_PER_REQUEST)
                candles = await exchange.fetch_ohlcv(symbol, interval, since=since, limit=batch_size)

                if not candles:
                    break

                all_candles.extend(candles)
                remaining -= len(candles)

                # Set 'since' to last candle timestamp + 1ms for pagination
                since = candles[-1][0] + 1

                if len(candles) < batch_size:
                    break  # No more data available

            return all_candles

        except ccxt_async.RateLimitExceeded:
            wait = BASE_BACKOFF_SECONDS * (2 ** attempt)
            logger.warning(f"Rate limited for {symbol}/{interval}, retrying in {wait}s...")
            await asyncio.sleep(wait)
        except ccxt_async.NetworkError as e:
            wait = BASE_BACKOFF_SECONDS * (2 ** attempt)
            logger.warning(f"Network error for {symbol}/{interval}: {e}, retrying in {wait}s...")
            await asyncio.sleep(wait)

    logger.error(f"All retries exhausted for {symbol}/{interval}")
    return all_candles  # Return whatever we got
