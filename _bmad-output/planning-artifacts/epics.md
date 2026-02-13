---
stepsCompleted: [1, 2, 3, 4]
lastStep: 4
status: 'complete'
completedAt: '2026-02-13'
inputDocuments:
  - prd.md
  - _bmad-output/planning-artifacts/architecture.md
---

# rabbit-quant - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for rabbit-quant, decomposing the requirements from the PRD and Architecture into implementable stories.

## Requirements Inventory

### Functional Requirements

FR-01: System must support fetching OHLCV data for Stocks and Crypto from public market data APIs.
FR-02: System must handle at least 50 concurrent assets.
FR-03: System must support 6 distinct timeframes: 1m, 5m, 15m, 1h, 4h, 1d.
FR-04: Data ingestion for multiple assets must run concurrently to meet the 60-second throughput target.
FR-05: Database must enable "upsert" functionality to append new candles without duplicating history.
FR-06: System must calculate the Dominant Cycle Period using FFT (Fast Fourier Transform).
FR-07: System must apply a Low-Pass Filter to smooth out high-frequency noise before cycle detection.
FR-08: System must project the dominant cycle phase forward by at least 20 bars.
FR-09: System must calculate the Hurst Exponent using the R/S (Rescaled Range) method.
FR-10: Hurst calculation for 10,000 candles must complete in under 0.05 seconds.
FR-11: System must allow users to define "Long" and "Short" logic based on Cycle Phase and Hurst Value.
FR-12: Backtesting engine must support parameter sweeping (e.g., testing Hurst threshold from 0.5 to 0.9).
FR-13: System must calculate performance metrics: Total Return, Sharpe Ratio, Max Drawdown, Win Rate.
FR-14: System must export trade logs to CSV for audit.
FR-15: Dashboard must display an interactive Candlestick chart with zoom, pan, and crosshair.
FR-16: Chart must support overlaying the "Predicted Sine Wave" on top of price action.
FR-17: Dashboard must include a "Scanner Table" sortable by Hurst Exponent.
FR-18: Dashboard must visually indicate "Buy/Sell" signals (e.g., Green/Red markers).

### NonFunctional Requirements

NFR-01: Dashboard query response time must be < 50ms for cached data.
NFR-02: Backtesting 5 years of 1-minute data for 1 asset must complete in < 5 seconds.
NFR-03: RAM usage must never exceed 40GB (leaving 24GB for OS).
NFR-04: Background scheduler must automatically restart on failure.
NFR-05: All API failures must be logged to system.log without crashing the UI.
NFR-06: No user data or trading strategies shall be transmitted to any external server.
NFR-07: API Keys must be stored in a local .env file and never hardcoded.
NFR-08: Code must adhere to PEP-8 standards.
NFR-09: All complex math functions (FFT, Hurst) must have Docstrings.
NFR-10: Core mathematical modules must have >90% Unit Test coverage.

### Additional Requirements

**From Architecture:**
- Starter template: `uv init` + custom structure (no external template)
- Concurrency model: asyncio (I/O) + Numba @njit(parallel=True) (math) + ProcessPoolExecutor (batch)
- DuckDB schema: single `ohlcv` table with symbol/timeframe columns, upsert semantics
- Config: Pydantic Settings (.env) + TOML files (assets, strategy, timeframes)
- Logging: loguru with file rotation
- Scheduler: APScheduler for background data refresh
- Caching: in-memory DataFrame cache with TTL in dashboard layer
- Module boundary rules: each module has strict ownership (see Architecture doc)
- Data flow contracts: DataFrame → numpy ndarray → dict of arrays at module boundaries
- Numba compatibility: @njit functions must use numpy-only internals, wrapper functions handle conversions
- Error handling: return None/empty on errors, never raise across module boundaries
- Testing: pytest with fixtures, math tests against known analytical results
- Entry point: `main.py` CLI with commands: fetch, backtest, dashboard

### FR Coverage Map

| FR | Epic | Description |
|----|------|-------------|
| FR-01 | Epic 1 | OHLCV fetching for Stocks & Crypto |
| FR-02 | Epic 1 | 50+ concurrent assets |
| FR-03 | Epic 1 | 6 timeframes support |
| FR-04 | Epic 1 | Concurrent data ingestion (<60s) |
| FR-05 | Epic 1 | DuckDB upsert (no duplicates) |
| FR-06 | Epic 2 | FFT Dominant Cycle Period |
| FR-07 | Epic 2 | Low-Pass Filter for noise smoothing |
| FR-08 | Epic 2 | Forward cycle projection (20+ bars) |
| FR-09 | Epic 2 | Hurst Exponent (R/S method) |
| FR-10 | Epic 2 | Hurst performance (<0.05s for 10K candles) |
| FR-11 | Epic 3 | Configurable Long/Short signal logic |
| FR-12 | Epic 3 | Parameter sweep engine |
| FR-13 | Epic 3 | Performance metrics (Sharpe/DD/WR) |
| FR-14 | Epic 3 | CSV trade log export |
| FR-15 | Epic 4 | Interactive Candlestick chart |
| FR-16 | Epic 4 | Sine Wave overlay |
| FR-17 | Epic 4 | Scanner Table sorted by Hurst |
| FR-18 | Epic 4 | Buy/Sell signal markers |

