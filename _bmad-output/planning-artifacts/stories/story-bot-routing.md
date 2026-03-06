User Story: Phase 4.2 - Implement Configurable Asymmetric Routing, Dynamic Timeframe Mapping, and Time-Based Exits
Title: Implement Configurable Asymmetric Routing, Dynamic Timeframe Mapping, Cross-Sectional Ranking, and Time-Based Exits

Description:
As a quantitative developer,
I want to fully decouple the execution logic of Bot A (Trend) and Bot B (Mean Reversion) by making their target timeframes, indicator thresholds (Hurst & CHOP), concurrency limits, and risk parameters fully configurable via strategy.toml, while introducing a Time-Based Exit mechanism for Bot B and strict Cross-Sectional Ranking for asset selection,
So that I can dynamically tune the strategy's environment constraints, maximize capital velocity, prevent alphabetical capital drain, and satisfy the Exhaustion Trap mandate without violating Portfolio Heat limits.

Background & Context:
Currently, strategy parameters and timeframe mappings are shared globally or hardcoded. To achieve institutional-grade flexibility, the Smart Router must be entirely config-driven with deeply isolated [bot_a] and [bot_b] blocks in strategy.toml. Bot A must enforce the "Exhaustion Trap" rule by requiring Micro Compression on lower timeframes before entering a macro trend. Furthermore, because bulk_runner.py processes timeframes sequentially, the Numba engine requires only a single dynamic trade counter. To comply with the "Alphabetical Capital Drain" directive, the engine must utilize cross-sectional ranking to allocate limited concurrency slots to the highest-probability setups first. Finally, Bot B requires a Time Stop mechanism to prevent dead capital lockups in ranging markets.

Acceptance Criteria:

1. Dynamic Configuration Updates (strategy.toml & config.py)

[ ] Create deeply isolated configuration blocks for [bot_a] and [bot_b] in strategy.toml.

[ ] Add a timeframes list to each bot (e.g., timeframes = ["1d"] for Bot A; timeframes = ["4h"] for Bot B).

[ ] Define asymmetric risk and concurrency settings:

Bot A: max_concurrent_trades = 2, risk_per_trade = 0.02.

Bot B: max_concurrent_trades = 4, risk_per_trade = 0.01, max_holding_bars = 12.

[ ] Make regime thresholds fully configurable, specifically enforcing the Exhaustion Trap for Bot A:

Bot A: hurst_min = 0.55, chop_htf_max = 45.0, and ltf_chop_min = 61.8 (Micro Compression).

Bot B: hurst_max = 0.55, chop_min = 58.0.

2. Dynamic Strategy Routing (bulk_runner.py)

[ ] Update the run_bulk_backtest loop to read the timeframes lists from the strategy config.

[ ] Dynamically determine the strategy_type integer (0 for Bot A, 1 for Bot B) by checking if the current timeframe tf belongs to Bot A or Bot B.

[ ] Pass the bot-specific thresholds (Hurst, CHOP, Concurrency, Risk) dynamically into the Numba engine based on the active strategy_type.

3. Asymmetric Capital Allocation & Cross-Sectional Ranking (vbt_runner.py)

[ ] Modify the simulate_portfolio_nb loop to use a single open_trades_count variable that is checked against the dynamically passed max_concurrent_trades parameter.

[ ] Implement strict Cross-Sectional Ranking inside the Numba Entry Router: Before allocating capital on any given bar, use the pre-computed rank_metric (Volatility-Adjusted Momentum for Bot A, or Extreme Deviation for Bot B) to sort all valid signals.

[ ] Allocate the limited concurrency slots strictly to the highest-ranked assets first, actively preventing the "Alphabetical Capital Drain" scenario.

4. Time-Based Exit Logic (Time Stop)

[ ] Initialize an array bars_in_trade = np.zeros(n_assets, dtype=np.int32) in the Numba engine to track the holding period of active positions.

[ ] Increment bars_in_trade[a] by 1 for every bar an asset remains in an open position, resetting to 0 upon entry.

[ ] Implement the Time Stop rule for Bot B (strategy_type == 1): If bars_in_trade[a] >= max_holding_bars, immediately force-close the position at the current market close price.

5. Validation & Portfolio Heat Compliance

[ ] Run a backtest verifying that the engine dynamically assigns Bot A to the 1D chart and Bot B to the 4H chart based purely on strategy.toml.

[ ] Verify that stagnant Bot B trades are successfully aborted after max_holding_bars.

[ ] Verify via trade logs that entries prioritize the highest-ranked assets (e.g., highest momentum or highest RSI deviation) rather than defaulting to the alphabetical index of the DataFrame columns.
