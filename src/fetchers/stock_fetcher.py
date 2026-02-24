"""Stock data fetcher using yfinance.

Fetches OHLCV data for stock/ETF symbols and returns standardized DataFrames
ready for DuckDB upsert.
"""

import pandas as pd
import yfinance as yf
from loguru import logger

# yfinance period mapping: how far back to fetch for each timeframe
TIMEFRAME_PERIOD_MAP = {
    "1m": "7d",    # yfinance limits 1m to 7 days
    "5m": "60d",   # yfinance limits 5m to 60 days
    "15m": "60d",
    "1h": "730d",
    "4h": "730d",  # Fetch 1h data, resample to 4h
    "1d": "max",
}


def fetch_stock_ohlcv(symbol: str, timeframe: str, yf_interval: str, latest_timestamp=None) -> pd.DataFrame | None:
    """Fetch OHLCV data for a single stock symbol and timeframe.

    Args:
        symbol: Stock ticker (e.g., "AAPL").
        timeframe: Internal timeframe name (e.g., "1h", "4h").
        yf_interval: yfinance interval string from timeframe mapping.
        latest_timestamp: Optional pd.Timestamp of the most recent candle.

    Returns:
        Standardized DataFrame with OHLCV_COLUMNS, or None on failure.
    """
    try:
        ticker = yf.Ticker(symbol)
        if latest_timestamp is not None:
            start_date = latest_timestamp.strftime("%Y-%m-%d")
            df = ticker.history(start=start_date, interval=yf_interval)
        else:
            period = TIMEFRAME_PERIOD_MAP.get(timeframe, "730d")
            df = ticker.history(period=period, interval=yf_interval)

        if df is None or df.empty:
            logger.warning(f"No data returned for {symbol}/{timeframe}")
            return None

        # Standardize column names to match OHLCV schema
        df = df.reset_index()
        rename_map = {
            "Date": "timestamp",
            "Datetime": "timestamp",
            "Open": "open_price",
            "High": "high_price",
            "Low": "low_price",
            "Close": "close_price",
            "Volume": "volume",
        }
        df = df.rename(columns=rename_map)

        # Keep only needed columns
        needed = ["timestamp", "open_price", "high_price", "low_price", "close_price", "volume"]
        available = [c for c in needed if c in df.columns]
        if len(available) < len(needed):
            logger.error(f"Missing columns for {symbol}/{timeframe}: {set(needed) - set(available)}")
            return None
        df = df[needed].copy()

        # Resample 1h -> 4h if needed
        if timeframe == "4h" and yf_interval == "1h":
            df = _resample_to_4h(df)
            if df is None or df.empty:
                return None

        # Remove timezone info from timestamp for DuckDB compatibility
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)

        # Add symbol and timeframe columns
        df["symbol"] = symbol
        df["timeframe"] = timeframe

        # Drop rows with NaN
        df = df.dropna()

        logger.debug(f"Fetched {len(df)} rows for {symbol}/{timeframe}")
        return df

    except Exception as e:
        logger.error(f"Failed to fetch {symbol}/{timeframe}: {e}")
        return None


def _resample_to_4h(df: pd.DataFrame) -> pd.DataFrame | None:
    """Resample 1h OHLCV data to 4h bars."""
    try:
        if df.empty:
            return df
        df = df.set_index("timestamp")
        resampled = df.resample("4h").agg({
            "open_price": "first",
            "high_price": "max",
            "low_price": "min",
            "close_price": "last",
            "volume": "sum",
        })
        resampled = resampled.dropna().reset_index()
        return resampled
    except Exception as e:
        logger.error(f"Failed to resample to 4h: {e}")
        return None
