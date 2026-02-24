---
stepsCompleted: [1, 2, 3, 4]
lastStep: 4
status: 'complete'
completedAt: '2026-02-16'
inputDocuments:
  - prd.md
  - _bmad-output/planning-artifacts/architecture.md
---

# Epic 5: Live Paper Trading System

Users can test strategies in real-time with a simulated portfolio, tracking PnL without risking real capital.

## Stories

### Story 5.1: Paper Trading Database Schema

As a **system architect**,
I want a database schema to store portfolio state (balance, positions, trade history),
So that the trading bot can persist its activities across restarts.

**Acceptance Criteria:**

**Given** the Postgres/DuckDB database
**When** the application initializes
**Then** two new tables are created:
1.  `portfolio_state`: Stores `current_balance`, `initial_balance`, `updated_at`.
2.  `paper_trades`: Stores `symbol`, `side` (LONG/SHORT), `entry_price`, `quantity`, `tp`, `sl`, `status` (OPEN/CLOSED/CANCELED), `exit_price`, `pnl`, `timestamps`.

### Story 5.2: Execution Engine (Entry Logic)

As a **quant trader**,
I want the system to automatically open paper trades when high-confidence signals are detected,
So that I can verify if the signals actually lead to profitable outcomes.

**Acceptance Criteria:**

**Given** a "STRONG BUY" or "STRONG SELL" signal from the Scanner
**And** the signal's timeframe matches the configured `trading_timeframes` (e.g., 1h, 4h)
**And** sufficient "paper USD" balance exists
**When** the signal is processed
**Then** a new trade record is inserted into `paper_trades` with `OPEN` status
**And** the Position Size is calculated (e.g., Fixed $1000 or % of Equity)
**And** TP/SL levels are recorded based on the signal's ATR calculation

### Story 5.3: Execution Engine (Exit Logic)

As a **quant trader**,
I want the system to monitor open positions and close them when TP or SL levels are hit,
So that I can capture profits and limit losses automatically.

**Acceptance Criteria:**

**Given** an `OPEN` position in `paper_trades`
**When** new market data is fetched
**Then** the system compares the current `close_price` (or High/Low) against the trade's `tp` and `sl`

**Given** price hits TP
**When** the exit executes
**Then** the trade status updates to `CLOSED`, `exit_price` is recorded, and `pnl` is calculated
**And** the `portfolio_state` balance is increased by the proceeds

**Given** price hits SL
**When** the exit executes
**Then** the trade is closed with a loss, and balance is updated accordingly

### Story 5.4: Paper Trading Dashboard

As a **user**,
I want a dedicated dashboard tab to view my paper portfolio performance,
So that I can evaluate the strategy's real-time effectiveness.

**Acceptance Criteria:**

**Given** the Streamlit dashboard
**When** I navigate to the "Paper Trading" tab
**Then** I see metrics: `Total PnL`, `Win Rate`, `Current Balance`, `Open Exposure`
**And** a table of "Active Positions" with live unrealized PnL
**And** a history table of "Closed Trades"

### Story 5.5: Portfolio Reset

As a **user**,
I want to reset my paper trading account to its initial state,
So that I can restart testing with a clean slate after tweaking parameters.

**Acceptance Criteria:**

**Given** the dashboard or CLI
**When** I trigger a "Reset Portfolio" action
**Then** all rows in `paper_trades` are deleted (or archived)
**And** `portfolio_state` is reset to the initial capital (e.g., $10,000)
