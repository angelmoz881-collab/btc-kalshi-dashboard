import time
from datetime import datetime, timezone
import requests
import pandas as pd
import numpy as np
import streamlit as st
import json
import streamlit.components.v1 as components
import plotly.graph_objects as go

st.set_page_config(page_title="BTC × Kalshi Scalp Desk", page_icon="₿", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');
:root {color-scheme:dark}
.stApp {background:radial-gradient(ellipse at 90% -10%,rgba(33,79,125,.24),transparent 42%),linear-gradient(180deg,#08111e 0%,#0b1422 58%,#0b1422 100%);color:#e9f1fc;font-family:'DM Sans',sans-serif}
.block-container {padding-top:1.5rem;max-width:1420px;padding-left:1.5rem;padding-right:1.5rem;padding-bottom:3rem}
h1,h2,h3 {font-family:'Space Grotesk',sans-serif!important;letter-spacing:-.035em!important}
h3 {color:#dceaff!important}
p, label {color:#c2d0e4}
[data-testid="stMetric"] {background:linear-gradient(145deg,rgba(26,43,66,.95),rgba(15,28,46,.96));padding:18px 19px;border:1px solid #263a54;border-radius:17px;box-shadow:0 9px 25px rgba(0,0,0,.13);min-height:108px}
[data-testid="stMetricLabel"] {color:#94a9c4!important;font-size:.79rem!important;letter-spacing:.02em}
[data-testid="stMetricValue"] {font-family:'Space Grotesk',sans-serif;font-weight:700;letter-spacing:-.04em;font-size:clamp(1.25rem,2vw,1.85rem)!important}
[data-testid="stMetricDelta"] {font-weight:700}
[data-testid="stTabs"] {margin-top:1rem}
[data-testid="stTabs"] [role="tablist"] {gap:8px;border-bottom:1px solid #27374e}
[data-testid="stTabs"] button {font-weight:700;border-radius:10px 10px 0 0;padding:12px 17px;color:#9bb1cf}
[data-testid="stTabs"] button[aria-selected="true"] {color:#64d8d0!important;background:#13263a}
[data-testid="stSidebar"] {background:#0d1a2a;border-right:1px solid #263a54}
[data-testid="stSidebar"] h2 {color:#ecf7ff}
[data-testid="stRadio"] div[role="radiogroup"] {gap:6px;flex-wrap:wrap}
[data-testid="stRadio"] label {border:1px solid #30455f;background:#12243a;border-radius:9px;padding:4px 10px}
[data-testid="stAlert"] {border-radius:13px}
hr {border-color:#243850!important}
.hero {padding:22px 25px;border:1px solid #2a415e;border-radius:21px;background:linear-gradient(112deg,rgba(24,50,74,.92),rgba(12,28,48,.94) 60%,rgba(10,54,63,.8));margin-bottom:18px;box-shadow:0 12px 38px rgba(0,0,0,.13)}
.eyebrow {font-size:.72rem;letter-spacing:.16em;font-weight:800;color:#68d8cc;text-transform:uppercase;margin-bottom:7px}
.hero-title {font-family:'Space Grotesk',sans-serif;font-size:clamp(1.5rem,3vw,2.4rem);font-weight:700;letter-spacing:-.05em;color:#f1f7ff;line-height:1.13}
.hero-sub {color:#a6bbd2;font-size:.87rem;margin-top:8px}
.badge {display:inline-block;border:1px solid #276d6d;border-radius:20px;background:rgba(16,109,102,.2);color:#7aede0;font-weight:800;font-size:.72rem;padding:6px 11px;margin-top:13px}
.section-heading {font-size:.72rem;font-weight:800;color:#8fa6c1;letter-spacing:.14em;text-transform:uppercase;margin:20px 0 11px}
@media(max-width:650px){.block-container{padding:1rem .7rem 2rem}.hero{padding:18px 16px;border-radius:15px}[data-testid="stMetric"]{padding:12px 11px;min-height:94px}[data-testid="stMetricValue"]{font-size:1.18rem!important}[data-testid="stTabs"] button{padding:9px 7px;font-size:.78rem}}
</style>""", unsafe_allow_html=True)
st.markdown("""<div class="hero"><div class="eyebrow">Live market intelligence · Bitcoin / Kalshi</div><div class="hero-title">₿ &nbsp; BTC Scalp Terminal</div><div class="hero-sub">Price action, momentum and 15-minute prediction-market liquidity — in one focused workspace.</div><span class="badge">● RESEARCH MODE &nbsp;·&nbsp; NO AUTO-TRADING</span></div>""", unsafe_allow_html=True)

COINBASE = "https://api.exchange.coinbase.com"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
HEADERS = {"User-Agent": "BTC-Kalshi-Scalp-Desk/1.0", "Accept": "application/json"}

@st.cache_data(ttl=15)
def get_candles(granularity=60):
    """Get distinct UTC one-minute BTC candles; retry a bounded historical window."""
    def normalize(rows):
        df = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"])
        if df.empty:
            return df
        for col in ("time", "low", "high", "open", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["time", "low", "high", "open", "close"])
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        return df.drop_duplicates("time").sort_values("time").reset_index(drop=True)

    # Coinbase Exchange candles supports at most 300 buckets per request.
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = end - pd.Timedelta(minutes=299)
    params = {"granularity": granularity, "start": start.isoformat(), "end": end.isoformat()}
    response = requests.get(f"{COINBASE}/products/BTC-USD/candles",
                            params=params, headers=HEADERS, timeout=15)
    response.raise_for_status()
    df = normalize(response.json())
    if len(df) >= 30:
        return df

    # If the primary endpoint provides insufficient history, try Coinbase's
    # alternate public Advanced Trade candles feed before showing an error.
    # Kraken provides public BTC/USD minute OHLC history without credentials.
    kr = requests.get("https://api.kraken.com/0/public/OHLC",
                      params={"pair": "XBTUSD", "interval": 1}, timeout=15)
    kr.raise_for_status()
    body = kr.json()
    if body.get("error"):
        raise ValueError(f"Kraken candle API: {body['error']}")
    pairs = [v for k, v in body.get("result", {}).items() if k != "last"]
    if not pairs:
        raise ValueError("Both candle feeds returned insufficient historical data")
    # Kraken rows: [time, open, high, low, close, vwap, volume, count]
    fallback = [[row[0], row[3], row[2], row[1], row[4], row[6]] for row in pairs[0]]
    df = normalize(fallback)
    if len(df) < 30:
        raise ValueError(f"Candle feeds returned only {len(df)} distinct minutes")
    return df.tail(300).reset_index(drop=True)

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
    return j.get("orderbook_fp") or j.get("orderbook") or j


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

def quote_cents(market, side, kind):
    """Kalshi quotes: *_dollars strings or legacy integer-cent fields."""
    for key in (f"{side}_{kind}_dollars", f"{side}_{kind}"):
        value = market.get(key)
        if value is None or value == "":
            continue
        try:
            result = float(value) * (100 if key.endswith("_dollars") else 1)
            return result if 0 <= result <= 100 else None
        except (TypeError, ValueError):
            continue
    return None

def levels(book, side):
    """Parse Kalshi fixed-point orderbook_fp, dollar, and legacy bids."""
    if not isinstance(book, dict):
        return []
    # New API: orderbook_fp.yes_dollars / no_dollars, rows [price, count_fp]
    # Some responses nest orderbook_fp inside the top-level orderbook object.
    book = book.get("orderbook_fp") or book
    if book.get(f"{side}_dollars") is not None:
        rows, dollar_prices = book[f"{side}_dollars"], True
    elif book.get(side) is not None:
        rows, dollar_prices = book[side], False
    else:
        return []
    result = []
    for row in rows or []:
        if isinstance(row, dict):
            raw_price = row.get("price_dollars", row.get("price"))
            raw_qty = row.get("count_fp", row.get("quantity", row.get("count", row.get("size", 0))))
            is_dollars = dollar_prices or row.get("price_dollars") is not None
        elif isinstance(row, (list, tuple)) and len(row) >= 2:
            raw_price, raw_qty = row[:2]
            is_dollars = dollar_prices
        else:
            continue
        try:
            price = float(raw_price) * (100 if is_dollars else 1)
            qty = float(raw_qty)
            if 0 <= price <= 100 and qty > 0:
                result.append((price, qty))
        except (ValueError, TypeError):
            continue
    return sorted(result, key=lambda x: x[0], reverse=True)

def kalshi_snapshot(ticker):
    market = get_market(ticker)
    # A quote is useful even if the order-book endpoint is temporarily unavailable.
    book_error = None
    try:
        book = get_orderbook(ticker)
    except requests.RequestException as exc:
        book = {}
        book_error = str(exc)
    yes = levels(book, "yes")
    no = levels(book, "no")
    ybid = quote_cents(market, "yes", "bid")
    nbid = quote_cents(market, "no", "bid")
    if ybid is None and yes: ybid = yes[0][0]
    if nbid is None and no: nbid = no[0][0]
    yask = quote_cents(market, "yes", "ask")
    nask = quote_cents(market, "no", "ask")
    if yask is None and nbid is not None: yask = 100 - nbid
    if nask is None and ybid is not None: nask = 100 - ybid
    return dict(market=market, yes=yes, no=no, yes_bid=ybid, no_bid=nbid,
                yes_ask=yask, no_ask=nask, book_error=book_error)

def show_price(value):
    return f"{value:.1f}¢" if value is not None else "—"

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

st.markdown('<div class="section-heading">Market overview · BTC / USD</div>', unsafe_allow_html=True)
st.metric("BTC-USD", f"${price:,.2f}", f"{ret1:+.3f}% / 1m")
m1, m2 = st.columns(2)
m1.metric("5-minute move", f"{ret5:+.3f}%" if pd.notna(ret5) else "—")
m2.metric("15-minute move", f"{ret15:+.3f}%" if pd.notna(ret15) else "—")
m3, m4 = st.columns(2)
m3.metric("EMA trend", trend)
m4.metric("15m realized vol*", f"{vol15:.3f}%" if pd.notna(vol15) else "—")
st.caption("*Approximate realized volatility from recent 1-minute returns; not a forecast.")

kalshi_data = None
kalshi_error = None
if market_ticker:
    try:
        kalshi_data = kalshi_snapshot(market_ticker)
    except requests.RequestException as exc:
        kalshi_error = str(exc)

tab1, tab2, tab3 = st.tabs(["Live dashboard", "Kalshi order flow", "How to interpret"])

with tab1:
    st.markdown("#### BTC / USD · Price action")
    if market_ticker:
        st.info(f"🎯 **Kalshi market ticker: `{market_ticker}`**" +
                (f"  |  Status: **{kalshi_data['market'].get('status', 'unknown')}**" if kalshi_data else "  |  Quotes unavailable"))
    else:
        st.warning("⚠️ No Kalshi ticker selected. Open Settings to select an active BTC 15-minute contract.")
    st.caption("TradingView Lightweight Charts · drag to pan · pinch or scroll to zoom · crosshair for exact candle prices")
    timeframe = st.radio("Candle timeframe", ["1m", "5m", "15m", "30m", "1h"], index=0, horizontal=True)
    window = st.radio("Visible history", ["15m", "30m", "1h", "3h", "6h"], index=2, horizontal=True)
    c1, c2 = st.columns(2)
    with c1:
        show_ema = st.toggle("EMA 5 / 15", value=True)
    with c2:
        chart_style = st.selectbox("Chart style", ["Candles", "Line"], label_visibility="collapsed")
    minutes = {"15m": 15, "30m": 30, "1h": 60, "3h": 180, "6h": 360}[window]
    candle_minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60}[timeframe]
    # Coinbase timestamps are already UTC datetime values. Preserve those
    # timestamps, remove duplicate buckets, then resample OHLC properly.
    source = candles.copy()
    source["time"] = pd.to_datetime(source["time"], utc=True, errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        source[col] = pd.to_numeric(source[col], errors="coerce")
    source = source.dropna(subset=["time", "open", "high", "low", "close"])
    source = source.sort_values("time").drop_duplicates("time", keep="last")
    if candle_minutes > 1:
        source = (source.set_index("time")
                  .resample(f"{candle_minutes}min", label="left", closed="left")
                  .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
                  .dropna(subset=["open", "high", "low", "close"])
                  .reset_index())
    # Keep history available for panning; the initial view is set in JS.
    view = source.tail(300).copy()
    view["epoch"] = (view["time"].astype("int64") // 1_000_000_000).astype("int64")
    bars = [{"time": int(r.epoch), "open": float(r.open), "high": float(r.high),
             "low": float(r.low), "close": float(r.close)} for r in view.itertuples()]
    if not bars:
        st.error("No valid BTC candles were received. Try reloading the dashboard.")
        st.stop()
    if len(bars) < 10:
        st.warning(f"Only {len(bars)} distinct {timeframe} candles received; displaying available data.")
    line = [{"time": b["time"], "value": b["close"]} for b in bars]
    ema5 = [{"time": int(t), "value": float(v)} for t, v in zip(view["epoch"], view["close"].ewm(span=5, adjust=False).mean())]
    ema15 = [{"time": int(t), "value": float(v)} for t, v in zip(view["epoch"], view["close"].ewm(span=15, adjust=False).mean())]
    visible_count = max(2, min(len(bars), max(1, minutes // candle_minutes)))
    # Native Plotly chart: no embedded iframe or Lightweight Charts time-axis state.
    # Datetime x-values are taken directly from the validated OHLC dataframe.
    chart = go.Figure()
    if chart_style == "Candles":
        chart.add_trace(go.Candlestick(
            x=view["time"], open=view["open"], high=view["high"],
            low=view["low"], close=view["close"], name="BTC/USD",
            increasing=dict(line=dict(color="#38d6b0"), fillcolor="#38d6b0"),
            decreasing=dict(line=dict(color="#ff6d83"), fillcolor="#ff6d83"),
        ))
    else:
        chart.add_trace(go.Scatter(
            x=view["time"], y=view["close"], name="BTC/USD",
            mode="lines", line=dict(color="#60a5fa", width=2)))
    if show_ema:
        for span, color in ((5, "#fbbf24"), (15, "#a78bfa")):
            chart.add_trace(go.Scatter(
                x=view["time"], y=view["close"].ewm(span=span, adjust=False).mean(),
                name=f"EMA {span}", mode="lines", line=dict(color=color, width=1)))
    # Date ranges, unlike chart-library logical ranges, cannot collapse to one bar.
    right_edge = view["time"].iloc[-1] + pd.Timedelta(minutes=candle_minutes * 2)
    left_edge = right_edge - pd.Timedelta(minutes=max(minutes, candle_minutes * 4))
    chart.update_layout(
        height=520, margin=dict(l=8, r=8, t=12, b=15),
        paper_bgcolor="#0c1929", plot_bgcolor="#0c1929",
        font=dict(color="#c6d3e5", size=12),
        xaxis=dict(type="date", range=[left_edge, right_edge],
                   showgrid=True, gridcolor="#1b2e44",
                   rangeslider=dict(visible=False), tickformat="%H:%M"),
        yaxis=dict(side="right", showgrid=True, gridcolor="#1b2e44",
                   tickprefix="$", tickformat=",.2f", fixedrange=False),
        showlegend=show_ema, legend=dict(orientation="h", y=1.12, x=0),
        dragmode="pan", uirevision=f"{timeframe}-{window}-{chart_style}",
        hovermode="x unified",
    )
    st.plotly_chart(chart, use_container_width=True, config={
        "displaylogo": False, "scrollZoom": True, "responsive": True,
        "modeBarButtonsToRemove": ["lasso2d", "select2d"],
    })
    st.caption(f"Loaded {len(bars)} distinct {timeframe} BTC candles · UTC: "
               f"{datetime.fromtimestamp(bars[0]['time'], timezone.utc):%H:%M}–"
               f"{datetime.fromtimestamp(bars[-1]['time'], timezone.utc):%H:%M} · "
               f"Showing last {visible_count} candles initially.")
    st.caption("Drag sideways to inspect older candles. Pinch to zoom on mobile; scroll to zoom on desktop. Use the time buttons to reset your view.")
    st.markdown('<div class="section-heading">Kalshi live quotes · directly below BTC chart</div>', unsafe_allow_html=True)
    if kalshi_data:
        k = kalshi_data
        yes_col, no_col = st.columns(2)
        with yes_col:
            st.metric("🟢 YES · Buy", show_price(k["yes_ask"]))
            st.caption(f"Sell YES: {show_price(k['yes_bid'])}")
        with no_col:
            st.metric("🔴 NO · Buy", show_price(k["no_ask"]))
            st.caption(f"Sell NO: {show_price(k['no_bid'])}")
        st.caption(f"Ticker: {market_ticker} · Status: {k['market'].get('status', 'unknown')} · Expiry (UTC): {k['market'].get('close_time', 'unknown')}")
        if all(k[name] is None for name in ('yes_ask', 'no_ask', 'yes_bid', 'no_bid')):
            st.warning("No current quotes returned for this contract. A missing quote is not a zero-cent price.")
    elif kalshi_error:
        st.warning(f"Kalshi quotes unavailable: {kalshi_error}")
    else:
        st.info("No active Kalshi contract selected. Check Settings to select one.")
    st.caption("Quotes are in cents per contract, not model probabilities. Opposite-side bids may imply asks; fees and slippage are not included.")

    st.markdown('<div class="section-heading">Momentum readout</div>', unsafe_allow_html=True)
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
        st.warning("No open BTC 15-minute market selected. Check the sidebar.")
    elif kalshi_error:
        st.error(f"Kalshi market request failed: {kalshi_error}")
    elif kalshi_data:
        k = kalshi_data
        market = k["market"]
        st.subheader(str(market.get("title") or market.get("subtitle") or market_ticker))
        st.caption(f"Ticker: {market_ticker}")
        a, b = st.columns(2)
        a.metric("Market status", str(market.get("status", "unknown")))
        b.metric("Close / expiry (UTC)", str(market.get("close_time", market.get("expiration_time", "unknown"))))
        st.caption(f"Strike: {market.get('floor_strike', market.get('cap_strike', market.get('strike_price', 'not provided')))}")
        st.markdown("### Live YES / NO quotes")
        yes_col, no_col = st.columns(2)
        with yes_col:
            st.metric("🟢 Buy YES", show_price(k["yes_ask"]))
            st.caption(f"Sell YES: {show_price(k['yes_bid'])}")
        with no_col:
            st.metric("🔴 Buy NO", show_price(k["no_ask"]))
            st.caption(f"Sell NO: {show_price(k['no_bid'])}")
        yes, no = k["yes"], k["no"]
        yes_depth = sum(q for _, q in yes)
        no_depth = sum(q for _, q in no)
        total = yes_depth + no_depth
        imbalance = ((yes_depth - no_depth) / total * 100) if total else np.nan
        x, y, z = st.columns(3)
        x.metric("YES visible depth", f"{yes_depth:,.0f}" if yes else "—")
        y.metric("NO visible depth", f"{no_depth:,.0f}" if no else "—")
        z.metric("Depth imbalance", f"{imbalance:+.1f}%" if pd.notna(imbalance) else "Unavailable")
        if k["book_error"]:
            st.warning(f"Order book unavailable: {k['book_error']}")
        elif not yes and not no:
            st.info("No visible bids were returned. This does not mean YES or NO costs 0¢.")
        st.markdown("#### Visible order-book bids")
        left, right = st.columns(2)
        with left:
            st.markdown("**YES bids**")
            st.dataframe(pd.DataFrame(yes, columns=["Price (¢)", "Contracts"]).head(15), use_container_width=True, hide_index=True)
        with right:
            st.markdown("**NO bids**")
            st.dataframe(pd.DataFrame(no, columns=["Price (¢)", "Contracts"]).head(15), use_container_width=True, hide_index=True)
        st.subheader("Decision checklist")
        if abs(direction_score) < 8:
            st.warning("NO TRADE bias: BTC momentum is weak or mixed.")
        elif yes and no and pd.notna(imbalance) and np.sign(direction_score) == np.sign(imbalance) and abs(imbalance) >= min_edge:
            st.success("Momentum and visible depth align. Candidate only; verify price, spread, expiry and fees.")
        else:
            st.warning("No confirmed order-flow edge. Avoid forcing a trade.")
        st.caption("Order-book depth is not a forecast. Quotes can change and may not be executable at the displayed size.")

with tab3:
    st.markdown("""
**What this version does**
- Pulls recent BTC-USD 1-minute candles from Coinbase public market data.
- Calculates short-term returns, EMA trend and a simple momentum heuristic.
- Automatically discovers open Kalshi BTC 15-minute markets and displays available YES/NO quotes and visible bids.
- Shows a cautious candidate/no-trade checklist.

**What it does not claim**
- It does not know the exact final BTC price.
- It does not calculate a statistically validated probability of finishing above/below a strike.
- It does not use private order flow, hidden liquidity or every trade print.
- It does not place orders.

**For a proper model:** save timestamped BTC and Kalshi snapshots, collect realized outcomes, then backtest with walk-forward validation, fees, spread, slippage and calibration. A signal should be promoted only if out-of-sample performance supports it.
""")
st.caption(f"Last dashboard update: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} • Data may be delayed.")
