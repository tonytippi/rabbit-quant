# User Story: Phase 3.5 - Cross-Sectional Ranking for Multi-Asset Capital Allocation

## Title
Implement Volatility-Adjusted Momentum Ranking to Eliminate Alphabetical Capital Drain

## Description
As a quantitative developer,
I want to implement a dynamic cross-sectional ranking system (Volatility-Adjusted Momentum) across the 50-token asset universe,
So that when a macroeconomic trend triggers dozens of simultaneous MTF buy signals, the Time-First Numba engine explicitly allocates its 2-trade concurrency limit to the absolute strongest market leaders, eliminating the software flaw of allocating capital based on alphabetical column indexing.

## Background & Context
During the expansion of the multi-asset portfolio from 3 tokens to 50 Binance tokens, the strategy's Total Return collapsed from +22.23% to 1.5%. Diagnostic analysis revealed an "Alphabetical Capital Drain" caused by the 2D matrix architecture.
When the macroeconomic regime shifts to a trend (Hurst > 0.55), the entire crypto market moves together. The Time-First Numba loop detects 30+ simultaneous valid buy setups. Because `max_concurrent_trades` is strictly capped at 2 (to protect against systemic flash crashes), the loop sequentially evaluates the DataFrame columns and immediately fills its capital allocation with the first two alphabetical tokens it sees (e.g., AAVE and ADA), completely starving high-beta leaders (like SOL or BTC) located further down the column index.
To achieve the >100% Total Return benchmark without dangerously increasing the risk profile to a 15-trade "shotgun" approach, the engine must prioritize quality over alphabetical order. We will achieve this by feeding a 2D `rank_metrics` array into the Numba matrix, ranking all valid signals by their Volatility-Adjusted Momentum before a single dollar is deployed.

## Acceptance Criteria
### 1. Vectorized Ranking Metric Calculation
- [ ] In `main.py`, calculate a 24-period lookback momentum array for all 50 tokens: `momentum_24h = closes.diff(24)`.
- [ ] Normalize the absolute momentum against the asset's intrinsic noise to calculate the Volatility-Adjusted Momentum Score: `Rank Score = (Close_current - Close_t-n) / ATR`
- [ ] Implement Numba-safe data casting: Scrub the resulting 2D DataFrame of all NaN and Infinite values (resulting from division by zero during flat market hours) and cast it to a strict `np.float64` NumPy array.

### 2. Numba Engine Integration
- [ ] Pass the cleaned `rank_metrics` 2D array into the existing `simulate_portfolio_nb` function.
- [ ] Verify that at timestamp `i`, the engine maps the `rank_metrics` to the `potentials_arr` array, successfully running `np.argsort(-candidate_ranks)` to push the highest-momentum tokens to the front of the execution queue.

### 3. Validation & Reporting
- [ ] Maintain the strict risk parameters: `risk_per_trade = 0.02` (2%) and `max_concurrent_trades = 2` (Max Portfolio Exposure = 4%).
- [ ] Run a new 50-token `--sweep` on the 4H timeframe.
- [ ] Output a multi-asset VectorBT tear sheet proving that the algorithmic sorting correctly captures the high-beta altcoin runners, pushing the Total Return back toward the 100%+ institutional benchmark while maintaining a Max Drawdown < 15%.

## Technical Details & Architecture Notes
**Pandas Pre-computation:** The ranking math must happen outside the Numba loop using Pandas vectorized operations to keep the C-compilation lightning fast.
```python
# Pre-compute the rank metrics before passing to @njit
lookback = 24
momentum = close_df.diff(lookback)
volatility_adjusted_momentum = momentum / atr_df

# CRITICAL: Numba will crash on NaNs or Infs
safe_rank_metrics = volatility_adjusted_momentum.fillna(0).replace([np.inf, -np.inf], 0).values
```
**The Math Rationale:** Why divide by ATR? A $0.10 token jumping $0.02 looks like a massive move, while a $50,000 token moving $100 looks tiny. Dividing the absolute price change by the asset's ATR standardizes the "momentum" across all 50 tokens, ensuring the engine compares apples to apples.