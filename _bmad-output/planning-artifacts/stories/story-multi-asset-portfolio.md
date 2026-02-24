# User Story: Phase 3 - Multi-Asset Portfolio Backtesting & Diversification

## Title
Implement Multi-Asset Portfolio Execution (VectorBT) for Beta Harvesting & Systemic Risk Control

## Description
As a quantitative developer,
I want to upgrade the Backtest Engine (`vbt_runner.py`) and Live Execution environment to seamlessly handle simultaneous multi-asset portfolios (e.g., BTC, ETH, SOL),
So that I can reduce the `risk_per_trade` back down to a conservative 1-2%, widen the Trailing Stops to 3.0x ATR for maximum trend capture, and rely on the high-Beta nature of altcoin runners to compound my Total Return well over the 100% benchmark, while strictly capping Systemic Drawdown via Portfolio-Level Exposure Limits.

## Background & Context
In Phase 2 (Asymmetric Trade Management), we successfully stabilized the Top-Down Filter's Win Rate (28%+) and Sharpe Ratio (3.0+) on the 1H timeframe. However, to hit aggressive absolute return targets (>50%) on a single asset (BTC), we had to artificially inflate the risk to 7% per trade.

The quantitative solution is **Portfolio Beta Harvesting**. By diversifying the engine across high-beta assets like Bitcoin (BTC), Ethereum (ETH), and Solana (SOL):
1. We can drop the `risk_per_trade` back down to a highly conservative 1% - 2%.
2. We can widen the Trailing Stop back to 3.0x ATR.
3. The stacked returns from high-beta altcoins (which often outpace BTC during macro trends) will exponentially compound the Total Return.

**The Correlation Threat:** BTC, ETH, and SOL are highly correlated (Covariance is heavily positive). They do not offer true "Uncorrelated Alpha." Because of this, a Flash Crash will hit all three simultaneously. If the system enters all three at 2% risk, a systemic flash crash will cause a simultaneous 6% drawdown. We must implement a strict Portfolio-Level Exposure Cap to prevent this systemic risk.

## Acceptance Criteria

### 1. Multi-Asset Data Harmonization
- [ ] Update `src/backtest/vbt_runner.py` to accept 2D pandas DataFrames (where columns represent multiple assets like `BTC/USDT`, `ETH/USDT`, `SOL/USDT`) instead of a single 1D Series.
- [ ] Ensure all supporting indicator arrays (HTF Direction, MTF CHOP metrics, Phase Array, ATR, Highs, Lows) correctly align their shapes as 2D matrices natively supported by VectorBT's vectorized broadcasting.

### 2. Upgraded Numba Compilation (@njit)
- [ ] Refactor the custom `calculate_trailing_exits_nb` Numba loop to iterate over 2D arrays (Columns = Assets, Rows = Time) so the engine can process trailing stops and breakeven ratchets for multiple coins simultaneously at high speed.
- [ ] Ensure independent tracking of `highest_price`, `lowest_price`, and `is_breakeven` variables for each asset within the loop.

### 3. Risk Configuration Re-calibration & Exposure Caps
- [ ] Update `strategy.toml` defaults:
    - Drop `risk_per_trade` to `0.02` (2%).
    - Set `breakeven_atr_threshold` to `2.0`.
    - Adjust `trailing_atr_multiplier_range` to `[2.5, 3.0, 3.5]`.
- [ ] Add `ETH/USDT` and `SOL/USDT` to the `crypto.symbols` list in `config/assets.toml`.
- [ ] **Implement a Portfolio-Level Exposure Cap:** The engine must never risk more than `X%` (e.g., 4%) of total account equity at any given time across all active positions.
- [ ] **Implement a Signal Ranker:** If BTC, ETH, and SOL all fire valid MTF buy signals in the same candle, the engine must rank them by structural strength (e.g., highest Daily Hurst value or lowest 15m CHOP value) and only allocate capital to the Top 2, preventing the portfolio from becoming over-leveraged on a single directional market move.

### 4. Validation & Reporting
- [ ] Run a new 5-year `--sweep` passing the combined BTC, ETH, and SOL datasets into the engine simultaneously.
- [ ] Generate a multi-asset VectorBT portfolio tear sheet proving that the combined Total Return breaches the 100%+ threshold while maintaining a Max Drawdown < 30%.

## Technical Details & Architecture Notes

*   **VectorBT 2D Matrix Evaluation:** To successfully implement the Signal Ranker and Portfolio Exposure Cap, the custom Numba logic (`@njit`) must be structured as a **Time-First** loop, not Asset-First. The engine must evaluate row-by-row (`for i in range(n): for col in range(num_assets): ...`). This allows the system to pause at every single candlestick, scan all available assets, rank them, check the current portfolio-level capital allocation, and then decide which assets get the money before moving to the next timestamp.
*   **Capital Allocation:** By default, if three assets fire a buy signal simultaneously and `risk_per_trade` is 2%, the engine will deploy 6% of the current cash pile. Ensure `accumulate=False` operates on a per-asset basis, meaning the engine can hold 1 BTC trade, 1 ETH trade, and 1 SOL trade concurrently, but never 2 BTC trades.