## Epic List

### Epic 1: Data Acquisition & Storage
Users can ingest and store multi-asset OHLCV data from stock and crypto markets, ready for analysis.
**FRs covered:** FR-01, FR-02, FR-03, FR-04, FR-05

### Epic 2: Quantitative Signal Generation
Users can detect dominant market cycles and measure trend persistence (Hurst) to identify high-probability turning points.
**FRs covered:** FR-06, FR-07, FR-08, FR-09, FR-10

### Epic 3: Strategy Backtesting & Optimization
Users can validate trading hypotheses by backtesting cycle+Hurst strategies with parameter optimization and detailed performance reports.
**FRs covered:** FR-11, FR-12, FR-13, FR-14

### Epic 4: Interactive Trading Dashboard
Users can visually monitor markets in real-time, scan for opportunities by Hurst ranking, and see buy/sell signals on interactive charts with cycle overlays.
**FRs covered:** FR-15, FR-16, FR-17, FR-18

---

## Epic 1: Data Acquisition & Storage

Users can ingest and store multi-asset OHLCV data from stock and crypto markets, ready for analysis.

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

---

## Epic 2: Quantitative Signal Generation

Users can detect dominant market cycles and measure trend persistence (Hurst) to identify high-probability turning points.

### Story 2.1: FFT Dominant Cycle Detection

As a **quant researcher**,
I want to detect the dominant cycle period in price data using FFT,
So that I can identify recurring market rhythms for timing entries/exits.

**Acceptance Criteria:**

**Given** a numpy array of close prices (minimum 256 data points)
**When** I call the cycle detection function
**Then** it returns the dominant cycle period (in bars) using Fast Fourier Transform
**And** the function has a docstring explaining the FFT methodology

**Given** a synthetic sinusoidal input with known period (e.g., 50 bars)
**When** FFT analysis runs
**Then** the detected dominant period matches the known period within 5% tolerance

**Given** close price data from DuckDB
**When** the wrapper function is called with a DataFrame
**Then** it converts to numpy, calls the @njit function, and returns the result
**And** the @njit function uses only numpy operations (no pandas, no Python objects)

### Story 2.2: Low-Pass Filter for Noise Smoothing

As a **quant researcher**,
I want high-frequency noise removed from price data before cycle detection,
So that the dominant cycle signal is cleaner and more reliable.

**Acceptance Criteria:**

**Given** a numpy array of close prices with mixed frequency components
**When** I apply the low-pass filter
**Then** high-frequency noise is attenuated while preserving the dominant cycle
**And** the cutoff frequency is configurable via `config/strategy.toml`

**Given** a synthetic signal with a known dominant cycle plus random noise
**When** the filter is applied before FFT
**Then** cycle detection accuracy improves compared to unfiltered data

**Given** the filter function
**When** I inspect its implementation
**Then** it has a docstring explaining the filtering approach and parameters

### Story 2.3: Forward Cycle Phase Projection

As a **quant researcher**,
I want the detected cycle projected forward by at least 20 bars,
So that I can anticipate upcoming cycle tops and bottoms.

**Acceptance Criteria:**

**Given** a detected dominant cycle period and current phase
**When** I call the projection function
**Then** it returns a phase array extending at least 20 bars into the future
**And** the projection is represented as a sine wave with the detected period

**Given** historical data where the cycle was detected
**When** the forward projection is generated
**Then** the projection smoothly continues from the last known phase
**And** the output includes both the historical fit and the forward projection

**Given** the projection output
**When** consumed by downstream modules (backtest or dashboard)
**Then** it is returned as a dict containing `dominant_period`, `phase_array`, and `projection_array`

### Story 2.4: Numba-Optimized Hurst Exponent

As a **quant researcher**,
I want to calculate the Hurst Exponent using the R/S method with Numba JIT,
So that I can measure trend persistence at high speed.

**Acceptance Criteria:**

**Given** a numpy array of 10,000 close prices
**When** I call the Hurst calculation function
**Then** it completes in under 0.05 seconds
**And** the function uses `@numba.njit` with numpy-only internals

