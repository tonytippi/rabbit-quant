---
stepsCompleted: [1, 2, 3, 4]
lastStep: 4
status: 'complete'
completedAt: '2026-02-13'
inputDocuments:
  - prd.md
  - _bmad-output/planning-artifacts/architecture.md
---

# Epic 1: Data Acquisition & Storage

Users can ingest and store multi-asset OHLCV data from stock and crypto markets, ready for analysis.

## Stories

### Story 1.1: Project Scaffold & Configuration System

As a **developer**,
I want a fully initialized project with config loading from `.env` and TOML files,
So that all modules have a typed, validated configuration foundation to build upon.

**Acceptance Criteria:**

**Given** a fresh clone of the repository
**When** I run `uv sync`
**Then** all dependencies install and a virtual environment is created
**And** `pyproject.toml` contains all project metadata, ruff, and pytest config

**Given** a `.env` file with API keys and a `config/assets.toml` with asset lists
**When** I run `python main.py`
**Then** Pydantic Settings loads and validates all config values
**And** invalid config raises a clear validation error at startup

**Given** the project directory
**When** I inspect the structure
**Then** all directories from Architecture doc exist (`src/`, `src/signals/`, `src/backtest/`, `src/dashboard/`, `config/`, `data/`, `tests/`, `logs/`)
**And** `main.py` provides CLI skeleton with `fetch`, `backtest`, `dashboard` subcommands
**And** loguru is configured with file rotation to `logs/rabbit.log`

### Story 1.2: DuckDB Schema & Upsert Operations

As a **quant researcher**,
I want OHLCV data stored in a local DuckDB database with upsert capability,
So that I can incrementally update data without duplicating history.

**Acceptance Criteria:**

**Given** DuckDB is configured in `data/rabbit.duckdb`
**When** the data_loader module initializes
**Then** an `ohlcv` table is created with columns: `symbol`, `timeframe`, `timestamp`, `open_price`, `high_price`, `low_price`, `close_price`, `volume`
**And** a unique constraint exists on (`symbol`, `timeframe`, `timestamp`)

**Given** a pandas DataFrame of OHLCV candles
**When** I call the upsert function with overlapping timestamps
**Then** existing rows are updated and new rows are inserted
**And** no duplicate records exist after the operation

**Given** an empty or missing DuckDB file
**When** the module initializes
**Then** the database and table are created automatically

### Story 1.3: Stock Data Fetching via yfinance

As a **quant researcher**,
I want to fetch OHLCV data for stocks and ETFs from yfinance,
So that I can analyze equity markets locally.

**Acceptance Criteria:**

**Given** an asset list in `config/assets.toml` with stock symbols (e.g., AAPL, NVDA)
**When** I run `python main.py fetch`
**Then** OHLCV data is fetched for all configured stock symbols
**And** data is stored in DuckDB via the upsert function from Story 1.2

**Given** a symbol with 6 configured timeframes (1m, 5m, 15m, 1h, 4h, 1d)
**When** data is fetched
**Then** all 6 timeframes are retrieved and stored separately

**Given** yfinance returns an API error or rate limit
**When** the fetch is attempted
**Then** the error is logged via loguru without crashing
**And** the pipeline continues to the next symbol

### Story 1.4: Crypto Data Fetching via ccxt

As a **quant researcher**,
I want to fetch OHLCV data for cryptocurrencies from exchanges via ccxt,
So that I can analyze crypto markets alongside stocks.

**Acceptance Criteria:**

**Given** an asset list in `config/assets.toml` with crypto pairs (e.g., BTC/USDT, ETH/USDT)
**When** I run `python main.py fetch`
**Then** OHLCV data is fetched for all configured crypto pairs
**And** data is stored in DuckDB via the upsert function

**Given** a crypto pair with 6 configured timeframes
**When** data is fetched
**Then** all 6 timeframes are retrieved and stored separately

**Given** an exchange API error or rate limit
**When** the fetch is attempted
**Then** retry with exponential backoff is executed
**And** persistent failures are logged without crashing the pipeline

### Story 1.5: Concurrent Multi-Asset Ingestion

As a **quant researcher**,
I want data ingestion for 50+ assets to run concurrently,
So that updates complete within 60 seconds.

**Acceptance Criteria:**

**Given** 50+ assets configured (mixed stocks + crypto)
**When** I run `python main.py fetch`
**Then** all assets are fetched using asyncio concurrency
**And** total ingestion completes in under 60 seconds

**Given** some assets fail during concurrent fetch
**When** the pipeline runs
**Then** successful assets are stored normally
**And** failed assets are logged with error details
**And** a summary is printed showing success/failure counts

**Given** concurrent fetching is running
**When** I check system resource usage
**Then** RAM stays within reasonable bounds (no memory leak from concurrent connections)

### Story 1.6: PostgreSQL Migration

As a **devops engineer**,
I want to migrate the data storage layer from DuckDB to PostgreSQL,
So that multiple processes (Scheduler, Dashboard, Backtester) can read/write concurrently without file locking issues.

**Acceptance Criteria:**

**Given** a valid PostgreSQL connection string in `.env` (e.g., `DATABASE_URL=postgresql://user:pass@localhost:5432/rabbit`)
**When** the application starts
**Then** `src/data_loader.py` connects to Postgres instead of DuckDB (using `psycopg2` or `asyncpg`)

**Given** the Postgres database is empty
**When** the schema initializes
**Then** the `ohlcv` table is created with `(symbol, timeframe, timestamp)` as the Primary Key or Unique Index

**Given** new market data fetching occurs
**When** `upsert_ohlcv` is called
**Then** it uses PostgreSQL's `INSERT ... ON CONFLICT DO UPDATE` syntax to handle duplicates correctly
