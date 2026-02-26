"""Streamlit dashboard — scanner table, chart viewer, auto-refresh.

Story 4.1 — Dashboard layout with scanner table sorted by Hurst.
Story 4.4 — Auto-refresh with APScheduler background data refresh.

Architecture boundary: reads DuckDB + signals output as DataFrames,
NEVER writes data. APScheduler refreshes a shared cache dict in
the background; Streamlit reads from it on each rerun.

Launch: uv run streamlit run src/dashboard/app.py
"""

import time
from pathlib import Path

import pandas as pd
import streamlit as st
from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger

# Lazy imports to avoid circular deps and speed up initial load
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Background data cache — written by APScheduler, read by Streamlit
# ---------------------------------------------------------------------------
_bg_cache: dict[str, pd.DataFrame] = {}


def _refresh_scanner_data() -> None:
    """Background job: recompute scanner data and store in _bg_cache."""
    try:
        settings, *_ = _get_config()
        db_path = str(_PROJECT_ROOT / settings.duckdb_path)
        if not Path(db_path).exists():
            return
        # Bypass Streamlit cache — direct computation
        df = _compute_scanner_data(db_path)
        _bg_cache["scanner"] = df
        logger.debug(f"Background refresh complete: {len(df)} rows")
    except Exception as e:
        logger.error(f"Background refresh failed: {e}")


def _start_scheduler() -> None:
    """Start APScheduler once per Streamlit server process."""
    if "scheduler_started" not in st.session_state:
        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(_refresh_scanner_data, "interval", seconds=60, id="scanner_refresh")
        scheduler.start()
        # Trigger first refresh immediately
        _refresh_scanner_data()
        st.session_state["scheduler_started"] = True
        logger.info("APScheduler started — refreshing scanner data every 60s")


def _get_config():
    """Load config lazily."""
    from src.config import load_config
    return load_config()


def _compute_scanner_data(db_path: str) -> pd.DataFrame:
    """Compute scanner data from DB (no Streamlit cache — used by scheduler)."""
    import duckdb

    from src.signals.filters import generate_signal

    conn = duckdb.connect(db_path, read_only=True)

    try:
        pairs = conn.execute(
            "SELECT DISTINCT symbol, timeframe FROM ohlcv ORDER BY symbol, timeframe"
        ).fetchdf()

        if pairs.empty:
            return pd.DataFrame()

        rows = []
        for _, pair in pairs.iterrows():
            sym, tf = pair["symbol"], pair["timeframe"]
            df = conn.execute(
                "SELECT * FROM ohlcv WHERE symbol = ? AND timeframe = ? ORDER BY timestamp",
                [sym, tf],
            ).fetchdf()

            if df.empty or len(df) < 20:
                continue

            # Fetch HTF data (assume '1d' is HTF for MTF logic)
            df_htf = conn.execute(
                "SELECT * FROM ohlcv WHERE symbol = ? AND timeframe = '1d' ORDER BY timestamp",
                [sym],
            ).fetchdf()

            # Generate full signal dict with MTF
            sig_data = generate_signal(df, sym, tf, hurst_threshold=0.6, lowpass_cutoff=0.1, htf_df=df_htf)

            if sig_data is None:
                continue

            rows.append({
                "Symbol": sym,
                "Timeframe": tf,
                "LTF Hurst": round(sig_data["hurst_value"], 4),
                "HTF Hurst": round(sig_data["htf_hurst_value"], 4) if sig_data.get("htf_hurst_value") else None,
                "Dominant Cycle": sig_data["dominant_period"],
                "Phase": round(sig_data["current_phase"], 2),
                "Amplitude": round(sig_data["amplitude"], 2),
                "Veto Z": round(sig_data["atr_zscore"], 2),
                "Signal": sig_data["signal"].upper(),
                "Last Price": round(float(df["close_price"].iloc[-1]), 2),
            })

        return pd.DataFrame(rows)

    except Exception as e:
        logger.error(f"Scanner data load failed: {e}")
        return pd.DataFrame()
    finally:
        conn.close()


def _load_scanner_data(db_path: str) -> pd.DataFrame:
    """Return scanner data — prefers background cache, falls back to direct compute."""
    if "scanner" in _bg_cache and not _bg_cache["scanner"].empty:
        return _bg_cache["scanner"]
    # First load before scheduler has run
    return _compute_scanner_data(db_path)


