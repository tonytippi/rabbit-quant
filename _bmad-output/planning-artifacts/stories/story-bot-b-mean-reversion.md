# User Story: Phase 4.1 - Implement Dedicated Mean Reversion Engine (Bot B)

## Title
Implement Dedicated Mean Reversion Engine (Bot B) for Lower Timeframes with Strict Portfolio Heat Constraints

## Description
As a quantitative developer,  
I want to implement a dedicated Mean Reversion strategy (Bot B) that operates exclusively on lower timeframes (4H, 1H, 15m),  
So that I can exploit high-volatility intraday consolidation and increase capital turnover, without altering or interfering with the existing Trend-Following logic (Bot A) on the 1D chart.

## Acceptance Criteria

### 1. Configuration Updates (strategy.toml & config.py)
- [x] Add a new configuration block `[bot_b]` in `strategy.toml`.
- [x] Define Bot B specific regime thresholds: `hurst_max = 0.45` and `chop_min = 61.8`. (Relaxed to 0.55 in implementation due to Hurst bias).
- [x] Define Bot B fixed risk parameters: `take_profit_atr = 2.0` and `stop_loss_atr = 1.0`.

### 2. Strategy Routing in Numba Engine (vbt_runner.py)
- [x] Update the `simulate_portfolio_nb` function signature to accept a `strategy_type` integer flag (e.g., 0 for Bot A, 1 for Bot B).
- [x] Wrap the existing entry logic in a conditional block for Bot A (`if strategy_type == 0`), leaving its mathematics completely unchanged.
- [x] Implement the new Bot B entry logic (`elif strategy_type == 1`): Trigger entries exclusively when the market is in heavy consolidation (Hurst < 0.45 AND CHOP > 61.8) and aligns with the cycle phase (buy troughs, sell peaks).

### 3. Static Exit Logic for Bot B
- [x] Update the exit tracking arrays in the Numba loop to handle fixed targets.
- [x] If a position is opened by Bot B, calculate and freeze the Take Profit (Entry + 2*ATR) and Stop Loss (Entry - 1*ATR) at the time of entry.
- [x] Execute the Bot B exit immediately when the price crosses the static Take Profit or Stop Loss, bypassing the dynamic Trailing Stop/Breakeven Ratchet used by Bot A.

### 4. Cross-Sectional Ranking (Asset Selection)
- [x] Implement a specific ranking metric for Bot B in the pre-computation phase (Pandas) to measure the "rubber band effect" (e.g., Distance from the 20-SMA or RSI Z-Score) to quantify overextension.
- [x] Update the Numba sorting logic:
    - If `strategy_type == 0` (Bot A): Sort by Volatility-Adjusted Momentum.
    - If `strategy_type == 1` (Bot B): Sort Long candidates by the most extreme negative deviation (oversold), and Short candidates by the most extreme positive deviation (overbought).

### 5. Portfolio Heat & Matrix Execution Constraints
- [x] Ensure the Numba loop strictly adheres to the Time-First execution architecture (`for time -> for asset`) to maintain portfolio-level awareness.
- [x] Enforce the `max_concurrent_trades` cap (e.g., 2 trades = 4% maximum account heat). The engine must check `open_trades_count` before executing the top-ranked setups, halting execution once the capital allowance is reached to prevent systemic correlation risk.

### 6. Bulk Runner Integration & Validation (bulk_runner.py)
- [x] Update `run_bulk_backtest` to dynamically pass the correct `strategy_type` integer to the engine based on the timeframe (pass 0 if tf == "1d", pass 1 if tf in ["4h", "1h", "15m"]).
- [x] Run a multi-asset validation test to confirm Bot B successfully executes trades on lower timeframes, strictly respects the 2-trade maximum, and significantly improves the geometric Total Return.

## Quantitative Directives Check
- [x] **No Alpha-Asset Bias:** Time-First Numba loop enforced.
- [x] **No Portfolio Heat Overload:** Max 2 concurrent trades cap enforced.
- [x] **No Exit Collision:** Static targets for Bot B, dynamic for Bot A.
- [x] **Geometric Compounding:** Handled via existing `vectorbt` setup.
