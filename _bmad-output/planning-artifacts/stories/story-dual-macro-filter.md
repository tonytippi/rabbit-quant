# User Story: Phase 3.7 - Implement Dual Macro Filter (Hurst & CHOP) with Dynamic Configuration

## Title
Implement Configurable Dual Macro Filter Engine (Rolling Hurst + CHOP)

## Description
As a quantitative developer,
I want to re-integrate the rolling Hurst Exponent calculation (with an expanded 100-period window) alongside the existing Choppiness Index (CHOP) and make their usage strictly controlled via `strategy.toml`,
So that I can dynamically switch between (or combine) these macro filters during execution, and optimize variables like `htf_threshold` and `ltf_threshold` via parameter sweeping without modifying the core Numba engine code.

## Background & Context
While the CHOP index is computationally lightweight and effective for basic ranging detection, the R/S Hurst Exponent provides superior mathematical insight into long-term persistence (memory) in the time series. Initially removed due to computational overhead, a C-compiled Numba Rolling Hurst implementation has proven viable. By utilizing an expanded 100-period window, the Hurst Exponent can act as a more robust macro-trend identifier.

Currently, the Numba `simulate_portfolio_nb` valid entry condition relies solely on CHOP, and its thresholds are hardcoded deep inside the execution pipeline. We need a flexible architecture that supports both indicators, allowing the backtester to utilize CHOP, Hurst, or a dual-handshake approach based on parameters injected dynamically from `strategy.toml`. Moving these parameters to the config also unlocks the ability to run exhaustive parameter sweeps across the filters.

## Acceptance Criteria
### 1. Rolling Hurst Re-Integration (Pandas/Numba)
- [x] Restore the `calculate_rolling_hurst` function in `src/signals/fractals.py` utilizing the `@njit` C-compiled `_rolling_hurst_rs` loop to ensure high-performance execution across 50 tokens.
- [x] Modify the rolling window from 30 periods to 100 periods to capture deeper macroeconomic trend persistence.
- [x] Ensure the 2D `matrix_hurst` in `bulk_runner.py` is safely shifted (`.shift(1).ffill()`) to prevent Look-Ahead Bias.

### 2. Configuration & Parameter Mapping (`strategy.toml`)
- [x] Update `config/strategy.toml` and `src/config.py` to include new filter selection logic (e.g., `macro_filter_type = "chop"` / `"hurst"` / `"both"`).
- [x] Expose all hardcoded thresholds (`htf_threshold`, `ltf_threshold`, `veto_threshold`) in the configuration file.
- [x] Add support for sweeping these new thresholds in the `StrategyConfig` sweep ranges to find the optimal combinations.

### 3. Numba Engine Execution (`vbt_runner.py`)
- [x] Update the `simulate_portfolio_nb` function signature to accept the `matrix_hurst` array and the required configuration flags/thresholds.
- [x] Modify the `valid` entry boolean logic inside the Numba loop to dynamically enforce conditions based on the selected `macro_filter_type`:
  - If `"hurst"`, enforce `hurst_value > hurst_threshold`
  - If `"chop"`, enforce `htf_metric < htf_threshold` & `ltf_metric > ltf_threshold`
  - If `"both"`, require all conditions to agree.

### 4. Validation & Sweeping
- [x] Run a 50-token backtest on the `4h` timeframe with `macro_filter_type="hurst"` and verify total trades drop compared to no filter.
- [x] Run a parameter sweep testing the permutations of CHOP vs. Hurst, outputting the highest Sharpe Ratios to the leaderboard CSV.

## Technical Details & Architecture Notes
**Performance Bottleneck Warning:** The `_rolling_hurst_rs` calculation must remain tightly bound in C-speed Numba execution. Calculate it sequentially across the assets before matrix alignment.

**The Master Router:** This Rolling Hurst matrix will become the core traffic controller for Phase 4. Capital will be routed to Bot A when rolling_hurst > 0.55, and eventually routed to Bot B when rolling_hurst < 0.45.
