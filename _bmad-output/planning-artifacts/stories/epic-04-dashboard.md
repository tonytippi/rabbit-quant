---
stepsCompleted: [1, 2, 3, 4]
lastStep: 4
status: 'complete'
completedAt: '2026-02-13'
inputDocuments:
  - prd.md
  - _bmad-output/planning-artifacts/architecture.md
---

# Epic 4: Interactive Trading Dashboard

Users can visually monitor markets in real-time, scan for opportunities by Hurst ranking, and see buy/sell signals on interactive charts with cycle overlays.

## Stories

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

### Story 4.5: Writer Service for Server Deployment

As a **devops engineer**,
I want a dedicated "run-scheduler" command that handles data fetching in a separate process,
So that I can deploy the dashboard in a read-only container without DuckDB locking conflicts.

**Acceptance Criteria:**

**Given** `main.py` is executed with `run-scheduler`
**When** the service starts
**Then** it enters a persistent loop
**And** schedules `fetch_all_assets` to run every X minutes (configurable)

**Given** the scheduler is running
**When** the fetch job triggers
**Then** it acquires the DuckDB write lock, updates data, and releases the lock

**Given** the dashboard is running simultaneously
**When** it reads data
**Then** it does so in `read_only=True` mode and does not block the scheduler

### Story 4.6: Headless Signal Scanner

As a **quant trader**,
I want the Writer Service to automatically scan for trading signals after every data fetch and log opportunities to a file,
So that I can receive trade alerts without keeping the dashboard open.

**Acceptance Criteria:**

**Given** the Writer Service has completed a fetch cycle
**When** new data is available
**Then** it immediately triggers a signal scan for all assets

**Given** the scan detects a "LONG" or "SHORT" signal (based on Strategy Config)
**When** the signal is confirmed (Hurst > threshold)
**Then** the signal details (Symbol, Timeframe, Direction, Price, Hurst) are logged to `logs/trading_signals.log`
**And** a summary is printed to the console logs

### Story 4.7: Telegram Signal Alerts

As a **mobile trader**,
I want to receive an instant Telegram notification when a high-confidence signal is detected,
So that I can act on opportunities while away from my computer.

**Acceptance Criteria:**

**Given** valid `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`
**When** the Headless Signal Scanner detects a signal
**Then** a formatted message is sent to the configured Telegram chat
**And** the message includes: Symbol, Timeframe, Direction, Price, Hurst value, and Phase

**Given** the Telegram API is unreachable
**When** sending fails
**Then** the error is logged, but the scheduler continues running without crashing
