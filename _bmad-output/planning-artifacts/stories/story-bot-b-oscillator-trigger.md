User Story: Phase 4.3 - Implement Oscillator Trigger for Bot B
Title: Replace Cycle Phase Trigger with Extreme Oscillator Deviation (RSI/Z-Score) for Bot B

Description:
As a quantitative developer,
I want to replace the sinusoidal Cycle Phase trigger with an Extreme Deviation trigger (such as RSI or Bollinger Bands Z-Score) for Bot B's entry logic,
So that the engine can successfully execute trades in chaotic, ranging markets (Hurst < 0.55, CHOP > 58) where price action does not form clean sine waves, thereby resolving trade starvation and fully utilizing the Mean Reversion architecture.

Background & Context:
Backtest data proves that while the environment filters (Hurst < 0.55 and CHOP > 58) correctly identify high-volatility ranging markets, Bot B is severely starved of trades. This occurs because ranging markets have broken sinusoidal structures, making the detect_dominant_cycle logic mathematically incompatible. To fix this, Bot B must use a momentum oscillator designed for ranging environments (like RSI or Z-Score) as its entry trigger. This oscillator will also serve as the perfect Cross-Sectional Ranking metric to satisfy the "Alphabetical Capital Drain" constraint mandated in the system directives, sorting assets by the most extreme oversold deviation before allocating capital.

Acceptance Criteria:

1. Configuration Updates (strategy.toml)

[ ] Add specific oscillator parameters to the [bot_b] configuration block (e.g., rsi_period = 14, rsi_oversold = 30, rsi_overbought = 70).

2. Indicator Pre-Computation (bulk_runner.py)

[ ] Calculate the chosen oscillator (RSI or Z-Score) using Pandas vectorization before passing the arrays to the Numba engine.

[ ] Clean the arrays (handling NaN and Inf values) to comply with Numba compilation constraints.

3. Divergent Entry Logic in Numba Engine (vbt_runner.py)

[ ] Modify the Entry Router logic inside simulate_portfolio_nb to use completely separate triggers based on the strategy_type.

[ ] If strategy_type == 0 (Bot A): Continue requiring the mathematical Cycle Phase alignment (e.g., bottoming phase) alongside the macro-expansion filters.

[ ] If strategy_type == 1 (Bot B): Completely ignore the Cycle Phase array. Require RSI < rsi_oversold (for Long entries) alongside the ranging environment filters (Hurst < 0.55 and CHOP > 58.0).

4. Cross-Sectional Ranking Integration

[ ] Update the sorting logic for Bot B to utilize the new oscillator values. When multiple assets trigger a Mean Reversion setup simultaneously, the engine must allocate the limited concurrency slots to the assets with the lowest RSI (most extremely oversold) first.

5. Validation & Institutional Compliance

[ ] Run a backtest on the 4H and 1H timeframes.

[ ] Verify that the total trade count for Bot B increases significantly (e.g., to a statistically significant sample size > 100 trades over 5 years) while maintaining a Win Rate strictly > 60%.