@st.cache_data(ttl=60)
def _load_ohlcv(db_path: str, symbol: str, timeframe: str) -> pd.DataFrame:
    """Load OHLCV data for a specific symbol/timeframe."""
    import duckdb

    conn = duckdb.connect(db_path, read_only=True)
    try:
        df = conn.execute(
            "SELECT * FROM ohlcv WHERE symbol = ? AND timeframe = ? ORDER BY timestamp",
            [symbol, timeframe],
        ).fetchdf()
        return df
    except Exception as e:
        logger.error(f"OHLCV load failed for {symbol}/{timeframe}: {e}")
        return pd.DataFrame()
    finally:
        conn.close()


def _render_scanner(scanner_df: pd.DataFrame) -> tuple[str, str] | None:
    """Render the scanner table and return selected symbol/timeframe."""
    st.subheader("Asset Scanner")

    if scanner_df.empty:
        st.info("No data available. Run `python main.py fetch` to ingest market data.")
        return None

    # Color-code signals
    def _highlight_signal(val):
        if val == "LONG":
            return "color: #26a69a; font-weight: bold"
        elif val == "SHORT":
            return "color: #ef5350; font-weight: bold"
        return ""

    styled = scanner_df.style.map(_highlight_signal, subset=["Signal"])
    st.dataframe(styled, use_container_width=True, height=300)

    # Symbol selector
    symbols = scanner_df["Symbol"].unique().tolist()
    timeframes = scanner_df["Timeframe"].unique().tolist()

    col1, col2 = st.columns(2)
    with col1:
        selected_symbol = st.selectbox("Symbol", symbols, index=0)
    with col2:
        selected_tf = st.selectbox("Timeframe", timeframes, index=0)

    return selected_symbol, selected_tf


def _render_chart(db_path: str, symbol: str, timeframe: str) -> None:
    """Render candlestick chart with overlays for selected symbol."""
    import duckdb

    from src.dashboard.charts import create_candlestick_chart
    from src.signals.filters import generate_signal

    df = _load_ohlcv(db_path, symbol, timeframe)

    if df.empty:
        st.warning(f"No data for {symbol}/{timeframe}")
        return

    # Fetch HTF
    conn = duckdb.connect(db_path, read_only=True)
    try:
        df_htf = conn.execute(
            "SELECT * FROM ohlcv WHERE symbol = ? AND timeframe = '1d' ORDER BY timestamp",
            [symbol],
        ).fetchdf()
    finally:
        conn.close()

    # Compute signals
    sig_data = generate_signal(df, symbol, timeframe, hurst_threshold=0.6, lowpass_cutoff=0.1, htf_df=df_htf)

    signal_data = None
    if sig_data:
        signal_data = {"signal": sig_data["signal"], "current_phase": sig_data["current_phase"]}
        # Create chart
        # Wait, create_candlestick_chart might expect cycle_result
        cycle_result = {"dominant_period": sig_data["dominant_period"], "current_phase": sig_data["current_phase"], "phase_array": sig_data["phase_array"], "projection_array": sig_data["projection_array"]}
        fig = create_candlestick_chart(df, symbol, timeframe, cycle_result, signal_data)
        st.plotly_chart(fig, use_container_width=True)

        # Metrics row
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("LTF Hurst", f"{sig_data['hurst_value']:.4f}")
        with col2:
            st.metric("HTF Hurst", f"{sig_data['htf_hurst_value']:.4f}" if sig_data.get("htf_hurst_value") else "N/A")
        with col3:
            st.metric("Dominant Cycle", f"{sig_data['dominant_period']} bars")
        with col4:
            st.metric("Signal", sig_data["signal"].upper())
        with col5:
            st.metric("Veto Z-Score", f"{sig_data['atr_zscore']:.2f}")
    else:
        st.warning("Failed to generate signals for chart.")