**Given** white noise (random walk) input data
**When** Hurst is calculated
**Then** the result is approximately 0.5 (within 0.1 tolerance)

**Given** a strongly trending synthetic series
**When** Hurst is calculated
**Then** the result is approximately 0.7+ indicating persistent trend

**Given** the Hurst function
**When** I inspect it
**Then** it has a docstring explaining the R/S (Rescaled Range) method
**And** a wrapper function accepts DataFrame input and returns a float

### Story 2.5: Combined Signal Generation

As a **quant researcher**,
I want cycle phase and Hurst value combined into actionable trading signals,
So that I can identify high-probability turning points with trend confirmation.

**Acceptance Criteria:**

**Given** a symbol with OHLCV data in DuckDB
**When** I run signal generation via `signals/filters.py`
**Then** it reads data, computes cycle (Stories 2.1-2.3) and Hurst (Story 2.4), and returns a combined signal dict

**Given** the combined signal output
**When** I inspect its structure
**Then** it contains: `symbol`, `timeframe`, `dominant_period`, `current_phase`, `hurst_value`, `phase_array`, `projection_array`, `signal` (long/short/neutral)

**Given** configurable thresholds in `config/strategy.toml` (e.g., `hurst_threshold = 0.6`)
**When** signals are generated
**Then** the signal logic uses these thresholds to determine long/short/neutral

**Given** the signal generation is run for multiple assets
**When** using ProcessPoolExecutor for batch compute
**Then** all assets are processed in parallel across available CPU cores

---

## Epic 3: Strategy Backtesting & Optimization

Users can validate trading hypotheses by backtesting cycle+Hurst strategies with parameter optimization and detailed performance reports.

### Story 3.1: Configurable Long/Short Signal Logic

As a **quant researcher**,
I want to define long and short entry rules based on cycle phase and Hurst value,
So that I can test different trading hypotheses.

**Acceptance Criteria:**

**Given** `config/strategy.toml` with `hurst_threshold`, `cycle_phase_long`, `cycle_phase_short` parameters
**When** the backtest engine reads the config
**Then** it builds VectorBT entry/exit signals based on these rules

**Given** combined signal output from Epic 2 (signal dict with phase + Hurst)
**When** long logic is evaluated
**Then** a long entry triggers when cycle phase is at bottom AND Hurst > threshold

**Given** the same signal output
**When** short logic is evaluated
**Then** a short entry triggers when cycle phase is at top AND Hurst > threshold

### Story 3.2: Parameter Sweep Engine

As a **quant researcher**,
I want to sweep strategy parameters across a multi-dimensional grid,
So that I can find optimal settings for each asset/timeframe.

**Acceptance Criteria:**

**Given** a parameter grid defined in `config/strategy.toml` covering:
- `hurst_threshold`: e.g., [0.5, 0.55, 0.6, ..., 0.9]
- `cycle_phase_long`: e.g., phase angles for bottom detection
- `cycle_phase_short`: e.g., phase angles for top detection
**When** I run `python main.py backtest`
**Then** VectorBT executes the strategy for every combination across all parameter dimensions

**Given** a 5-year 1-minute dataset for 1 asset
**When** the parameter sweep runs
**Then** it completes in under 5 seconds using vectorized operations

**Given** a large parameter grid
**When** the sweep runs
**Then** RAM usage stays under 40GB
**And** results are stored in a DataFrame indexed by parameter values

### Story 3.3: Performance Metrics & Heatmap

As a **quant researcher**,
I want Sharpe Ratio, Max Drawdown, Win Rate, and Total Return calculated for each parameter set,
So that I can evaluate which settings produce the best risk-adjusted returns.

**Acceptance Criteria:**

**Given** a completed backtest run (single or sweep)
**When** the analyzer processes results
**Then** it calculates: Total Return, Sharpe Ratio, Max Drawdown, Win Rate

**Given** a parameter sweep result
**When** metrics are computed
**Then** a heatmap DataFrame is generated showing Sharpe Ratio across parameter combinations
**And** the heatmap can be displayed or exported

**Given** the metrics output
**When** I inspect the values
**Then** Sharpe, Drawdown, and WinRate match manual calculation on the same data

### Story 3.4: Trade Log CSV Export

As a **quant researcher**,
I want to export a detailed trade log to CSV,
So that I can audit individual trades and verify strategy behavior.

**Acceptance Criteria:**

**Given** a completed backtest run
**When** I request CSV export
**Then** a CSV file is generated with columns: `entry_time`, `exit_time`, `symbol`, `direction`, `entry_price`, `exit_price`, `pnl`, `return_pct`

**Given** the exported CSV
**When** I compare it to the backtest metrics
**Then** the sum of individual trade PnL matches Total Return
**And** Win Rate matches the ratio of positive PnL trades

