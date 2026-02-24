# User Story: Implement Asymmetric Trade Management (Trailing Exits & Position Sizing)

## Title
Implement Asymmetric Trade Management (Trailing ATR Exits & Dynamic Position Sizing)

## Description
As a quantitative developer,
I want to upgrade the trade execution engine from rigid time-based cycle exits to dynamic, price-action based Trailing Exits,
So that winning trades initiated by the Top-Down Filter (MTF) can run for maximum profit along the macroeconomic trend, effectively overcoming the mathematical drag of exchange commission fees and significantly boosting the Sharpe Ratio.

## Background & Context
Following the successful implementation of the Top-Down Filter (MTF) strategy, a 5-year historical parameter sweep on BTC/USDT revealed excellent entry mechanics (filtering 175,000+ data points down to ~350 high-probability setups). However, the strategy generated a negative Sharpe Ratio (-1.41) due to two major flaws in the current trade management architecture:
1. **Commission Drag:** The engine paid $55,915 in exchange fees on 358 trades.
2. **Premature Exits (Time-Based):** The current logic forces an exit the moment the 15-minute cycle reaches the opposite peak (average trade duration: 52 minutes). This cuts off winning trades before they can mature into large swing trades that capitalize on the Daily (HTF) trend, destroying the Risk:Reward asymmetry needed to overcome a 0.1% fee structure.

To fix this, the strategy must transition from time-based exits (cycle peaks) to volatility-based trailing exits (ATR), allowing winners to run until the structural trend actually bends.

## Acceptance Criteria

### 1. Vectorized Trailing Stops (Backtesting Engine)
- [ ] Modify `src/backtest/vbt_runner.py` to support custom exit logic using VectorBT's trailing stop mechanics.
- [ ] Replace the hardcoded cycle-based exits (`long_exits = short_zone`) with a dynamic **ATR Trailing Stop**.
    - For Longs: Trail the stop `N * ATR` below the highest price reached since entry.
    - For Shorts: Trail the stop `N * ATR` above the lowest price reached since entry.
- [ ] Parameterize the Trailing Stop multiplier (`trailing_atr_multiplier`) and add it to the `strategy.toml` configuration and the multi-dimensional parameter sweep.

### 2. Live Trade Execution Engine Update
- [ ] Update the `PaperTrader` class in `src/services/trader.py` to support dynamic, moving Stop Losses (Trailing Stops).
- [ ] Implement a `monitor_positions` logic update that continuously recalculates and ratchets the Stop Loss level in the database (`trades_table`) as the price moves favorably.
- [ ] Implement a **Breakeven Ratchet**: Before the Trailing Stop takes full effect, if the price moves favorably by `1 * ATR`, instantly move the hard Stop Loss to the Entry Price (Breakeven) plus a microscopic margin to cover the 0.1% Binance fee. This guarantees a "Risk-Free" trade while waiting for the larger macro trend to unfold.

### 3. Dynamic Position Sizing (Risk Management)
- [ ] Update `src/backtest/vbt_runner.py` and `src/services/trader.py` to utilize fractional position sizing based on account equity and ATR risk, rather than trading 100% of available capital per trade.
- [ ] Implement a `risk_per_trade` configuration (e.g., 1% or 2% of total equity) to dictate position size, ensuring survivability during consecutive losing streaks.
- [ ] Position size must be calculated dynamically upon entry using the refined crypto-centric distance-to-stop formula:
    *   `Risk Amount ($) = Account Equity * Risk_Per_Trade %`
    *   `Distance to Stop ($) = N * ATR` (The actual capital at risk per single coin/unit)
    *   `Position Size (Units) = Risk Amount ($) / Distance to Stop ($)`
    *   *(This eliminates "Multiplier" confusion and directly maps ATR-based risk to order size).*

### 4. Single-Position Enforcement (Anti-Pyramiding)
- [ ] Because trades now stay open significantly longer (riding the Trailing Stop), the system must ignore new entry signals while a position is already active.
- [ ] Update `src/backtest/vbt_runner.py` to enforce a strict single-position rule (e.g., using VectorBT's `accumulate=False` or custom conflict resolution).

### 5. Validation & Reporting
- [ ] Run a new 5-year `--sweep` on BTC/USDT using the newly implemented Trailing ATR Exits.
- [ ] The engine must demonstrate a significantly improved Profit Factor (>1.5) and a positive Sharpe Ratio (>1.0) on the optimal parameter set, proving the mathematical viability of the strategy against real-world commission drag.

## Technical Details & Architecture Notes

*   **VectorBT Trailing Stops (The Trap):** Native `vbt.Portfolio.from_signals` supports `sl_stop` and `sl_trail`. However, passing an array of ATR values to `sl_stop` locks in the ATR value at the exact moment of entry. It does not dynamically recalculate as the trade progresses. To achieve a truly dynamic ATR Trailing Stop that expands/contracts with ongoing price action, we must bypass the native `sl_stop` parameter and write a custom Numba-compiled signal generator (`vbt.nb`) to iteratively evaluate the Highs/Lows and current ATR step-by-step, feeding a binary exits array back into the Portfolio module.
*   **Database Schema:** The `paper_trades` table already has a `sl` column. The `monitor_positions` loop will need a specific block to check: `if current_price > (entry_price + (X * ATR)): new_sl = current_price - (X * ATR); UPDATE trades_table SET sl = new_sl`.
*   **The Goal:** Shift the Win Rate / Reward profile from `High Win Rate / Low Reward` (which dies to fees) to `Moderate Win Rate / Massive Reward` (Asymmetric Trading).