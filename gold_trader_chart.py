import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def _safe_float(value):
    try:
        x = float(value)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def render_gold_trader_chart(candles, strike=None, current_ref=None):
    """Render a trader-style Gold chart from one-minute GC=F candles."""
    if candles is None or candles.empty:
        st.info("No Gold candle data available yet.")
        return

    chart = candles.tail(120).copy()
    chart["time"] = pd.to_datetime(chart["time"], utc=True)
    chart["ema5"] = chart["close"].ewm(span=5, adjust=False).mean()
    chart["ema15"] = chart["close"].ewm(span=15, adjust=False).mean()
    chart["mom3"] = chart["close"].pct_change(3) * 100.0

    delta = chart["close"].diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=5).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=5).mean()
    rs = gain / loss.replace(0, np.nan)
    chart["rsi14"] = 100.0 - (100.0 / (1.0 + rs))

    chart["bull_cross"] = (
        (chart["ema5"] > chart["ema15"])
        & (chart["ema5"].shift(1) <= chart["ema15"].shift(1))
        & (chart["mom3"] > 0)
    )
    chart["bear_cross"] = (
        (chart["ema5"] < chart["ema15"])
        & (chart["ema5"].shift(1) >= chart["ema15"].shift(1))
        & (chart["mom3"] < 0)
    )
    chart["bull_reversal"] = (
        (chart["close"] > chart["open"])
        & (chart["low"] <= chart["low"].rolling(5, min_periods=3).min())
        & (chart["rsi14"] < 45)
        & (chart["mom3"].diff() > 0)
    )
    chart["bear_reversal"] = (
        (chart["close"] < chart["open"])
        & (chart["high"] >= chart["high"].rolling(5, min_periods=3).max())
        & (chart["rsi14"] > 55)
        & (chart["mom3"].diff() < 0)
    )

    st.markdown("### Gold trader chart")
    st.caption("1-minute GC=F candles · EMA 5/15 · Kalshi strike · momentum · heuristic trend/reversal markers")

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.74, 0.26],
    )

    fig.add_trace(
        go.Candlestick(
            x=chart["time"],
            open=chart["open"],
            high=chart["high"],
            low=chart["low"],
            close=chart["close"],
            name="GC=F 1m",
            increasing_line_color="#22c55e",
            decreasing_line_color="#ef4444",
            increasing_fillcolor="#22c55e",
            decreasing_fillcolor="#ef4444",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=chart["time"],
            y=chart["ema5"],
            mode="lines",
            name="EMA 5",
            line=dict(color="#facc15", width=2),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=chart["time"],
            y=chart["ema15"],
            mode="lines",
            name="EMA 15",
            line=dict(color="#38bdf8", width=2),
        ),
        row=1,
        col=1,
    )

    bull_cross = chart[chart["bull_cross"]]
    bear_cross = chart[chart["bear_cross"]]
    bull_rev = chart[chart["bull_reversal"]]
    bear_rev = chart[chart["bear_reversal"]]

    if not bull_cross.empty:
        fig.add_trace(
            go.Scatter(
                x=bull_cross["time"],
                y=bull_cross["low"],
                mode="markers",
                name="Bull cross",
                marker=dict(symbol="triangle-up", size=11, color="#22c55e"),
                hovertemplate="Bull EMA cross<extra></extra>",
            ),
            row=1,
            col=1,
        )
    if not bear_cross.empty:
        fig.add_trace(
            go.Scatter(
                x=bear_cross["time"],
                y=bear_cross["high"],
                mode="markers",
                name="Bear cross",
                marker=dict(symbol="triangle-down", size=11, color="#ef4444"),
                hovertemplate="Bear EMA cross<extra></extra>",
            ),
            row=1,
            col=1,
        )
    if not bull_rev.empty:
        fig.add_trace(
            go.Scatter(
                x=bull_rev["time"],
                y=bull_rev["low"],
                mode="markers",
                name="Bull reversal",
                marker=dict(symbol="star", size=10, color="#a3e635"),
                hovertemplate="Possible bullish reversal<extra></extra>",
            ),
            row=1,
            col=1,
        )
    if not bear_rev.empty:
        fig.add_trace(
            go.Scatter(
                x=bear_rev["time"],
                y=bear_rev["high"],
                mode="markers",
                name="Bear reversal",
                marker=dict(symbol="star", size=10, color="#fb7185"),
                hovertemplate="Possible bearish reversal<extra></extra>",
            ),
            row=1,
            col=1,
        )

    momentum_colors = np.where(chart["mom3"].fillna(0) >= 0, "#22c55e", "#ef4444")
    fig.add_trace(
        go.Bar(
            x=chart["time"],
            y=chart["mom3"],
            name="3m momentum %",
            marker_color=momentum_colors,
            opacity=0.72,
            hovertemplate="%{y:.3f}%<extra>3m momentum</extra>",
        ),
        row=2,
        col=1,
    )
    fig.add_hline(y=0, line_width=1, line_dash="dot", line_color="#64748b", row=2, col=1)

    recent_low = float(chart["low"].min())
    recent_high = float(chart["high"].max())
    latest_close = float(chart["close"].iloc[-1])
    price_span = max(recent_high - recent_low, max(abs(latest_close) * 0.0008, 0.5))
    pad = price_span * 0.12
    y_min = recent_low - pad
    y_max = recent_high + pad

    strike_value = _safe_float(strike)
    current_value = _safe_float(current_ref)

    # Always keep the Kalshi strike visible. This was previously only drawn when
    # the strike already happened to fall inside the candle auto-range.
    if strike_value is not None:
        range_pad = max(price_span * 0.10, abs(strike_value) * 0.00015, 0.25)
        y_min = min(y_min, strike_value - range_pad)
        y_max = max(y_max, strike_value + range_pad)
        fig.add_hline(
            y=strike_value,
            line_width=2.4,
            line_dash="dashdot",
            line_color="#f59e0b",
            annotation_text=f"KALSHI STRIKE  {strike_value:,.2f}",
            annotation_position="top left",
            annotation_font_color="#fbbf24",
            row=1,
            col=1,
        )

    if current_value is not None:
        ref_pad = max(price_span * 0.08, abs(current_value) * 0.0001, 0.20)
        y_min = min(y_min, current_value - ref_pad)
        y_max = max(y_max, current_value + ref_pad)
        fig.add_hline(
            y=current_value,
            line_width=1.5,
            line_dash="dash",
            line_color="#c084fc",
            annotation_text=f"Gold ref {current_value:,.2f}",
            annotation_position="bottom left",
            annotation_font_color="#d8b4fe",
            row=1,
            col=1,
        )

    fig.update_yaxes(range=[y_min, y_max], fixedrange=False, row=1, col=1, title_text="Gold")
    fig.update_yaxes(title_text="3m %", zeroline=False, row=2, col=1)
    fig.update_xaxes(rangeslider_visible=False, showspikes=True, spikemode="across", spikesnap="cursor")
    fig.update_layout(
        height=540,
        template="plotly_dark",
        hovermode="x unified",
        dragmode="pan",
        margin=dict(l=8, r=8, t=14, b=8),
        legend=dict(orientation="h", y=1.02, x=0, font=dict(size=10)),
        uirevision="gold-trader-chart-v2-strike",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"displayModeBar": False, "scrollZoom": True},
    )

    last_mom = _safe_float(chart["mom3"].iloc[-1])
    last_rsi = _safe_float(chart["rsi14"].iloc[-1])
    strike_distance = None
    if strike_value is not None:
        strike_reference = current_value if current_value is not None else latest_close
        strike_distance = strike_reference - strike_value

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("3m momentum", "—" if last_mom is None else f"{last_mom:+.3f}%")
    c2.metric("Chart RSI", "—" if last_rsi is None else f"{last_rsi:.1f}")
    c3.metric("EMA bias", "BULL" if chart["ema5"].iloc[-1] > chart["ema15"].iloc[-1] else "BEAR")
    c4.metric("To Kalshi strike", "—" if strike_distance is None else f"{strike_distance:+.2f}")

    if strike_value is None:
        st.caption("Kalshi strike is unavailable for the currently selected market.")

    st.caption(
        "Orange dash-dot = Kalshi strike. Purple dashed = current Gold reference. "
        "Markers are heuristic trend/reversal flags, not guaranteed trade signals. "
        "Pyth XAU/USD is used for settlement-reference distance when authenticated; "
        "GC=F remains the chart proxy."
    )
