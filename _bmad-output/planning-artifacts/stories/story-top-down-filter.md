# User Story: Implement Top-Down Filter Strategy (Strategy 1)

## Title
Implement Top-Down Filter (MTF) with Dual Hurst Handshake and Volatility Veto

## Description
As a quantitative developer,
I want to upgrade our current single-timeframe trading algorithm to a Multiple Timeframe (MTF) architecture implementing the "Top-Down Filter" strategy,
So that we can trade with higher probability by aligning Lower Timeframe (LTF) execution with Higher Timeframe (HTF) macroeconomic trends while actively mitigating "Ghost Traps" and Black Swan volatility events.

## Background & Context
Based on the brainstorming session (`brainstorming-session-2026-02-21.md`), the current single-timeframe logic is vulnerable to false signals (Ghost Traps) during volatile markets. The new architecture requires three core components:
1. **The Dual Hurst Handshake:** Ensuring both the macro trend (Daily) and the micro environment (15m) are structurally sound before entry.
2. **The ADX/Volatility Veto (Kill Switch):** A dynamic circuit breaker (Rolling Z-Score on ATR) to halt trading during abnormal market shocks.
3. **Robust Vectorized Backtesting:** Implementing precise `Resample-Shift-Forward-Fill` logic in `vectorbt` to absolutely eliminate Look-Ahead Bias during the 5-year historical backtest.

## Acceptance Criteria

### 1. Algorithm Enhancement (MTF Integration)
- [ ] Modify `src/data_loader.py` to seamlessly fetch and align both HTF (e.g., Daily) and LTF (e.g., 15m) data for a given asset.
- [ ] Implement the **Choppiness Index (CHOP)** as a computationally efficient substitute for Hurst during the vectorized backtesting phase.
- [ ] Update `src/signals/filters.py` and `src/signals/fractals.py` to support the Dual Hurst Handshake logic. To avoid the **Exhaustion Trap**, the LTF must be in compression while the HTF is trending:
    *   **Live (Hurst):** `if (H_daily >= 0.55) AND (H_15m < 0.45)`
    *   **Backtest (CHOP):** `if (CHOP_daily < 38.2) AND (CHOP_15m > 61.8)`
- [ ] Implement the **Volatility Veto**: Calculate a Rolling Z-Score for the LTF ATR. If `ATR_15m > 3 Standard Deviations above 50-period rolling mean`, trigger a system-wide halt (no trades).

### 2. Backtesting (5-Year Historical Data)
- [ ] Update `src/backtest/vbt_runner.py` to handle Multiple Timeframes.
- [ ] **CRITICAL:** Implement the `Resample -> Calculate -> Shift(1) -> Forward-Fill` pipeline for the HTF metric to guarantee **zero Look-Ahead Bias** when mapped to the 15m execution index.
- [ ] Execute a 5-year historical backtest across a predefined asset universe using `vectorbt`.
- [ ] Output a comprehensive performance report (Sharpe, Max Drawdown, Win Rate) comparing the new MTF Top-Down Filter against the baseline single-timeframe model.

### 3. Live Paper Trading Readiness
- [ ] Build a toggle or configuration parameter to switch the variance metric from CHOP (optimized for backtesting) back to the true **Numba-optimized Hurst Exponent** for live/paper execution.
- [ ] Ensure the live execution loop correctly queries the newly closed HTF candle and applies the Volatility Veto in real-time.
- [ ] Deploy the strategy to a paper trading environment for forward-testing validation.

### 4. Dashboard & Visualization Updates
- [ ] Update `src/dashboard/app.py` (Scanner and Chart views) to display the new MTF architecture context.
- [ ] The Scanner table must display both the LTF Hurst/CHOP value and the corresponding HTF Hurst/CHOP gatekeeper value.
- [ ] Add a column or visual indicator for the **Volatility Veto status** (e.g., displaying the current ATR Z-Score and whether the kill switch is active).
- [ ] Ensure the individual asset chart overlays accurately reflect the MTF signal logic (only painting a 'LONG' signal when both HTF and LTF conditions are met).
- [ ] Update the **Paper Trading tab** to record and display the MTF context (HTF Hurst, LTF Hurst, and Volatility state) at the exact time of trade entry for historical review.

## Technical Details & Architecture Notes

*   **Current State:** The codebase currently evaluates signals in isolation (`src/signals/filters.py`) and utilizes a highly performant Numba R/S Hurst calculation (`src/signals/fractals.py`). There is no existing MTF infrastructure.
*   **VectorBT MTF Alignment Snippet:**
    ```python
    # Conceptual MTF Alignment for VectorBT
    daily_data = vbt.Data.resample('1D')
    daily_chop = calculate_chop(daily_data)
    # The Shift Operator is MANDATORY to prevent Look-Ahead Bias
    safe_daily_chop = daily_chop.shift(1) 
    aligned_daily_chop = safe_daily_chop.ffill() # Map back to 15m index
    ```
*   **Dynamic Thresholds:** Avoid hardcoding the `0.55` and `0.45` Hurst thresholds; parameterize them as grid arrays for `vectorbt` optimization (`np.arange(0.5, 0.7, 0.05)`).
