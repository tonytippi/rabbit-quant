"""Bulk backtest runner for multiple assets and timeframes.

Orchestrates the execution of backtests across all configured symbols and timeframes,
providing a consolidated summary report and leaderboard.
"""

import time
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

from src.backtest.analyzer import export_trade_log_csv
from src.backtest.vbt_runner import run_backtest
from src.config import AppSettings, AssetConfig, StrategyConfig, TimeframeConfig
from src.data_loader import get_connection, query_ohlcv
from src.fetchers.orchestrator import fetch_all_assets
from src.signals.cycles import detect_dominant_cycle_filtered
from src.signals.filters import calculate_atr_zscore_series
from src.signals.fractals import calculate_chop, calculate_rolling_hurst


def _calculate_atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range (ATR) series."""
    high = df["high_price"]
    low = df["low_price"]
    close = df["close_price"]

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(window=period).mean()
    return atr.bfill()


def _calculate_rsi_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index (RSI)."""
    close = df["close_price"]
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.bfill().fillna(50.0)


def _calculate_bb_kc_series(df: pd.DataFrame, bb_window: int = 20, bb_std: float = 2.0, kc_window: int = 20, kc_mult: float = 1.5):
    """Calculate Bollinger Bands and Keltner Channels."""
    close = df["close_price"]
    high = df["high_price"]
    low = df["low_price"]
    
    # Bollinger Bands
    sma = close.rolling(window=bb_window).mean()
    std = close.rolling(window=bb_window).std()
    bb_upper = sma + (std * bb_std)
    bb_lower = sma - (std * bb_std)
    
    # Keltner Channels
    ema = close.ewm(span=kc_window, adjust=False).mean()
    atr = _calculate_atr_series(df, period=kc_window)
    kc_upper = ema + (atr * kc_mult)
    kc_lower = ema - (atr * kc_mult)
    
    return bb_upper.bfill(), bb_lower.bfill(), kc_upper.bfill(), kc_lower.bfill()


