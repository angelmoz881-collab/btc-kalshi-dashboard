import time
from datetime import datetime, timezone
import requests
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="BTC × Kalshi Scalp Desk", page_icon="₿", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
.stApp {background: #0b1220; color: #e7edf8;}
.block-container {padding-top: 1.1rem; max-width: 1500px; padding-left: 1rem; padding-right: 1rem;}
[data-testid="stMetric"] {background: #121d30; padding: 12px 15px; border: 1px solid #24324a; border-radius: 12px;}
[data-testid="stMetricLabel"] {color: #a8b8d3;}
div[data-testid="stTabs"] button {font-weight: 600;}
@media (max-width: 600px) {.block-container {padding-left: .5rem; padding-right: .5rem;} h1 {font-size: 1.65rem !important;}}
</style>""", unsafe_allow_html=True)
st.title("₿ BTC · Kalshi Trading Desk")
st.caption("15-minute BTC contract research dashboard • signal-only • no automatic trading")

COINBASE = "https://api.exchange.coinbase.com"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
HEADERS = {"User-Agent": "BTC-Kalshi-Scalp-Desk/1.0", "Accept": "application/json"}

@st.cache_data(ttl=10)
def get_candles(granularity=60):
    # Coinbase candle rows: [time, low, high, open, close, volume]
    r = requests.get(
        f"{COINBASE}/products/BTC-USD/candles",
        params={"granularity": granularity},
        headers=HEADERS, timeout=12
    )
    r.raise_for_status()
    rows = r.json()
    df = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.sort_values("time").reset_index(drop=True)

@st.cache_data(ttl=8)
def get_market(ticker):
    r = requests.get(f"{KALSHI}/markets/{ticker}", headers=HEADERS, timeout=12)
    r.raise_for_status()
    j = r.json()
    return j.get("market", j)

@st.cache_data(ttl=5)
def get_orderbook(ticker):
    r = requests.get(f"{KALSHI}/markets/{ticker}/orderbook", headers=HEADERS, timeout=12)
    r.raise_for_status()
    j = r.json()
    return j.get("orderbook", j)


@st.cache_data(ttl=12)
def discover_btc_15m_markets():
    """Fetch open KXBTC15M markets and prioritize the nearest future close."""
    found = []
    cursor = None
    now = datetime.now(timezone.utc)
    for _ in range(5):
        params = {"series_ticker": "KXBTC15M", "status": "open", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        response = requests.get(f"{KALSHI}/markets", params=params, headers=HEADERS, timeout=12)
        response.raise_for_status()
        payload = response.json()
        found.extend(payload.get("markets", []))
        cursor = payload.get("cursor")
        if not cursor:
            break

    def seconds_to_close(market):
        try:
            dt = datetime.fromisoformat(str(market.get("close_time", "")).replace("Z", "+00:00"))
            return (dt - now).total_seconds()
        except (ValueError, TypeError):
            return -1

    unique = {m["ticker"]: m for m in found if m.get("ticker") and seconds_to_close(m) > 0}
    return sorted(unique.values(), key=seconds_to_close)

def cents(value):
    if value is None:
        return None
    try:
        x = float(value)
        return x * 100 if x <= 1 else x
    except (ValueError, TypeError):
        return None

def levels(book, side):
    arr = book.get(side, []) or []
    out = []
    for row in arr:
        if isinstance(row, dict):
            price = row.get("price", row.get("price_dollars"))
            qty = row.get("quantity", row.get("count", row.get("size", 0)))
        else:
            price, qty = row[0], row[1]
        try:
            p = float(price)
            # Kalshi newer endpoints may provide dollar strings; older ones cents.
            if p <= 1:
                p *= 100
            out.append((p, float(qty)))
        except (ValueError, TypeError):
            pass
    return out

def safe_float(x):
    try: return float(x)
    except (ValueError, TypeError): return np.nan

with st.sidebar:
    st.header("Settings")
    st.caption("Automatically searches Kalshi for open BTC 15-minute markets; refreshes discovery every 12 seconds.")
    try:
        discovered_markets = discover_btc_15m_markets()
    except Exception as e:
        discovered_markets = []
        st.warning(f"Automatic market discovery failed: {e}")
    market_options = {
        f"{m.get('title') or m.get('subtitle') or m['ticker']} · {m['ticker']}": m["ticker"]
        for m in discovered_markets if m.get("ticker")
    }
    if market_options:
        selected_label = st.selectbox("Detected open BTC 15-minute market", list(market_options.keys()), index=0)
        market_ticker = market_options[selected_label]
        st.success(f"Selected ticker: {market_ticker}")
        st.caption("The nearest-closing active contract is selected by default on every refresh. You can select another open contract if needed.")
    else:
        st.info("No matching open BTC 15-minute markets were found automatically. You can enter a ticker manually below.")
        market_ticker = ""
    manual_ticker = st.text_input(
        "Or enter ticker manually",
        placeholder="KX...-...",
        help="Optional fallback if automatic discovery does not find the market."
    ).strip().upper()
    if manual_ticker:
        market_ticker = manual_ticker
    refresh = st.checkbox("Auto-refresh page every 15 seconds (resets chart view)", value=False)
    st.markdown("---")
    st.markdown("**Signal controls**")
    min_edge = st.slider("Minimum model edge (percentage points)", 1, 20, 5)
    st.caption("Signals are research estimates, not guaranteed predictions. Confirm market rules, expiry and fees.")

if refresh:
    st.markdown("<meta http-equiv='refresh' content='15'>", unsafe_allow_html=True)

try:
    candles = get_candles(60)
    if len(candles) < 10:
        st.error("Not enough Coinbase candle data returned.")
        st.stop()
except Exception as e:
    st.error(f"Could not load Coinbase market data: {e}")
    st.info("Check your internet connection or try again. Coinbase public market data is used; no API key is needed.")
    st.stop()

last = candles.iloc[-1]
prev = candles.iloc[-2]
price = float(last["close"])
ret1 = (price / float(candles.iloc[-2]["close"]) - 1) * 100
ret5 = (price / float(candles.iloc[-6]["close"]) - 1) * 100 if len(candles) >= 6 else np.nan
ret15 = (price / float(candles.iloc[-16]["close"]) - 1) * 100 if len(candles) >= 16 else np.nan
returns = candles["close"].pct_change().dropna()
vol15 = float(returns.tail(15).std() * np.sqrt(15) * 100) if len(returns) >= 15 else np.nan
ema_fast = candles["close"].ewm(span=5, adjust=False).mean().iloc[-1]
ema_slow = candles["close"].ewm(span=15, adjust=False).mean().iloc[-1]
trend = "BULLISH" if ema_fast > ema_slow else "BEARISH" if ema_fast < ema_slow else "MIXED"

st.subheader("Live BTC metrics")
st.metric("BTC-USD", f"${price:,.2f}", f"{ret1:+.3f}% / 1m")
m1, m2 = st.columns(2)
m1.metric("5-minute move", f"{ret5:+.3f}%" if pd.notna(ret5) else "—")
m2.metric("15-minute move", f"{ret15:+.3f}%" if pd.notna(ret15) else "—")
m3, m4 = st.columns(2)
m3.metric("EMA trend", trend)
m4.metric("15m realized vol*", f"{vol15:.3f}%" if pd.notna(vol15) else "—")
st.caption("*Approximate realized volatility from recent 1-minute returns; not a forecast.")

tab1, tab2, tab3 = st.tabs(["Live dashboard", "Kalshi order flow", "How to interpret"])

with tab1:
    st.markdown("#### BTC / USD · Interactive price chart")
    window = st.radio("Visible history", ["15m", "30m", "1h", "3h", "6h"], index=2, horizontal=True,
                      help="Tap a time window to zoom directly to that period. You can also pinch or drag on the chart.")
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        show_ema = st.toggle("EMA lines", value=True)
    with c2:
        show_volume = st.toggle("Volume", value=False)
    with c3:
        chart_style = st.selectbox("Chart", ["Candles", "Line"], label_visibility="collapsed")
    minutes = {"15m": 15, "30m": 30, "1h": 60, "3h": 180, "6h": 360}[window]
    view = candles.tail(minutes + 1).copy()
    fig = go.Figure()
    if chart_style == "Candles":
        fig.add_trace(go.Candlestick(x=view["time"], open=view["open"], high=view["high"],
                                    low=view["low"], close=view["close"], name="BTC",
                                    increasing_line_color="#21c997", decreasing_line_color="#ff647c",
                                    increasing_fillcolor="#21c997", decreasing_fillcolor="#ff647c"))
    else:
        fig.add_trace(go.Scatter(x=view["time"], y=view["close"], name="BTC",
                                 line=dict(color="#60a5fa", width=2.5), mode="lines"))
    if show_ema:
        fig.add_trace(go.Scatter(x=view["time"], y=view["close"].ewm(span=5, adjust=False).mean(),
                                 mode="lines", name="EMA 5", line=dict(color="#fbbf24", width=1.5)))
        fig.add_trace(go.Scatter(x=view["time"], y=view["close"].ewm(span=15, adjust=False).mean(),
                                 mode="lines", name="EMA 15", line=dict(color="#a78bfa", width=1.5)))
    if show_volume:
        fig.add_trace(go.Bar(x=view["time"], y=view["volume"], name="Volume", yaxis="y2",
                             marker_color="rgba(100,160,230,.35)", opacity=.45))
    fig.update_layout(
        height=530, template="plotly_dark", paper_bgcolor="#0e192a", plot_bgcolor="#0e192a",
        font=dict(color="#dbe6f6", size=13), margin=dict(l=4, r=6, t=24, b=8),
        dragmode="pan", hovermode="x unified", uirevision="btc-chart",
        xaxis=dict(showgrid=True, gridcolor="#25344b", rangeslider=dict(visible=False),
                   showspikes=True, spikemode="across", spikesnap="cursor"),
        yaxis=dict(side="right", showgrid=True, gridcolor="#25344b", tickprefix="$", tickformat=",.0f",
                   fixedrange=False, automargin=True),
        yaxis2=dict(overlaying="y", side="left", visible=False, rangemode="tozero"),
        legend=dict(orientation="h", y=1.08, x=0),
    )
    st.plotly_chart(fig, use_container_width=True, config={
        "scrollZoom": True, "displaylogo": False, "responsive": True,
        "modeBarButtonsToRemove": ["lasso2d", "select2d"],
        "doubleClick": "reset+autosize", "displayModeBar": True,
    })
    st.caption("**Chart controls:** Drag to pan · pinch with two fingers to zoom · double-tap to reset. Use the 15m–6h buttons for instant zoom. Turn off page auto-refresh in Settings while inspecting candles.")
    st.subheader("Scalp context")
    direction_score = np.clip((ret5 if pd.notna(ret5) else 0) * 18 + (ret15 if pd.notna(ret15) else 0) * 5, -100, 100)
    if abs(direction_score) < 8:
        context = "NO CLEAR EDGE — wait for confirmation"
    elif direction_score > 0:
        context = "UPSIDE MOMENTUM — only consider a long after checking Kalshi price and spread"
    else:
        context = "DOWNSIDE MOMENTUM — only consider a short/downside thesis after checking Kalshi price and spread"
    st.info(context)
    st.write(f"Momentum composite (heuristic): **{direction_score:+.1f}/100**. This is not a calibrated probability.")
    st.dataframe(candles.tail(10).sort_values("time", ascending=False), use_container_width=True, hide_index=True)

with tab2:
    if not market_ticker:
        st.warning("No open BTC 15-minute market was detected. Check the sidebar or enter a ticker manually.")
        st.write("Open the Kalshi contract page and copy its market ticker. This avoids silently analyzing the wrong expiry or strike.")
    else:
        try:
            market = get_market(market_ticker)
            book = get_orderbook(market_ticker)
            st.subheader(str(market.get("title", market.get("subtitle", market_ticker))))
            status = market.get("status", "unknown")
            close_time = market.get("close_time", market.get("expiration_time", "unknown"))
            strike = market.get("floor_strike", market.get("cap_strike", market.get("strike_price", "not provided")))
            a,b,c = st.columns(3)
            a.metric("Market status", str(status))
            b.metric("Close / expiry", str(close_time))
            c.metric("Strike field", str(strike))
            yes = levels(book, "yes")
            no = levels(book, "no")
            yes_depth = sum(q for p,q in yes)
            no_depth = sum(q for p,q in no)
            total = yes_depth + no_depth
            imbalance = ((yes_depth - no_depth) / total * 100) if total else np.nan
            x,y,z = st.columns(3)
            x.metric("YES visible depth", f"{yes_depth:,.0f}")
            y.metric("NO visible depth", f"{no_depth:,.0f}")
            z.metric("Book depth imbalance", f"{imbalance:+.1f}%" if pd.notna(imbalance) else "Unavailable")
            if yes and no:
                best_yes_bid = max(p for p,q in yes)
                best_no_bid = max(p for p,q in no)
                st.write(f"Best YES bid: **{best_yes_bid:.1f}¢** · Best NO bid: **{best_no_bid:.1f}¢**")
                st.caption("Kalshi YES/NO bids are not a direct spot-price forecast. Spread/asks may need to be inferred from the complementary side; verify current market mechanics.")
            st.markdown("#### Visible order-book levels")
            lcol, rcol = st.columns(2)
            with lcol:
                st.markdown("**YES bids**")
                st.dataframe(pd.DataFrame(yes, columns=["Price (¢)", "Quantity"]).sort_values("Price (¢)", ascending=False).head(15), use_container_width=True, hide_index=True)
            with rcol:
                st.markdown("**NO bids**")
                st.dataframe(pd.DataFrame(no, columns=["Price (¢)", "Quantity"]).sort_values("Price (¢)", ascending=False).head(15), use_container_width=True, hide_index=True)
            st.subheader("Decision checklist")
            if abs(direction_score) < 8:
                st.warning("NO TRADE bias: BTC momentum is weak or mixed.")
            elif pd.notna(imbalance) and np.sign(direction_score) == np.sign(imbalance) and abs(imbalance) >= min_edge:
                st.success("Momentum and displayed depth point the same way. Treat as a candidate only; verify spread, expiry, trade flow and fees.")
            else:
                st.warning("Signals disagree or depth imbalance is not strong enough. Avoid forcing a trade.")
            st.caption("Displayed depth can be canceled or spoofed and does not show all hidden liquidity. This prototype does not ingest full tick-by-tick trade flow.")
        except Exception as e:
            st.error(f"Could not load that Kalshi market: {e}")
            st.info("Check the ticker and whether the market is available through Kalshi's public market-data API.")

with tab3:
    st.markdown("""
**What this version does**
- Pulls recent BTC-USD 1-minute candles from Coinbase public market data.
- Calculates short-term returns, EMA trend and a simple momentum heuristic.
- Pulls a Kalshi market and its visible YES/NO order book when you provide the exact ticker.
- Shows a cautious candidate/no-trade checklist.

**What it does not claim**
- It does not know the exact final BTC price.
- It does not calculate a statistically validated probability of finishing above/below a strike.
- It does not use private order flow, hidden liquidity or every trade print.
- It does not place orders.

**For a proper model:** save timestamped BTC and Kalshi snapshots, collect realized outcomes, then backtest with walk-forward validation, fees, spread, slippage and calibration. A signal should be promoted only if out-of-sample performance supports it.
""")
st.caption(f"Last dashboard update: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} • Data may be delayed.")
