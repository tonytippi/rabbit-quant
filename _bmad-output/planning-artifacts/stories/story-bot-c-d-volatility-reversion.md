User Story: Phase 4.4 - Implement Volatility-Based Mean Reversion Engines (Bot C & Bot D)
Title: Implement Configurable Volatility-Based Mean Reversion Engines (Bot C: BB/Keltner Squeeze, Bot D: ATR-Filtered RSI) for Lower Timeframes

Description:
As a quantitative developer,
I want to introduce two new, fully independent mean-reversion models (Bot C and Bot D) based on real-time volatility metrics rather than lagging statistical filters (Hurst/CHOP),
So that I can effectively scale the trade frequency on lower timeframes (1H, 15m) to the 300-500 trade range, test multiple hypotheses simultaneously, and seamlessly toggle each strategy on or off via the configuration file.

Background & Context:
Empirical backtesting revealed that the Hurst Exponent and CHOP index suffer from severe lookback lag on lower timeframes, resulting in "trade starvation" (only ~60 trades over 5 years on the 1H chart). To capitalize on intraday noise, the system needs strategies that react to immediate volatility contractions.

Bot C (Squeeze Model): Enters when Bollinger Bands contract inside Keltner Channels (low volatility squeeze) and price Pierces the lower BB with an oversold RSI.

Bot D (Pure ATR-RSI Model): Enters when current volatility is below its historical average (ATR < 50-period ATR MA) combined with an extreme oversold RSI.
The architecture must support dynamic toggling—if a bot's timeframes array in strategy.toml is empty ([]), the engine must completely bypass its execution.

Acceptance Criteria:

1. Configuration Expansion (strategy.toml & config.py)

[ ] Add distinct [bot_c] and [bot_d] configuration blocks in strategy.toml.

[ ] Ensure each block has its own timeframes, max_concurrent_trades, risk_per_trade, take_profit_atr, stop_loss_atr, and max_holding_bars.

[ ] Implement a toggle mechanism: If a bot's timeframes array is empty (e.g., timeframes = []), bulk_runner.py must dynamically ignore that bot during the routing phase.

[ ] Add specific indicator parameters (e.g., bb_window, kc_window, kc_multiplier, atr_ma_window) to the respective config blocks.

2. Volatility Indicator Pre-Computation (bulk_runner.py)

[ ] Pre-compute Bollinger Bands (Upper, Lower) and Keltner Channels (Upper, Lower) for Bot C.

[ ] Pre-compute a 50-period Simple Moving Average of the ATR (ATR_MA50) for Bot D.

[ ] Pre-compute RSI for both Bot C and Bot D.

[ ] Clean all new arrays (handling NaN and Inf values) before passing them to the Numba compiler.

3. Multi-Strategy Routing in Numba Engine (vbt_runner.py)

[ ] Expand the simulate_portfolio_nb router to accept strategy_type as 0 (Bot A), 1 (Bot B), 2 (Bot C), and 3 (Bot D).

[ ] Bot C Logic (strategy_type == 2): Trigger Long entries ONLY IF: (Bollinger Upper < Keltner Upper) AND (Bollinger Lower > Keltner Lower) AND (Low < Bollinger Lower) AND (RSI < rsi_oversold).

[ ] Bot D Logic (strategy_type == 3): Trigger Long entries ONLY IF: (Current ATR < ATR_MA50) AND (RSI < rsi_oversold).

[ ] Ensure each bot maintains strictly isolated concurrency checking (e.g., checking open_trades_bot_c < bot_c.max_concurrent_trades).

4. Cross-Sectional Ranking & Time-Based Exits

[ ] Enforce the "Alphabetical Capital Drain" protection for Bot C and Bot D by sorting concurrent signals based on the lowest RSI (most extreme deviation) before allocating capital.

[ ] Ensure the Time-Based Exit (max_holding_bars) logic is universally applied to Bot C and Bot D to prevent dead capital lockups in ranging markets.

5. Validation & Portfolio Risk Limits

[ ] Run an isolated backtest with Bot A, B disabled (timeframes = []) and Bot C, D enabled on the 1h timeframe.

[ ] Verify that the trade frequency scales significantly (target: > 300 trades) while maintaining a high Win Rate and adhering to maximum portfolio heat caps (e.g., total system concurrency never exceeds the sum of active bots).