**Given** the `main.py backtest` command
**When** it completes
**Then** the CSV is saved to a configurable output path
**And** the path is logged to console

### Story 3.5: Auto-Discovery & Config Recommendation

As a **quant researcher**,
I want the system to automatically identify the best performing parameter combination and recommend updating my config,
So that I don't have to manually interpret heatmaps to find optimal settings.

**Acceptance Criteria:**

**Given** a completed parameter sweep with metrics (from Stories 3.2 + 3.3)
**When** the analyzer ranks all parameter combinations by Sharpe Ratio
**Then** it identifies the top 3 performing combinations

**Given** the top 3 results
**When** displayed to the user
**Then** each shows: `hurst_threshold`, `cycle_phase_long`, `cycle_phase_short`, Sharpe, Max Drawdown, Win Rate
**And** the #1 result is highlighted as the recommended setting

**Given** the user confirms the recommended parameters
**When** they accept
**Then** `config/strategy.toml` is updated with the new values
**And** the previous values are logged for rollback reference

**Given** the user rejects all recommendations
**When** they decline
**Then** config remains unchanged and the full results are saved to CSV for manual review

---

## Epic 4: Interactive Trading Dashboard

Users can visually monitor markets in real-time, scan for opportunities by Hurst ranking, and see buy/sell signals on interactive charts with cycle overlays.

### Story 4.1: Dashboard Layout & Scanner Table

As a **discretionary trader**,
I want a dashboard with a scanner table showing all assets sorted by Hurst Exponent,
So that I can quickly identify which assets have the strongest trends.

**Acceptance Criteria:**

**Given** signal data exists for 50+ assets (from Epic 2)
**When** I run `python main.py dashboard` (launches Streamlit)
**Then** a scanner table displays all assets with columns: `Symbol`, `Timeframe`, `Hurst`, `Dominant Cycle`, `Signal` (Long/Short/Neutral)

**Given** the scanner table is displayed
**When** I click a column header (e.g., Hurst)
**Then** the table sorts by that column in ascending/descending order

**Given** the dashboard is running
**When** data is loaded from DuckDB + signal cache
**Then** query response time is < 50ms for cached data
**And** an in-memory DataFrame cache with TTL is used

**Given** a new user launches the dashboard with no data
**When** the page loads
**Then** a clear message indicates no data available and suggests running `python main.py fetch`

### Story 4.2: Interactive Candlestick Chart

As a **discretionary trader**,
I want an interactive candlestick chart with zoom, pan, and crosshair,
So that I can visually analyze price action for any asset.

**Acceptance Criteria:**

**Given** I click a symbol row in the scanner table
**When** the chart loads
**Then** a Plotly candlestick chart renders with OHLCV data for that symbol/timeframe
**And** the chart supports zoom, pan, and crosshair interactions

**Given** the chart is displayed
**When** I hover over a candle
**Then** a tooltip shows: Date, Open, High, Low, Close, Volume

**Given** the chart is loading
**When** data is fetched from cache
**Then** chart renders in under 200ms for cached tickers

### Story 4.3: Sine Wave Overlay & Cycle Visualization

As a **discretionary trader**,
I want the predicted sine wave overlaid on the candlestick chart,
So that I can see where price sits relative to the dominant cycle.

**Acceptance Criteria:**

**Given** a candlestick chart is displayed for a symbol
**When** cycle data exists (from Epic 2 signal generation)
**Then** a sine wave is overlaid on the price chart using the detected dominant period and phase

**Given** the sine wave overlay
**When** I inspect it visually
**Then** the historical portion fits the recent price action
**And** the forward projection (20+ bars) extends beyond the last candle as a dashed/lighter line

**Given** cycle detection returned no valid cycle (insufficient data or flat market)
**When** the chart renders
**Then** no sine wave is shown and a note indicates "No dominant cycle detected"

### Story 4.4: Buy/Sell Signal Markers & Auto-Refresh

As a **discretionary trader**,
I want buy/sell signals visually marked on the chart and the dashboard to auto-refresh,
So that I can spot opportunities in real-time without manual reloading.

**Acceptance Criteria:**

**Given** a candlestick chart with signal data
**When** a Long signal exists at a timestamp
**Then** a green upward marker is rendered at that candle

**Given** a Short signal exists at a timestamp
**When** the chart renders
**Then** a red downward marker is rendered at that candle

**Given** the dashboard is running
**When** 60 seconds elapse
**Then** the scanner table and active chart auto-refresh with latest data
**And** APScheduler triggers a background data refresh cycle

**Given** the auto-refresh encounters an API or compute error
**When** the refresh fails
**Then** the error is logged via loguru
**And** the dashboard continues displaying the last known good data without crashing
