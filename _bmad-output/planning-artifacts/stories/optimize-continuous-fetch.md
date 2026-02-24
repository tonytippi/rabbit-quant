# User Story: Optimize Fetch Command for Continuous Data Ingestion

## Description
**As a** user running a quantitative trading workstation,
**I want** the `fetch` command to download only new OHLCV data starting from the most recent timestamp available in the database,
**So that** I can save on API rate limits, drastically reduce execution time, and avoid redownloading years of historical data on every run.

## Context
Currently, the fetch process in `src/fetchers/crypto_fetcher.py` and `src/fetchers/stock_fetcher.py` always fetches a fixed historical range (e.g., up to 730 days for stocks or a calculated number of candles for crypto). While `upsert_ohlcv` handles the duplicates gracefully, the network overhead and API wait times are substantial.

## Acceptance Criteria

1. **Database Query for Latest Timestamp:**
   - Implement a new function in `src/data_loader.py` (e.g., `get_latest_timestamp(conn, symbol, timeframe)`) that queries the maximum timestamp from the `ohlcv` table for a given symbol and timeframe.

2. **Orchestrator Integration:**
   - Update `src/fetchers/orchestrator.py` to retrieve this `latest_timestamp` before starting the fetch tasks.
   - Pass the `latest_timestamp` to `_fetch_stock_task` and `_fetch_crypto_task`.

3. **Crypto Fetcher (`ccxt`) Update:**
   - In `src/fetchers/crypto_fetcher.py`, if a `latest_timestamp` is provided, calculate the `since` parameter as `int(latest_timestamp.timestamp() * 1000)`.
   - Ensure the default logic (fetching based on `TIMEFRAME_CANDLE_LIMIT`) is preserved only when no existing data is found.

4. **Stock Fetcher (`yfinance`) Update:**
   - In `src/fetchers/stock_fetcher.py`, if a `latest_timestamp` is provided, use `ticker.history(start=start_date_string, interval=yf_interval)` instead of `period=period`.
   - Ensure the default logic (using `TIMEFRAME_PERIOD_MAP`) is preserved only when no existing data is found.

5. **Edge Cases & Resilience:**
   - Ensure that fetching the most recent candle (which might be incomplete and updated during the fetch) overlaps correctly and is resolved via the existing `upsert_ohlcv` logic.
   - Fall back to the full historical download if the query for the latest timestamp fails or returns `None`.

## Technical Notes
- The database abstraction supports both DuckDB and PostgreSQL. The `get_latest_timestamp` function must handle both connections appropriately.
- For `yfinance`, the `start` parameter typically expects a `YYYY-MM-DD` string. Adjust the `latest_timestamp` safely.
