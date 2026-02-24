"""Paper Trading Execution Engine.

Handles logic for opening and closing simulated trades, managing portfolio state,
and tracking PnL.
"""

from typing import Union
import pandas as pd
from loguru import logger
import duckdb
from sqlalchemy import text, insert, update, select
from sqlalchemy.engine import Connection as AlchemyConnection

from src.data_loader import DBConnection, portfolio_table, trades_table
from src.config import PaperConfig


class PaperTrader:
    """Manages paper trading operations."""

    def __init__(self, conn: DBConnection, config: PaperConfig) -> None:
        self.conn = conn
        self.config = config
        self.is_postgres = not isinstance(conn, duckdb.DuckDBPyConnection)

    def _get_balance(self) -> float:
        """Get current portfolio balance."""
        try:
            if self.is_postgres:
                stmt = select(portfolio_table.c.current_balance).where(portfolio_table.c.id == "main")
                return self.conn.scalar(stmt) or 0.0
            else:
                res = self.conn.execute("SELECT current_balance FROM portfolio_state WHERE id = 1").fetchone()
                return res[0] if res else 0.0
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return 0.0

    def _update_balance(self, amount_change: float) -> None:
        """Update portfolio balance."""
        try:
            if self.is_postgres:
                stmt = update(portfolio_table).where(portfolio_table.c.id == "main").values(
                    current_balance=portfolio_table.c.current_balance + amount_change,
                    updated_at=pd.Timestamp.utcnow()
                )
                self.conn.execute(stmt)
                self.conn.commit()
            else:
                self.conn.execute(
                    "UPDATE portfolio_state SET current_balance = current_balance + ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                    [amount_change]
                )
        except Exception as e:
            logger.error(f"Failed to update balance: {e}")

    def open_position(self, signal: dict) -> bool:
        """Open a new paper trade based on a signal."""
        from src.config import StrategyConfig
        strat_config = StrategyConfig()
        
        symbol = signal["symbol"]
        tf = signal["timeframe"]
        side = signal["signal"].upper() # LONG/SHORT
        price = float(signal.get("price", 0.0) or signal.get("close_price", 0.0) or signal.get("last_price", 0.0) or 0.0) # Ensure float
        if price == 0.0:
            price = float(signal.get("current_price", 1.0))
        
        atr = float(signal.get("atr", 0.0))
        tp = float(signal["tp"])
        sl = float(signal["sl"])
        
        ltf_hurst = signal.get("hurst_value", 0.0)
        htf_hurst = signal.get("htf_hurst_value")
        veto_z = signal.get("atr_zscore", 0.0)

        balance = self._get_balance()
        
        # Position Sizing Logic (Refined Crypto Formula)
        if self.config.use_dynamic_sizing and atr > 0:
            # Risk Amount ($) = Account Equity * Risk_Per_Trade %
            # Distance to Stop ($) = N * ATR
            # Position Size (Units) = Risk Amount ($) / Distance to Stop ($)
            risk_amount = balance * strat_config.risk_per_trade
            distance_to_stop = strat_config.trailing_atr_multiplier * atr
            quantity = risk_amount / distance_to_stop
            logger.info(f"Dynamic Sizing: Risking ${risk_amount:.2f} with {strat_config.trailing_atr_multiplier}xATR stop. Qty: {quantity:.4f}")
        else:
            if balance < self.config.fixed_position_size:
                logger.warning(f"Insufficient balance ({balance}) to open trade for {symbol}")
                return False
            quantity = self.config.fixed_position_size / price

        # Check if already open
        if self._is_position_open(symbol, tf):
            return False
            
        # Check Portfolio Exposure Cap
        if self._get_open_trades_count() >= strat_config.max_concurrent_trades:
            logger.warning(f"Portfolio exposure cap reached ({strat_config.max_concurrent_trades} trades). Rejecting {symbol} signal.")
            return False

        try:
            if self.is_postgres:
                import uuid
                trade_id = str(uuid.uuid4())
                stmt = insert(trades_table).values(
                    id=trade_id,
                    symbol=symbol,
                    timeframe=tf,
                    side=side,
                    entry_price=price,
                    quantity=quantity,
                    tp=tp,
                    sl=sl,
                    status="OPEN",
                    ltf_hurst=ltf_hurst,
                    htf_hurst=htf_hurst,
                    veto_z=veto_z,
                    highest_price=price,
                    lowest_price=price,
                    is_breakeven=False,
                    entry_time=pd.Timestamp.utcnow()
                )
                self.conn.execute(stmt)
                self.conn.commit()
            else:
                # DuckDB
                self.conn.execute("""
                    INSERT INTO paper_trades (id, symbol, timeframe, side, entry_price, quantity, tp, sl, status, ltf_hurst, htf_hurst, veto_z, highest_price, lowest_price, is_breakeven, entry_time)
                    VALUES (nextval('seq_paper_trades_id'), ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, FALSE, CURRENT_TIMESTAMP)
                """, [symbol, tf, side, price, quantity, tp, sl, ltf_hurst, htf_hurst, veto_z, price, price])
            
            logger.info(f"Opened {side} trade: {symbol} @ {price} (Qty: {quantity:.4f})")
            
            # Deduct used capital (approximate for paper tracking)
            # In paper trading, we usually track 'invested market value' rather than deducting from cash,
            # but for consistency with existing code:
            self._update_balance(-(quantity * price))
            
            return True

        except Exception as e:
            logger.error(f"Failed to open position: {e}")
            return False

    def _is_position_open(self, symbol: str, timeframe: str) -> bool:
        """Check if an open position exists for this symbol/timeframe."""
        try:
            if self.is_postgres:
                stmt = select(trades_table.c.id).where(
                    trades_table.c.symbol == symbol,
                    trades_table.c.timeframe == timeframe,
                    trades_table.c.status == "OPEN"
                )
                return bool(self.conn.scalar(stmt))
            else:
                res = self.conn.execute(
                    "SELECT 1 FROM paper_trades WHERE symbol = ? AND timeframe = ? AND status = 'OPEN'",
                    [symbol, timeframe]
                ).fetchone()
                return bool(res)
        except Exception:
            return False

    def _get_open_trades_count(self) -> int:
        """Get the total number of currently open trades in the portfolio."""
        try:
            if self.is_postgres:
                from sqlalchemy import func
                stmt = select(func.count()).select_from(trades_table).where(trades_table.c.status == "OPEN")
                return self.conn.scalar(stmt) or 0
            else:
                res = self.conn.execute("SELECT COUNT(*) FROM paper_trades WHERE status = 'OPEN'").fetchone()
                return res[0] if res else 0
        except Exception as e:
            logger.error(f"Failed to count open trades: {e}")
            return 0

    def monitor_positions(self, current_data: dict[str, float]) -> None:
        """Check open positions against current prices (TP/SL logic)."""
        from src.config import StrategyConfig
        from src.data_loader import query_ohlcv
        from src.signals.filters import calculate_atr_scalar
        
        strat_config = StrategyConfig()
        
        try:
            # Fetch open trades
            if self.is_postgres:
                query = select(trades_table).where(trades_table.c.status == "OPEN")
                trades = pd.read_sql(query, self.conn)
            else:
                trades = self.conn.execute("SELECT * FROM paper_trades WHERE status = 'OPEN'").fetchdf()

            if trades.empty:
                return

            for _, trade in trades.iterrows():
                symbol = trade["symbol"]
                tf = trade["timeframe"]
                if symbol not in current_data:
                    continue

                curr_price = current_data[symbol]
                side = trade["side"]
                tp = trade["tp"]
                sl = trade["sl"]
                qty = trade["quantity"]
                entry = trade["entry_price"]
                trade_id = trade["id"]
                
                highest_price = trade.get("highest_price", entry)
                lowest_price = trade.get("lowest_price", entry)
                is_breakeven = trade.get("is_breakeven", False)

                exit_price = None
                pnl = 0.0
                reason = ""
                
                # Dynamic ATR Recalculation for Trailing Stop
                # Fetch recent candles to calculate fresh ATR
                df_recent = query_ohlcv(self.conn, symbol, tf, limit=30)
                current_atr = calculate_atr_scalar(df_recent) if not df_recent.empty else 0.0

                # 1. Update Extremes and Check Trailing / Breakeven logic
                if side == "LONG":
                    if curr_price > highest_price:
                        highest_price = curr_price
                    
                    # Breakeven Ratchet
                    if not is_breakeven and current_atr > 0:
                        if curr_price >= entry + (current_atr * strat_config.breakeven_atr_threshold):
                            # Entry + 0.2% to cover fees
                            be_level = entry * 1.002
                            if be_level > sl:
                                sl = be_level
                                is_breakeven = True
                                logger.info(f"LONG {symbol} hit breakeven threshold. Stop ratcheted to {sl:.2f}")
                    
                    # Trailing Stop Update
                    if current_atr > 0:
                        new_trailing_sl = highest_price - (current_atr * strat_config.trailing_atr_multiplier)
                        if new_trailing_sl > sl:
                            sl = new_trailing_sl
                            logger.debug(f"LONG {symbol} trailing stop ratcheted to {sl:.2f}")

                    # Exit Check
                    if curr_price >= tp:
                        exit_price = curr_price
                        reason = "TP"
                    elif curr_price <= sl:
                        exit_price = curr_price
                        reason = "SL/Trailing"
                        
                elif side == "SHORT":
                    if curr_price < lowest_price:
                        lowest_price = curr_price
                        
                    # Breakeven Ratchet
                    if not is_breakeven and current_atr > 0:
                        if curr_price <= entry - (current_atr * strat_config.breakeven_atr_threshold):
                            # Entry - 0.2% to cover fees
                            be_level = entry * 0.998
                            if be_level < sl:
                                sl = be_level
                                is_breakeven = True
                                logger.info(f"SHORT {symbol} hit breakeven threshold. Stop ratcheted to {sl:.2f}")
                            
                    # Trailing Stop Update
                    if current_atr > 0:
                        new_trailing_sl = lowest_price + (current_atr * strat_config.trailing_atr_multiplier)
                        if new_trailing_sl < sl:
                            sl = new_trailing_sl
                            logger.debug(f"SHORT {symbol} trailing stop ratcheted to {sl:.2f}")

                    # Exit Check
                    if curr_price <= tp:
                        exit_price = curr_price
                        reason = "TP"
                    elif curr_price >= sl:
                        exit_price = curr_price
                        reason = "SL/Trailing"

                if exit_price:
                    # Calculate PnL
                    if side == "LONG":
                        pnl = (exit_price - entry) * qty
                    else:
                        pnl = (entry - exit_price) * qty

                    self._close_trade(trade_id, exit_price, pnl, reason)
                else:
                    # Update SL and extremes in database
                    self._update_trade_state(trade_id, sl, highest_price, lowest_price, is_breakeven)

        except Exception as e:
            logger.error(f"Failed to monitor positions: {e}")

    def _update_trade_state(self, trade_id: Union[str, int], sl: float, highest: float, lowest: float, is_be: bool) -> None:
        """Update running trade state (SL, extremes, breakeven flag)."""
        try:
            if self.is_postgres:
                stmt = update(trades_table).where(trades_table.c.id == trade_id).values(
                    sl=sl,
                    highest_price=highest,
                    lowest_price=lowest,
                    is_breakeven=is_be
                )
                self.conn.execute(stmt)
                self.conn.commit()
            else:
                self.conn.execute(
                    "UPDATE paper_trades SET sl = ?, highest_price = ?, lowest_price = ?, is_breakeven = ? WHERE id = ?",
                    [sl, highest, lowest, 1 if is_be else 0, trade_id]
                )
        except Exception as e:
            logger.error(f"Failed to update trade state {trade_id}: {e}")

    def _close_trade(self, trade_id: Union[str, int], price: float, pnl: float, reason: str) -> None:
        """Execute trade closing."""
        try:
            # Fetch trade details to get quantity and entry_price for capital return
            if self.is_postgres:
                stmt = select(trades_table).where(trades_table.c.id == trade_id)
                trade = self.conn.execute(stmt).first()
                qty = float(trade.quantity)
                entry = float(trade.entry_price)
            else:
                trade = self.conn.execute("SELECT quantity, entry_price FROM paper_trades WHERE id = ?", [trade_id]).fetchone()
                qty = float(trade[0])
                entry = float(trade[1])
            
            used_capital = qty * entry
            logger.info(f"Closing trade {trade_id} ({reason}) @ {price} | PnL: {pnl:.2f}")
            
            if self.is_postgres:
                stmt = update(trades_table).where(trades_table.c.id == trade_id).values(
                    status="CLOSED",
                    exit_price=price,
                    pnl=pnl,
                    exit_time=pd.Timestamp.utcnow()
                )
                self.conn.execute(stmt)
                self.conn.commit()
            else:
                self.conn.execute(
                    "UPDATE paper_trades SET status = 'CLOSED', exit_price = ?, pnl = ?, exit_time = CURRENT_TIMESTAMP WHERE id = ?",
                    [price, pnl, trade_id]
                )
            
            # Update Portfolio Balance (Return actual used capital + PnL)
            self._update_balance(used_capital + pnl)

        except Exception as e:
            logger.error(f"Failed to close trade {trade_id}: {e}")