def main():
    """Streamlit dashboard entry point."""
    st.set_page_config(
        page_title="Rabbit-Quant Dashboard",
        page_icon="chart_with_upwards_trend",
        layout="wide",
    )

    st.title("Rabbit-Quant Trading Dashboard")

    # Load config
    try:
        settings, assets, strategy, timeframes = _get_config()
        db_path = str(_PROJECT_ROOT / settings.duckdb_path)
    except Exception as e:
        st.error(f"Configuration error: {e}")
        return

    # Check if DB exists
    if not Path(db_path).exists():
        st.info("No database found. Run `python main.py fetch` to get started.")
        return

    # Start background scheduler (once per server process)
    _start_scheduler()

    # Load scanner data (from background cache or direct compute)
    start = time.perf_counter()
    scanner_df = _load_scanner_data(db_path)
    load_time = time.perf_counter() - start

    # --- Tabs ---
    tab_scanner, tab_paper = st.tabs(["Scanner", "Paper Trading"])

    with tab_scanner:
        # --- Sidebar Filters ---
        st.sidebar.header("Filters")

        # Hurst Filter
        min_hurst = st.sidebar.slider("Min Hurst", 0.5, 1.0, 0.6, 0.05)

        # Direction Filter
        directions = st.sidebar.multiselect(
            "Signal Direction", ["LONG", "SHORT", "NEUTRAL"], ["LONG", "SHORT"]
        )

        # Timeframe Filter
        all_tfs = scanner_df["Timeframe"].unique().tolist() if not scanner_df.empty else []
        selected_tfs = st.sidebar.multiselect("Timeframes", all_tfs, all_tfs)

        # Apply Filters
        if not scanner_df.empty:
            filtered_df = scanner_df[
                (scanner_df["LTF Hurst"] >= min_hurst) &
                (scanner_df["Signal"].isin(directions)) &
                (scanner_df["Timeframe"].isin(selected_tfs))
            ]
        else:
            filtered_df = scanner_df

        # --- Heatmap View ---
        if not scanner_df.empty:
            _render_heatmap(scanner_df, selected_tfs)

        # --- Detailed Scanner ---
        st.divider()
        selection = _render_scanner(filtered_df)

        if selection:
            symbol, timeframe = selection
            st.divider()
            _render_chart(db_path, symbol, timeframe)

    with tab_paper:
        _render_paper_trading(db_path)

    # Footer with refresh button
    col_foot1, col_foot2 = st.columns([4, 1])
    with col_foot1:
        st.caption(f"Data loaded in {load_time:.3f}s | Background refresh every 60s")
    with col_foot2:
        if st.button("Refresh Now"):
            _refresh_scanner_data()
            st.rerun()

    # Auto-refresh loop (Story 4.4)
    # Note: Page will show 'running' spinner while waiting for next refresh
    time.sleep(60)
    st.rerun()


def _render_paper_trading(db_path: str) -> None:
    """Render Paper Trading dashboard tab."""
    from src.config import load_config
    from src.data_loader import get_connection, reset_portfolio

    settings, _, _, _ = load_config()

    st.header("Live Paper Trading Portfolio")

    # Connect
    conn = get_connection(settings, read_only=True)

    try:
        # Fetch Balance
        if settings.use_postgres:
            balance_df = pd.read_sql("SELECT * FROM portfolio_state", conn)
            trades_df = pd.read_sql("SELECT * FROM paper_trades ORDER BY entry_time DESC", conn)
        else:
            balance_df = conn.execute("SELECT * FROM portfolio_state").fetchdf()
            trades_df = conn.execute("SELECT * FROM paper_trades ORDER BY entry_time DESC").fetchdf()

        if balance_df.empty:
            st.warning("Portfolio not initialized.")
            return

        current_bal = balance_df["current_balance"].iloc[0]
        init_bal = balance_df["initial_balance"].iloc[0]

        # Calculate Trade Metrics
        if not trades_df.empty:
            trades_df["Amount"] = trades_df["entry_price"] * trades_df["quantity"]

        # Active Stats & Live Prices
        active = trades_df[trades_df["status"] == "OPEN"].copy()
        invested_market_value = 0.0

        if not active.empty:
            current_prices = {}
            for symbol in active["symbol"].unique():
                # Fetch latest price (using same TF logic as scheduler)
                p_df = pd.read_sql(f"SELECT close_price FROM ohlcv WHERE symbol = '{symbol}' ORDER BY timestamp DESC LIMIT 1", conn)
                if not p_df.empty:
                    current_prices[symbol] = float(p_df["close_price"].iloc[0])

            active["Current Price"] = active["symbol"].map(current_prices)

            def calc_unrealized(row):
                if pd.isna(row["Current Price"]): return 0.0
                if row["side"] == "LONG":
                    return (row["Current Price"] - row["entry_price"]) * row["quantity"]
                else:
                    return (row["entry_price"] - row["Current Price"]) * row["quantity"]

            active["PnL"] = active.apply(calc_unrealized, axis=1)
            invested_market_value = (active["quantity"] * active["Current Price"]).sum()

        total_equity = current_bal + invested_market_value
        total_pnl = total_equity - init_bal
        pnl_pct = (total_pnl / init_bal) * 100

        # Metrics
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Equity", f"${total_equity:,.2f}", f"{pnl_pct:.2f}%")
        m2.metric("Available Cash", f"${current_bal:,.2f}")
        m3.metric("Position Value", f"${invested_market_value:,.2f}")

        # Active Positions
        st.subheader("Active Positions")
        if not active.empty:
            def style_pnl(val):
                color = "#26a69a" if val >= 0 else "#ef5350"
                return f"color: {color}; font-weight: bold"

            # Make sure we select the new columns if they exist
            cols_to_show = ["symbol", "side", "entry_price", "Current Price", "PnL", "tp", "sl", "ltf_hurst", "htf_hurst", "veto_z", "status", "entry_time"]
            existing_cols = [c for c in cols_to_show if c in active.columns]
            styled_active = active[existing_cols].style.map(style_pnl, subset=["PnL"])
            st.dataframe(styled_active, use_container_width=True)
        else:
            st.info("No active positions.")

        # Closed History
        st.subheader("Trade History")
        closed = trades_df[trades_df["status"] == "CLOSED"]
        if not closed.empty:
            cols_to_show_closed = ["symbol", "side", "entry_price", "exit_price", "pnl", "ltf_hurst", "htf_hurst", "veto_z", "entry_time", "exit_time"]
            existing_cols_closed = [c for c in cols_to_show_closed if c in closed.columns]
            st.dataframe(closed[existing_cols_closed], use_container_width=True)

        # Reset Button
        st.divider()
        if st.button("Reset Portfolio (Clear Data)", type="primary"):
            # Need write connection
            conn.close()
            w_conn = get_connection(settings, read_only=False)
            reset_portfolio(w_conn)
            w_conn.close()
            st.success("Portfolio reset! Refreshing...")
            time.sleep(1)
            st.rerun()

    except Exception as e:
        st.error(f"Error loading portfolio: {e}")
    finally:
        try:
            conn.close()
        except:
            pass