async def run_bulk_backtest(
    settings: AppSettings,
    assets: AssetConfig,
    strategy: StrategyConfig,
    timeframes: TimeframeConfig,
    asset_type: str = "crypto",
    sweep: bool = False,
    fetch: bool = False,
) -> None:
    """Run bulk backtest across all symbols and timeframes."""

    # Step 1: Optional Fetch
    if fetch:
        logger.info("Fetching latest data for all assets...")
        conn = get_connection(settings)
        await fetch_all_assets(conn, assets, timeframes)
        conn.close()

    symbols = assets.crypto_symbols if asset_type == "crypto" else assets.stock_symbols
    tfs = list(set(
        strategy.bot_a_timeframes +
        strategy.bot_b_timeframes +
        strategy.bot_c_timeframes +
        strategy.bot_d_timeframes
    ))

    logger.info(f"Starting bulk backtest for {len(symbols)} symbols x {len(tfs)} timeframes...")
    start_time = time.monotonic()

    results = []
    skipped_timeframes: list[tuple[str, str]] = []
    conn = get_connection(settings, read_only=True)

    # Group by Timeframe, NOT by Symbol
    for tf in tfs:
        logger.info(f"Processing timeframe: {tf}")

        close_dict, high_dict, low_dict = {}, {}, {}
        atr_dict, phase_dict, hurst_dict = {}, {}, {}
        ltf_dict, htf_dict, vol_z_dict, htf_dir_dict = {}, {}, {}, {}
        rsi_dict, atr_ma_dict = {}, {}
        bb_upper_dict, bb_lower_dict, kc_upper_dict, kc_lower_dict = {}, {}, {}, {}

        missing_count = 0
        insufficient_count = 0
        cycle_fail_count = 0

        # 1. Fetch and calculate indicators for all symbols
        for sym in symbols:
            df = query_ohlcv(conn, sym, tf)
            if df.empty:
                missing_count += 1
                continue
            if len(df) < strategy.hurst_min_data_points:
                insufficient_count += 1
                continue

            cycle_result = detect_dominant_cycle_filtered(df, cutoff=strategy.cycle_lowpass_cutoff)
            if not cycle_result:
                cycle_fail_count += 1
                continue

            df_time = df.copy()
            df_time["timestamp"] = pd.to_datetime(df_time["timestamp"])
            df_time.set_index("timestamp", inplace=True)

            rolling_hurst = calculate_rolling_hurst(df_time, window=256).shift(1).ffill()

            close_dict[sym] = df_time["close_price"]
            high_dict[sym] = df_time["high_price"]
            low_dict[sym] = df_time["low_price"]

            atr_dict[sym] = _calculate_atr_series(df_time, period=14)
            phase_dict[sym] = pd.Series(cycle_result["phase_array"], index=df_time.index)
            hurst_dict[sym] = rolling_hurst
            rsi_dict[sym] = _calculate_rsi_series(df_time, period=max(strategy.bot_b_rsi_period, strategy.bot_c_rsi_period, strategy.bot_d_rsi_period))
            
            # Bot C (Squeeze)
            bbu, bbl, kcu, kcl = _calculate_bb_kc_series(df_time, strategy.bot_c_bb_window, strategy.bot_c_bb_std, strategy.bot_c_kc_window, strategy.bot_c_kc_multiplier)
            bb_upper_dict[sym] = bbu
            bb_lower_dict[sym] = bbl
            kc_upper_dict[sym] = kcu
            kc_lower_dict[sym] = kcl
            
            # Bot D (ATR MA)
            atr_ma_dict[sym] = atr_dict[sym].rolling(window=strategy.bot_d_atr_ma_window).mean().bfill()

            # LTF metrics
            ltf_dict[sym] = calculate_chop(df_time)
            vol_z_dict[sym] = calculate_atr_zscore_series(df_time)

            # HTF metrics
            daily_df = df_time.resample("1D").agg({
                "open_price": "first",
                "high_price": "max",
                "low_price": "min",
                "close_price": "last",
                "volume": "sum"
            }).dropna()

            if not daily_df.empty:
                daily_chop = calculate_chop(daily_df, period=30)
                safe_daily_chop = daily_chop.shift(1)

                daily_sma = daily_df["close_price"].rolling(window=50).mean()
                daily_direction = np.where(daily_df["close_price"] > daily_sma, 1, -1)
                safe_daily_dir = pd.Series(daily_direction, index=daily_df.index).shift(1)

                htf_dict[sym] = safe_daily_chop.reindex(df_time.index).ffill().fillna(50.0)
                htf_dir_dict[sym] = safe_daily_dir.reindex(df_time.index).ffill().fillna(0)
            else:
                htf_dict[sym] = pd.Series(50.0, index=df_time.index)
                htf_dir_dict[sym] = pd.Series(0.0, index=df_time.index)

        if not close_dict:
            reason = (
                f"no eligible symbols (missing={missing_count}, "
                f"insufficient<{strategy.hurst_min_data_points}={insufficient_count}, "
                f"cycle_fail={cycle_fail_count})"
            )
            skipped_timeframes.append((tf, reason))
            logger.warning(f"Skipping timeframe {tf}: {reason}")
            continue

        # 2. Build the 2D Matrices
        matrix_close = pd.DataFrame(close_dict).ffill().bfill()
        matrix_high = pd.DataFrame(high_dict).reindex(matrix_close.index).ffill().bfill()
        matrix_low = pd.DataFrame(low_dict).reindex(matrix_close.index).ffill().bfill()
        matrix_atr = pd.DataFrame(atr_dict).reindex(matrix_close.index).ffill().fillna(0.0)
        matrix_phase = pd.DataFrame(phase_dict).reindex(matrix_close.index).ffill().fillna(0.0)

        matrix_ltf = pd.DataFrame(ltf_dict).reindex(matrix_close.index).ffill().fillna(100.0)
        matrix_htf = pd.DataFrame(htf_dict).reindex(matrix_close.index).ffill().fillna(50.0)
        matrix_vol_z = pd.DataFrame(vol_z_dict).reindex(matrix_close.index).ffill().fillna(0.0)
        matrix_htf_dir = pd.DataFrame(htf_dir_dict).reindex(matrix_close.index).ffill().fillna(0.0)
        matrix_rsi = pd.DataFrame(rsi_dict).reindex(matrix_close.index).ffill().fillna(50.0)
        
        matrix_bb_u = pd.DataFrame(bb_upper_dict).reindex(matrix_close.index).ffill().fillna(0.0)
        matrix_bb_l = pd.DataFrame(bb_lower_dict).reindex(matrix_close.index).ffill().fillna(0.0)
        matrix_kc_u = pd.DataFrame(kc_upper_dict).reindex(matrix_close.index).ffill().fillna(0.0)
        matrix_kc_l = pd.DataFrame(kc_lower_dict).reindex(matrix_close.index).ffill().fillna(0.0)
        matrix_atr_ma = pd.DataFrame(atr_ma_dict).reindex(matrix_close.index).ffill().fillna(0.0)

        matrix_hurst_df = pd.DataFrame(hurst_dict).reindex(matrix_close.index).ffill().fillna(strategy.hurst_threshold)
        matrix_hurst = matrix_hurst_df.values

        active_bots = []
        if tf in strategy.bot_a_timeframes: active_bots.append(0)
        if tf in strategy.bot_b_timeframes: active_bots.append(1)
        if tf in strategy.bot_c_timeframes: active_bots.append(2)
        if tf in strategy.bot_d_timeframes: active_bots.append(3)

        for strategy_type in active_bots:
            bot_names = {0: 'A (Trend)', 1: 'B (Mean Reversion)', 2: 'C (Squeeze)', 3: 'D (ATR-RSI)'}
            logger.info(f"Using Strategy Bot {bot_names[strategy_type]}")

            if strategy_type == 0:
                active_max_concurrent = strategy.bot_a_max_concurrent_trades
                active_risk = strategy.bot_a_risk_per_trade
                active_hurst_threshold = strategy.bot_a_hurst_min
                active_htf_threshold = strategy.bot_a_chop_htf_max
                active_ltf_threshold = strategy.bot_a_ltf_chop_min
                # Volatility-Adjusted Momentum Ranking (Bot A)
                lookback = 24
                momentum = matrix_close.diff(lookback)
                volatility_adjusted_momentum = momentum / matrix_atr
                matrix_rank = volatility_adjusted_momentum.fillna(0).replace([np.inf, -np.inf], 0)
            elif strategy_type == 1:
                active_max_concurrent = strategy.bot_b_max_concurrent_trades
                active_risk = strategy.bot_b_risk_per_trade
                active_hurst_threshold = strategy.bot_b_hurst_max
                active_htf_threshold = 45.0  # Unused practically by bot B
                active_ltf_threshold = strategy.bot_b_chop_min
                # Extreme Oscillator Deviation (Bot B) - Use RSI as the rank metric
                matrix_rank = matrix_rsi.replace([np.inf, -np.inf], 50.0)
            elif strategy_type == 2:
                active_max_concurrent = strategy.bot_c_max_concurrent_trades
                active_risk = strategy.bot_c_risk_per_trade
                active_hurst_threshold = strategy.hurst_threshold
                active_htf_threshold = 45.0
                active_ltf_threshold = 50.0
                matrix_rank = matrix_rsi.replace([np.inf, -np.inf], 50.0)
            elif strategy_type == 3:
                active_max_concurrent = strategy.bot_d_max_concurrent_trades
                active_risk = strategy.bot_d_risk_per_trade
                active_hurst_threshold = strategy.hurst_threshold
                active_htf_threshold = 45.0
                active_ltf_threshold = 50.0
                matrix_rank = matrix_rsi.replace([np.inf, -np.inf], 50.0)

            # 3. Call the Engine EXACTLY ONCE with the full StrategyConfig
            freq_str = tf.replace("m", "min")
            res = run_backtest(
                close=matrix_close,
                high=matrix_high,
                low=matrix_low,
                atr=matrix_atr,
                phase_array=matrix_phase.values,
                hurst_value=matrix_hurst,
                ltf_metric=matrix_ltf.values,
                htf_metric=matrix_htf.values,
                volatility_zscore=matrix_vol_z.values,
                htf_direction=matrix_htf_dir.values,
                rank_metric=matrix_rank.values,
                bb_upper=matrix_bb_u.values,
                bb_lower=matrix_bb_l.values,
                kc_upper=matrix_kc_u.values,
                kc_lower=matrix_kc_l.values,
                atr_ma=matrix_atr_ma.values,
                macro_filter_type=strategy.macro_filter_type,
                htf_threshold=active_htf_threshold,
                ltf_threshold=active_ltf_threshold,
                veto_threshold=strategy.veto_threshold,
                hurst_threshold=active_hurst_threshold,
                trailing_multiplier=strategy.trailing_atr_multiplier,
                breakeven_threshold=strategy.breakeven_atr_threshold,
                max_concurrent_trades=active_max_concurrent,
                risk_per_trade=active_risk,
                initial_capital=strategy.backtest_initial_capital,
                commission=strategy.backtest_commission,
                freq=freq_str,
                strategy_type=strategy_type,
                bot_b_hurst_max=strategy.bot_b_hurst_max,
                bot_b_chop_min=strategy.bot_b_chop_min,
                bot_b_take_profit_atr=strategy.bot_b_take_profit_atr,
                bot_b_stop_loss_atr=strategy.bot_b_stop_loss_atr,
                bot_b_max_holding_bars=strategy.bot_b_max_holding_bars,
                bot_b_rsi_oversold=strategy.bot_b_rsi_oversold,
                bot_b_rsi_overbought=strategy.bot_b_rsi_overbought,
                bot_c_take_profit_atr=strategy.bot_c_take_profit_atr,
                bot_c_stop_loss_atr=strategy.bot_c_stop_loss_atr,
                bot_c_max_holding_bars=strategy.bot_c_max_holding_bars,
                bot_c_rsi_oversold=strategy.bot_c_rsi_oversold,
                bot_d_take_profit_atr=strategy.bot_d_take_profit_atr,
                bot_d_stop_loss_atr=strategy.bot_d_stop_loss_atr,
                bot_d_max_holding_bars=strategy.bot_d_max_holding_bars,
                bot_d_rsi_oversold=strategy.bot_d_rsi_oversold,
            )

            if res:
                bot_letter = 'A' if strategy_type==0 else 'B' if strategy_type==1 else 'C' if strategy_type==2 else 'D'
                res["timeframe"] = tf
                res["symbol"] = f"PORTFOLIO_BOT_{bot_letter}"
                res["best_hurst_threshold"] = strategy.hurst_threshold
                results.append(res)

                # Export trade log for this timeframe
                output_dir = Path(strategy.backtest_output_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                csv_path = output_dir / f"trades_PORTFOLIO_{tf}_BOT_{bot_letter}.csv"
                export_trade_log_csv(res["portfolio"], str(csv_path), symbol=f"PORTFOLIO_BOT_{bot_letter}")
            else:
                reason = "backtest engine returned no result"
                skipped_timeframes.append((tf, reason))
                logger.warning(f"Skipping timeframe {tf}: {reason}")

    conn.close()

    elapsed = time.monotonic() - start_time
    print(
        f"\n\nBulk run complete in {elapsed:.1f}s. "
        f"Configured={len(tfs)}, completed={len(results)}, skipped={len(skipped_timeframes)}."
    )

    if skipped_timeframes:
        print("\nSkipped timeframes:")
        for tf, reason in skipped_timeframes:
            print(f"  - {tf}: {reason}")

    if not results:
        logger.warning("No results generated. Check if data exists.")
        return

    # Step 3: Aggregate & Report
    df = pd.DataFrame(results)

    # Sort by Sharpe Ratio descending
    df = df.sort_values("sharpe_ratio", ascending=False).reset_index(drop=True)

    # Console Leaderboard
    print("\n=== LEADERBOARD (Top 10) ===")
    print(df[[
        "symbol", "timeframe", "sharpe_ratio", "total_return", "max_drawdown", "total_trades", "win_rate", "best_hurst_threshold"
    ]].head(10).to_string(index=False))

    # Save to CSV
    output_dir = Path(strategy.backtest_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"summary_bulk_{asset_type}.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nFull results saved to: {csv_path}")
