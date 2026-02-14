"""Streamlit dashboard — scanner table, chart viewer, auto-refresh.

Story 4.1 — Dashboard layout with scanner table sorted by Hurst.
Story 4.4 — Auto-refresh with APScheduler background data refresh.

Architecture boundary: reads DuckDB + signals output as DataFrames,
NEVER writes data. Uses in-memory cache with TTL.

Launch: uv run streamlit run src/dashboard/app.py
"""

import time
from pathlib import Path

import pandas as pd
import streamlit as st
from loguru import logger

# Lazy imports to avoid circular deps and speed up initial load
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _get_config():
    """Load config lazily."""
    from src.config import load_config
    return load_config()


@st.cache_data(ttl=60)
def _load_scanner_data(db_path: str) -> pd.DataFrame:
    """Load scanner data: compute signals for all symbols in DB.

    Cached with 60s TTL for auto-refresh behavior.
    """
    import duckdb

    from src.signals.cycles import detect_dominant_cycle_filtered
    from src.signals.fractals import calculate_hurst

    conn = duckdb.connect(db_path, read_only=True)

    try:
        # Get unique symbol/timeframe pairs
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

            hurst = calculate_hurst(df)
            cycle = detect_dominant_cycle_filtered(df, cutoff=0.1)

            signal = "neutral"
            dominant_period = 0
            current_phase = 0.0
            amplitude = 0.0

            if cycle:
                dominant_period = cycle["dominant_period"]
                current_phase = cycle["current_phase"]
                amplitude = cycle["amplitude"]

                from src.signals.filters import _determine_signal
                signal = _determine_signal(current_phase, hurst, 0.6)

            rows.append({
                "Symbol": sym,
                "Timeframe": tf,
                "Hurst": round(hurst, 4),
                "Dominant Cycle": dominant_period,
                "Phase": round(current_phase, 2),
                "Amplitude": round(amplitude, 2),
                "Signal": signal.upper(),
                "Last Price": round(float(df["close_price"].iloc[-1]), 2),
            })

        return pd.DataFrame(rows)

    except Exception as e:
        logger.error(f"Scanner data load failed: {e}")
        return pd.DataFrame()
    finally:
        conn.close()


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

    styled = scanner_df.style.applymap(_highlight_signal, subset=["Signal"])
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
    from src.dashboard.charts import create_candlestick_chart
    from src.signals.cycles import detect_dominant_cycle_filtered
    from src.signals.filters import _determine_signal
    from src.signals.fractals import calculate_hurst

    df = _load_ohlcv(db_path, symbol, timeframe)

    if df.empty:
        st.warning(f"No data for {symbol}/{timeframe}")
        return

    # Compute signals
    cycle_result = detect_dominant_cycle_filtered(df, cutoff=0.1)
    hurst = calculate_hurst(df)

    signal_data = None
    if cycle_result:
        signal = _determine_signal(cycle_result["current_phase"], hurst, 0.6)
        signal_data = {"signal": signal, "current_phase": cycle_result["current_phase"]}

    # Create chart
    fig = create_candlestick_chart(df, symbol, timeframe, cycle_result, signal_data)
    st.plotly_chart(fig, use_container_width=True)

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Hurst", f"{hurst:.4f}")
    with col2:
        period = cycle_result["dominant_period"] if cycle_result else 0
        st.metric("Dominant Cycle", f"{period} bars")
    with col3:
        sig = signal_data["signal"].upper() if signal_data else "N/A"
        st.metric("Signal", sig)
    with col4:
        st.metric("Last Price", f"${df['close_price'].iloc[-1]:.2f}")


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

    # Load scanner data
    start = time.perf_counter()
    scanner_df = _load_scanner_data(db_path)
    load_time = time.perf_counter() - start

    # Scanner table
    selection = _render_scanner(scanner_df)

    if selection:
        symbol, timeframe = selection
        st.divider()
        _render_chart(db_path, symbol, timeframe)

    # Footer
    st.caption(f"Data loaded in {load_time:.3f}s | Auto-refreshes every 60s")

    # Auto-refresh via rerun (Story 4.4)
    time.sleep(60)
    st.rerun()


if __name__ == "__main__":
    main()
