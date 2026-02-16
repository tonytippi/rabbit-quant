---
stepsCompleted: [1, 2, 3, 4]
lastStep: 4
status: 'complete'
completedAt: '2026-02-13'
inputDocuments:
  - prd.md
  - _bmad-output/planning-artifacts/architecture.md
---

# Epic 3: Strategy Backtesting & Optimization

Users can validate trading hypotheses by backtesting cycle+Hurst strategies with parameter optimization and detailed performance reports.

## Stories

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

### Story 3.6: Bulk Backtest & Optimization

As a **quant researcher**,
I want to execute backtests across all configured symbols and timeframes in a single command,
So that I can rapidly identify the best performing assets across the entire market.

**Acceptance Criteria:**

**Given** multiple symbols and timeframes configured in `assets.toml` and `timeframes.toml`
**When** I run `python main.py backtest-all`
**Then** the system iterates through every symbol/timeframe combination
**And** runs a parameter sweep for each

**Given** the `--fetch` flag is provided
**When** the command runs
**Then** it automatically downloads the latest data for all symbols before backtesting

**Given** the execution is complete
**When** the results are ready
**Then** a "Leaderboard" is printed to the console showing the top assets by Sharpe Ratio
**And** a consolidated CSV summary is saved to the output directory
