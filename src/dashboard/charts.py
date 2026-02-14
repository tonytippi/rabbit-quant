"""Plotly chart components for the trading dashboard.

Story 4.2 — Interactive candlestick chart with zoom, pan, crosshair.
Story 4.3 — Sine wave overlay and cycle visualization.
Story 4.4 — Buy/sell signal markers.

Architecture boundary: reads DataFrames and signal dicts,
returns Plotly figures. NEVER writes data or fetches from APIs.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def create_candlestick_chart(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    cycle_result: dict | None = None,
    signal_data: dict | None = None,
) -> go.Figure:
    """Create an interactive candlestick chart with optional overlays.

    Args:
        df: OHLCV DataFrame with timestamp, open/high/low/close_price, volume.
        symbol: Asset symbol for chart title.
        timeframe: Timeframe for chart title.
        cycle_result: Optional cycle detection result dict with phase_array,
                      projection_array, amplitude, dominant_period.
        signal_data: Optional signal dict with 'signal' and 'current_phase'.

    Returns:
        Plotly Figure with candlestick chart and overlays.
    """
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.8, 0.2],
        subplot_titles=[f"{symbol} ({timeframe})", "Volume"],
    )

    # Candlestick chart
    fig.add_trace(
        go.Candlestick(
            x=df["timestamp"],
            open=df["open_price"],
            high=df["high_price"],
            low=df["low_price"],
            close=df["close_price"],
            name="OHLC",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        ),
        row=1, col=1,
    )

    # Volume bars
    colors = [
        "#26a69a" if c >= o else "#ef5350"
        for c, o in zip(df["close_price"], df["open_price"])
    ]
    fig.add_trace(
        go.Bar(
            x=df["timestamp"],
            y=df["volume"],
            name="Volume",
            marker_color=colors,
            opacity=0.5,
        ),
        row=2, col=1,
    )

    # Sine wave overlay (Story 4.3)
    if cycle_result and len(cycle_result.get("phase_array", [])) > 0:
        _add_sine_overlay(fig, df, cycle_result)

    # Signal markers (Story 4.4)
    if signal_data:
        _add_signal_markers(fig, df, signal_data)

    # Layout
    fig.update_layout(
        height=600,
        xaxis_rangeslider_visible=False,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
        template="plotly_dark",
        margin=dict(l=50, r=20, t=40, b=20),
    )

    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="rgba(128,128,128,0.2)")
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="rgba(128,128,128,0.2)")

    return fig


def _add_sine_overlay(fig: go.Figure, df: pd.DataFrame, cycle_result: dict) -> None:
    """Add sine wave overlay to candlestick chart.

    Shows historical fitted sine wave and forward projection.
    """
    phase_array = cycle_result["phase_array"]
    projection_array = cycle_result.get("projection_array", np.array([]))
    dominant_period = cycle_result.get("dominant_period", 0)

    if len(phase_array) == 0:
        return

    # Scale sine wave to price range for visual overlay
    close = df["close_price"].values
    price_mean = np.mean(close[-len(phase_array):])

    # Historical sine wave
    historical_sine = price_mean + phase_array
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"].iloc[-len(phase_array):],
            y=historical_sine,
            name=f"Cycle ({dominant_period} bars)",
            line=dict(color="#ffd54f", width=2),
            opacity=0.7,
        ),
        row=1, col=1,
    )

    # Forward projection (dashed)
    if len(projection_array) > 0:
        last_ts = df["timestamp"].iloc[-1]
        freq = _infer_freq(df["timestamp"])
        future_ts = pd.date_range(start=last_ts, periods=len(projection_array) + 1, freq=freq)[1:]

        projected_sine = price_mean + projection_array
        fig.add_trace(
            go.Scatter(
                x=future_ts,
                y=projected_sine,
                name="Projection",
                line=dict(color="#ffd54f", width=2, dash="dash"),
                opacity=0.5,
            ),
            row=1, col=1,
        )


def _add_signal_markers(fig: go.Figure, df: pd.DataFrame, signal_data: dict) -> None:
    """Add buy/sell signal markers to the chart."""
    signal = signal_data.get("signal", "neutral")
    if signal == "neutral":
        return

    # Mark the last candle with the signal
    last_idx = len(df) - 1
    last_ts = df["timestamp"].iloc[last_idx]

    if signal == "long":
        fig.add_trace(
            go.Scatter(
                x=[last_ts],
                y=[df["low_price"].iloc[last_idx]],
                mode="markers",
                marker=dict(symbol="triangle-up", size=15, color="#26a69a"),
                name="Long Signal",
            ),
            row=1, col=1,
        )
    elif signal == "short":
        fig.add_trace(
            go.Scatter(
                x=[last_ts],
                y=[df["high_price"].iloc[last_idx]],
                mode="markers",
                marker=dict(symbol="triangle-down", size=15, color="#ef5350"),
                name="Short Signal",
            ),
            row=1, col=1,
        )


def _infer_freq(timestamps: pd.Series) -> str:
    """Infer frequency from timestamp series for projection."""
    if len(timestamps) < 2:
        return "D"
    delta = timestamps.iloc[-1] - timestamps.iloc[-2]
    seconds = delta.total_seconds()
    if seconds <= 60:
        return "min"
    elif seconds <= 300:
        return "5min"
    elif seconds <= 900:
        return "15min"
    elif seconds <= 3600:
        return "h"
    elif seconds <= 14400:
        return "4h"
    else:
        return "D"