def _render_heatmap(df: pd.DataFrame, selected_tfs: list[str]) -> None:
    """Render a multi-timeframe confluence heatmap."""
    st.subheader("Confluence Heatmap")

    if df.empty:
        st.info("No data for heatmap.")
        return

    # Pivot: Index=Symbol, Columns=Timeframe, Values=Signal
    # We filter only by selected timeframes for the columns
    df_filtered = df[df["Timeframe"].isin(selected_tfs)]

    if df_filtered.empty:
        st.info("No data matches the timeframe filter.")
        return

    heatmap = df_filtered.pivot(index="Symbol", columns="Timeframe", values="Signal")

    # Sort columns chronologically
    TIMEFRAME_ORDER = ["15m", "1h", "4h", "1d"]

    # Get available columns that are also in our known order
    sorted_cols = [tf for tf in TIMEFRAME_ORDER if tf in heatmap.columns]

    # Append any unknown timeframes at the end (just in case)
    remaining_cols = [c for c in heatmap.columns if c not in sorted_cols]

    heatmap = heatmap[sorted_cols + remaining_cols]

    # --- Action & Score Calculation ---
    weights = {'1d': 3.0, '4h': 2.0, '1h': 1.0, '15m': 0.5}

    def calculate_action(row):
        score = 0.0
        for tf, weight in weights.items():
            if tf in row:
                val = row[tf]
                if val == "LONG":
                    score += weight
                elif val == "SHORT":
                    score -= weight

        if score >= 4.0: return "STRONG BUY", score
        if score >= 2.0: return "BUY", score
        if score <= -4.0: return "STRONG SELL", score
        if score <= -2.0: return "SELL", score
        return "WAIT", score

    # Apply calculation
    results = heatmap.apply(calculate_action, axis=1)
    heatmap.insert(0, "Action", results.apply(lambda x: x[0]))
    heatmap["Score"] = results.apply(lambda x: x[1])

    # Sort by Score Descending
    heatmap = heatmap.sort_values("Score", ascending=False)

    # Styling
    def color_signals(val):
        if val == "LONG":
            return "background-color: #26a69a; color: white; font-weight: bold"
        elif val == "SHORT":
            return "background-color: #ef5350; color: white; font-weight: bold"
        elif val == "NEUTRAL":
            return "color: gray"

        # Action Styling
        if val == "STRONG BUY":
            return "background-color: #00695c; color: white; font-weight: bold" # Dark Green
        if val == "BUY":
            return "background-color: #26a69a; color: white; font-weight: bold"
        if val == "STRONG SELL":
            return "background-color: #b71c1c; color: white; font-weight: bold" # Dark Red
        if val == "SELL":
            return "background-color: #ef5350; color: white; font-weight: bold"
        if val == "WAIT":
            return "color: gray; font-style: italic"

        return ""

    st.dataframe(
        heatmap.style.map(color_signals),
        use_container_width=True
    )


if __name__ == "__main__":
    main()
