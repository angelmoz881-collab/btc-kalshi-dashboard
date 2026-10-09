import time
from datetime import datetime, timezone
import requests
import pandas as pd
import numpy as np
import streamlit as st
import json
import html
import streamlit.components.v1 as components

st.set_page_config(page_title="BTC × Kalshi | Live Terminal", page_icon="₿", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');
:root {color-scheme:dark}
.stApp {background:radial-gradient(ellipse at 90% -10%,rgba(130,23,35,.24),transparent 42%),linear-gradient(180deg,#08090e 0%,#0b0d14 58%,#0b0d14 100%);color:#e9f1fc;font-family:'DM Sans',sans-serif}
.block-container {padding-top:1.5rem;max-width:1420px;padding-left:1.5rem;padding-right:1.5rem;padding-bottom:3rem}
h1,h2,h3 {font-family:'Space Grotesk',sans-serif!important;letter-spacing:-.035em!important}
h3 {color:#dceaff!important}
p, label {color:#c2d0e4}
[data-testid="stMetric"] {background:linear-gradient(145deg,rgba(26,43,66,.95),rgba(15,28,46,.96));padding:18px 19px;border:1px solid #39212a;border-radius:17px;box-shadow:0 9px 25px rgba(0,0,0,.13);min-height:108px}
[data-testid="stMetricLabel"] {color:#94a9c4!important;font-size:.79rem!important;letter-spacing:.02em}
[data-testid="stMetricValue"] {font-family:'Space Grotesk',sans-serif;font-weight:700;letter-spacing:-.04em;font-size:clamp(1.25rem,2vw,1.85rem)!important}
[data-testid="stMetricDelta"] {font-weight:700}
[data-testid="stTabs"] {margin-top:1rem}
[data-testid="stTabs"] [role="tablist"] {gap:8px;border-bottom:1px solid #39212a}
[data-testid="stTabs"] button {font-weight:700;border-radius:10px 10px 0 0;padding:12px 17px;color:#9bb1cf}
[data-testid="stTabs"] button[aria-selected="true"] {color:#ff6c78!important;background:#35161e}
[data-testid="stSidebar"] {background:#100c12;border-right:1px solid #39212a}
[data-testid="stSidebar"] h2 {color:#ecf7ff}
[data-testid="stRadio"] div[role="radiogroup"] {gap:6px;flex-wrap:wrap}
[data-testid="stRadio"] label {border:1px solid #56303a;background:#1a1119;border-radius:9px;padding:4px 10px}
[data-testid="stAlert"] {border-radius:13px}
hr {border-color:#3b222b!important}
.hero {padding:22px 25px;border:1px solid #5d2835;border-radius:21px;background:linear-gradient(112deg,rgba(52,15,24,.95),rgba(20,12,20,.95) 60%,rgba(55,17,28,.8));margin-bottom:18px;box-shadow:0 12px 38px rgba(0,0,0,.13)}
.eyebrow {font-size:.72rem;letter-spacing:.16em;font-weight:800;color:#ff6575;text-transform:uppercase;margin-bottom:7px}
.hero-title {font-family:'Space Grotesk',sans-serif;font-size:clamp(1.5rem,3vw,2.4rem);font-weight:700;letter-spacing:-.05em;color:#f1f7ff;line-height:1.13}
.hero-sub {color:#a6bbd2;font-size:.87rem;margin-top:8px}
.badge {display:inline-block;border:1px solid #a93d4e;border-radius:20px;background:rgba(155,35,52,.18);color:#ff8c96;font-weight:800;font-size:.72rem;padding:6px 11px;margin-top:13px}
.section-heading {font-size:.72rem;font-weight:800;color:#8fa6c1;letter-spacing:.14em;text-transform:uppercase;margin:20px 0 11px}
@media(max-width:650px){.block-container{padding:.55rem .65rem 2rem}.hero{padding:12px 14px;border-radius:13px;margin-bottom:8px}.hero-title{font-size:1.35rem}.hero-sub{font-size:.76rem}.badge{margin-top:7px;font-size:.63rem;padding:4px 8px}[data-testid="stMetric"]{padding:9px 10px;min-height:72px;border-radius:11px}[data-testid="stMetricValue"]{font-size:1.08rem!important}[data-testid="stTabs"] button{padding:8px 7px;font-size:.75rem}.section-heading{margin:10px 0 6px}[data-testid="stVerticalBlock"]{gap:.48rem}div[data-testid="stPlotlyChart"]{margin:0!important}}

.position-panel {background:linear-gradient(125deg,#250d17,#120e16 75%);border:1px solid #783140;border-radius:16px;padding:17px 18px;margin:10px 0 15px;box-shadow:0 9px 32px rgba(0,0,0,.2)}
.position-eyebrow{font-size:.66rem;color:#e7a6b0;font-weight:800;letter-spacing:.12em}
.position-mood{font-size:clamp(1.15rem,4vw,1.75rem);font-weight:900;letter-spacing:.035em;margin:9px 0 15px}
.position-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px}
.position-grid>div{background:#140e16;border:1px solid #43242d;border-radius:9px;padding:10px;min-width:0}
.position-grid small{display:block;font-size:.6rem;color:#aa8894;letter-spacing:.07em;margin-bottom:6px}
.position-grid strong{display:block;font-size:clamp(.88rem,1.6vw,1.15rem);color:#f7e9ed;overflow-wrap:anywhere}
.position-note{font-size:.7rem;color:#ac8996;margin-top:12px}
@media(max-width:650px){.position-panel{padding:12px}.position-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.position-grid>div{padding:8px}.position-grid strong{font-size:.95rem}}
</style>""", unsafe_allow_html=True)
st.markdown("""<div class="hero"><div class="eyebrow">HYPER-STYLE TERMINAL · BTC × KALSHI</div><div class="hero-title">₿ &nbsp; BTC / KALSHI LIVE</div><div class="hero-sub">Live candles · 15-minute contracts · order flow · risk first</div><span class="badge">● LIVE DATA &nbsp;·&nbsp; RESEARCH ONLY</span></div>""", unsafe_allow_html=True)

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

top_a, top_b, top_c = st.columns([1.5, 1, 1])
top_a.metric("BTC / USD", f"${price:,.2f}", f"{ret1:+.2f}% · 1m")
top_b.metric("5m move", f"{ret5:+.2f}%" if pd.notna(ret5) else "—")
top_c.metric("Trend", trend.title())

kalshi_data = None
kalshi_error = None
if market_ticker:
    try:
        kalshi_data = kalshi_snapshot(market_ticker)
    except requests.RequestException as exc:
        kalshi_error = str(exc)


# Dual-purpose research signals: deliberately conservative, not calibrated probabilities.
@st.cache_data(ttl=12, show_spinner=False)
def recent_exchange_trades():
    r = requests.get(f"{COINBASE}/products/BTC-USD/trades", headers=HEADERS, timeout=9)
    r.raise_for_status()
    trades = r.json()
    if not isinstance(trades, list):
        raise ValueError("Unexpected exchange trade format")
    result = []
    for t in trades:
        try:
            size = float(t["size"])
            px = float(t["price"])
            side = str(t.get("side", "")).lower()
            if size > 0 and px > 0 and side in ("buy", "sell"):
                # Coinbase Exchange trade 'side' is the maker side; the aggressor is opposite.
                result.append(("buy" if side == "sell" else "sell", size * px))
        except (KeyError, ValueError, TypeError):
            pass
    return result

@st.cache_data(ttl=45, show_spinner=False)
def blockchain_activity():
    # Unconfirmed transactions are NOT attributed to whales or exchanges.
    r = requests.get("https://mempool.space/api/mempool", timeout=9)
    r.raise_for_status()
    data = r.json()
    return int(data.get("count", 0)), int(data.get("vsize", 0))

def research_signals(frame, snapshot, exchange_trades):
    closes = frame["close"].astype(float)
    if len(closes) < 40:
        return {"outcome": "UNCERTAIN", "scalp": "WAIT", "reason": "Insufficient BTC history", "momentum": 0.0,
                "pressure": None, "bid_balance": None, "spread": None, "target": None}
    p = float(closes.iloc[-1])
    r5 = p / float(closes.iloc[-6]) - 1
    r15 = p / float(closes.iloc[-16]) - 1
    vol = float(closes.pct_change().tail(40).std())
    momentum = (r5 + 0.5 * r15) / max(vol * np.sqrt(15), 0.00001)
    pressure = None
    if exchange_trades:
        total = sum(v for _, v in exchange_trades)
        pressure = sum((1 if side == "buy" else -1) * v for side, v in exchange_trades) / total if total else None
    balance, spread, target = None, None, None
    if snapshot:
        yes_depth = sum(q for _, q in snapshot["yes"][:5])
        no_depth = sum(q for _, q in snapshot["no"][:5])
        if yes_depth + no_depth > 0:
            balance = (yes_depth - no_depth) / (yes_depth + no_depth)
        if snapshot["yes_ask"] is not None and snapshot["yes_bid"] is not None:
            spread = snapshot["yes_ask"] - snapshot["yes_bid"]
        m = snapshot["market"]
        # Strike is not universally present/meaningful; avoid inventing it.
        for key in ("floor_strike", "strike_price"):
            try:
                value = float(m[key])
                if 1000 < value < 1000000:
                    target = value
                    break
            except (KeyError, TypeError, ValueError):
                continue
    outcome = "UNCERTAIN"
    if target is not None:
        distance = (p - target) / p
        if distance > max(0.0003, vol * 2):
            outcome = "YES LEAN"
        elif distance < -max(0.0003, vol * 2):
            outcome = "NO LEAN"
    # A short-lived scalp setup is NOT an execution recommendation.
    scalp = "WAIT"
    reason = "Signals disagree, missing quotes, or insufficient edge"
    if snapshot and spread is not None and 0 <= spread <= 3 and pressure is not None and balance is not None:
        if momentum > 0.55 and pressure > 0.18 and balance > 0.12:
            scalp, reason = "WATCH YES", "Positive BTC momentum and trade/order-book pressure; check fees and depth"
        elif momentum < -0.55 and pressure < -0.18 and balance < -0.12:
            scalp, reason = "WATCH NO", "Negative BTC momentum and trade/order-book pressure; check fees and depth"
    return {"outcome": outcome, "scalp": scalp, "reason": reason, "momentum": momentum,
            "pressure": pressure, "bid_balance": balance, "spread": spread, "target": target}

with st.spinner("Checking exchange whale-size trades and Kalshi liquidity..."):
    try:
        whale_trades = recent_exchange_trades()
        whale_error = None
    except (requests.RequestException, ValueError) as exc:
        whale_trades, whale_error = [], str(exc)
    try:
        chain_count, chain_vsize = blockchain_activity()
        chain_error = None
    except (requests.RequestException, ValueError, TypeError) as exc:
        chain_count, chain_vsize, chain_error = None, None, str(exc)
engine = research_signals(candles, kalshi_data, whale_trades)

st.caption("Choose a section below. Each selection loads its content separately on mobile.")
# Native radio navigation reruns the app and reliably renders only the selected
# page on mobile browsers, avoiding empty Streamlit tab panels.
selected_page = st.radio(
    "Dashboard section",
    ["📈 LIVE CHART", "📊 MARKET FLOW", "📖 GUIDE"],
    horizontal=True,
    label_visibility="collapsed",
    key="dashboard_section",
)


if selected_page == "📈 LIVE CHART":
    if market_ticker:
        st.info(f"🎯 **Kalshi market ticker: `{market_ticker}`**" +
                (f"  |  Status: **{kalshi_data['market'].get('status', 'unknown')}**" if kalshi_data else "  |  Quotes unavailable"))
    else:
        st.warning("⚠️ No Kalshi ticker selected. Open Settings to select an active BTC 15-minute contract.")
    tcol, wcol = st.columns(2)
    with tcol:
        timeframe = st.selectbox("Candle size", ["1m", "5m", "15m", "30m", "1h"], index=0)
    with wcol:
        window = st.selectbox("Show history", ["15m", "30m", "1h", "3h", "6h"], index=2)
    with st.expander("⚙️ Chart options", expanded=False):
        show_ema = st.toggle("Show EMA 5 / 15", value=True)
        chart_style = st.radio("Chart type", ["Candles", "Line"], horizontal=True)
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

    # Convert timestamps to real UNIX *seconds* in a way that does not depend on
    # pandas' internal datetime resolution (ns/us/ms/s). Newer pandas builds can
    # preserve a non-nanosecond dtype, so dividing astype("int64") by 1e9 can
    # collapse many candles onto the same timestamp and make the chart appear empty.
    def _unix_seconds(value):
        ts = pd.Timestamp(value)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return int(ts.timestamp())

    view["epoch"] = view["time"].map(_unix_seconds).astype("int64")
    view = view.sort_values("epoch").drop_duplicates("epoch", keep="last")
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
    # Lightweight Charts handles native two-finger scaling and one-finger panning.
    # Pass unique, strictly ascending UNIX timestamps (seconds, not milliseconds).
    clean_bars = sorted({b["time"]: b for b in bars}.values(), key=lambda b: b["time"])
    if len(clean_bars) < 2:
        st.error("At least two distinct candles are required to draw the chart.")
        st.stop()
    closes = pd.Series([b["close"] for b in clean_bars], dtype="float64")
    overlays = []
    for span, color in ((5, "#fbbf24"), (15, "#a78bfa")):
        avg = closes.ewm(span=span, adjust=False).mean()
        overlays.append({"color": color, "points": [
            {"time": b["time"], "value": float(v)} for b, v in zip(clean_bars, avg)
        ]})
    chart_data = json.dumps({
        "bars": clean_bars,
        "line": [{"time": b["time"], "value": b["close"]} for b in clean_bars],
        "overlays": overlays if show_ema else [],
        "style": chart_style,
        "timeframe": timeframe,
        "visible": visible_count,
    }, allow_nan=False)
    chart_html = r"""<!doctype html><html><head>
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />
    <style>
    html,body{margin:0;background:#0b0b11;color:#d9e3f1;font-family:system-ui;overflow:hidden}
    #frame{position:relative;width:100%;height:440px;overflow:hidden}
    #chart{width:100%;height:440px;touch-action:none;overscroll-behavior:contain}
    #status{position:absolute;top:9px;left:12px;pointer-events:none;background:#120e16d9;
      border:1px solid #56303a;border-radius:8px;padding:6px 9px;font-size:12px;z-index:2}
    #error{color:#ff9eaa;padding:15px;display:none}
    </style></head><body>
    <div id="frame"><div id="status">BTC/USD · __TIMEFRAME__</div><div id="chart"></div><div id="error"></div></div>
    <script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js"></script>
    <script>
    const data=__PAYLOAD__;
    const root=document.getElementById('chart');
    const error=document.getElementById('error');
    try {
      if(!window.LightweightCharts) throw new Error('Chart library unavailable.');
      const LC=window.LightweightCharts;
      const chart=LC.createChart(root,{
        width:root.clientWidth,height:440,
        layout:{background:{type:'solid',color:'#0b0b11'},textColor:'#b9c9df'},
        grid:{vertLines:{color:'#251c27'},horzLines:{color:'#251c27'}},
        rightPriceScale:{borderColor:'#51303b',scaleMargins:{top:.08,bottom:.12}},
        timeScale:{timeVisible:true,secondsVisible:false,borderColor:'#51303b',
          barSpacing:8,minBarSpacing:2,rightOffset:3},
        crosshair:{mode:LC.CrosshairMode.Magnet},
        handleScroll:{mouseWheel:false,pressedMouseMove:true,horzTouchDrag:false,vertTouchDrag:false},
        handleScale:{axisPressedMouseMove:false,mouseWheel:false,pinch:true},
        kineticScroll:{touch:true,mouse:false}
      });
      const main=data.style==='Candles'
        ?chart.addCandlestickSeries({upColor:'#34d399',downColor:'#fb7185',borderVisible:false,
          wickUpColor:'#34d399',wickDownColor:'#fb7185'})
        :chart.addLineSeries({color:'#60a5fa',lineWidth:2});
      main.setData(data.style==='Candles'?data.bars:data.line);
      data.overlays.forEach(o=>{
        const series=chart.addLineSeries({color:o.color,lineWidth:1,
          lastValueVisible:false,priceLineVisible:false});series.setData(o.points);
      });
      function setInitialView(){
        const n=data.bars.length;
        const visible=Math.min(n,Math.max(3,data.visible));
        chart.timeScale().setVisibleLogicalRange({from:n-visible-1,to:n+2});
      }
      requestAnimationFrame(()=>requestAnimationFrame(setInitialView));
      new ResizeObserver(()=>chart.applyOptions({width:root.clientWidth})).observe(root);

      // Mobile controls: custom one-finger horizontal panning + native two-finger pinch.
      // Android browsers inside Streamlit iframes can swallow Lightweight Charts' built-in
      // one-finger drag, so we pan the logical time range ourselves.
      let panStartX=null;
      let panStartRange=null;
      let panMoved=false;
      root.addEventListener('touchstart', e => {
        if (e.touches.length===1) {
          panStartX=e.touches[0].clientX;
          const r=chart.timeScale().getVisibleLogicalRange();
          panStartRange=r ? {from:r.from,to:r.to} : null;
          panMoved=false;
        } else {
          panStartX=null;
          panStartRange=null;
        }
      }, {passive:true});

      root.addEventListener('touchmove', e => {
        if (e.touches.length!==1 || panStartX===null || !panStartRange) return;
        e.preventDefault();
        const dx=e.touches[0].clientX-panStartX;
        if (Math.abs(dx)>3) panMoved=true;
        const barsVisible=Math.max(1, panStartRange.to-panStartRange.from);
        const pxPerBar=Math.max(2, root.clientWidth/barsVisible);
        const shift=-dx/pxPerBar;
        chart.timeScale().setVisibleLogicalRange({
          from:panStartRange.from+shift,
          to:panStartRange.to+shift
        });
      }, {passive:false});

      root.addEventListener('touchend', e => {
        if (e.touches.length===0) {
          panStartX=null;
          panStartRange=null;
        }
      }, {passive:true});
      root.addEventListener('touchcancel', () => {
        panStartX=null;
        panStartRange=null;
      }, {passive:true});

      root.addEventListener('contextmenu',e=>e.preventDefault());
    } catch(e){error.style.display='block';error.textContent='Chart error: '+e.message;}
    </script></body></html>"""
    chart_html = chart_html.replace("__PAYLOAD__", chart_data).replace("__TIMEFRAME__", timeframe)
    components.html(chart_html, height=448, scrolling=False)
    st.caption("👆 Drag left/right: move through candles · 🤏 Pinch: zoom · Tap: inspect candle")
    with st.expander("Chart data / troubleshooting", expanded=False):
        st.caption(f"Loaded {len(clean_bars)} distinct {timeframe} candles · UTC "
                   f"{datetime.fromtimestamp(clean_bars[0]['time'], timezone.utc):%H:%M}–"
                   f"{datetime.fromtimestamp(clean_bars[-1]['time'], timezone.utc):%H:%M}.")
    # A compact, high-contrast contract status card inspired by trading terminals.
    expiry_raw = None
    if kalshi_data:
        market_info = kalshi_data["market"]
        expiry_raw = market_info.get("close_time") or market_info.get("expiration_time")
        seconds_left = None
        if expiry_raw:
            try:
                expires = pd.to_datetime(expiry_raw, utc=True)
                seconds_left = max(0, int((expires - pd.Timestamp.now(tz="UTC")).total_seconds()))
            except (ValueError, TypeError):
                pass
        clock = f"{seconds_left // 60:02d}:{seconds_left % 60:02d}" if seconds_left is not None else "—:—"
        target_raw = market_info.get("floor_strike") or market_info.get("strike_price")
        try:
            target_value = float(target_raw)
            distance = price - target_value
            target_text = f"${target_value:,.2f}"
            distance_text = f"${distance:+,.2f}"
        except (ValueError, TypeError):
            target_text = "—"
            distance_text = "—"
    else:
        clock, target_text, distance_text = "—:—", "—", "—"
    momentum = float(np.clip((ret5 if pd.notna(ret5) else 0) * 18 + (ret15 if pd.notna(ret15) else 0) * 5, -100, 100))
    if momentum > 8:
        mood, mood_color = "UPWARD MOMENTUM", "#36d7a4"
    elif momentum < -8:
        mood, mood_color = "DOWNWARD MOMENTUM", "#ff6c78"
    else:
        mood, mood_color = "NO CLEAR EDGE", "#ffcf77"
    # Client-side timer ticks every second without Streamlit rerunning or resetting the chart.
    # A separate server refresh is still required to roll over to a new Kalshi contract.
    timer_expiry = None
    if expiry_raw:
        try:
            timer_expiry = pd.to_datetime(expiry_raw, utc=True).isoformat()
        except (ValueError, TypeError, OverflowError):
            pass
    timer_html = r"""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
    <style>html,body{margin:0;background:transparent;color:#f4f6fb;font-family:system-ui,sans-serif}
    .timer{box-sizing:border-box;padding:11px 15px;border:1px solid #793141;border-radius:12px;background:#210f18;display:flex;align-items:center;justify-content:space-between;gap:12px}
    .label{font-size:11px;font-weight:800;letter-spacing:.13em;color:#efa3b0}.value{font-size:26px;font-weight:850;font-variant-numeric:tabular-nums;color:#fff;letter-spacing:.035em}
    .expired{color:#ff7183}.hint{font-size:10px;color:#aa8892}</style></head><body>
    <div class="timer"><div><div class="label">KALSHI CONTRACT · TIME LEFT</div><div class="hint" id="hint">Countdown updates every second</div></div><div class="value" id="count">--:--</div></div>
    <script>const expiry=__EXPIRY__;const el=document.getElementById('count');
    function tick(){if(!expiry){el.textContent='--:--';document.getElementById('hint').textContent='Expiry unavailable';return;}
    const ms=Date.parse(expiry)-Date.now();if(!Number.isFinite(ms)){el.textContent='--:--';return;}
    if(ms<=0){el.textContent='EXPIRED';el.classList.add('expired');document.getElementById('hint').textContent='Refresh dashboard for next contract';return;}
    const sec=Math.ceil(ms/1000);const hh=Math.floor(sec/3600);const mm=Math.floor((sec%3600)/60);const ss=sec%60;
    el.textContent=(hh?String(hh).padStart(2,'0')+':':'')+String(mm).padStart(2,'0')+':'+String(ss).padStart(2,'0');}
    tick();setInterval(tick,1000);</script></body></html>""".replace('__EXPIRY__', json.dumps(timer_expiry))
    components.html(timer_html, height=78, scrolling=False)
    st.markdown(f"""<div class="position-panel">
      <div class="position-eyebrow">● LIVE POSITION INTEL · INDICATORS ONLY</div>
      <div class="position-mood" style="color:{mood_color}">{html.escape(mood)}</div>
      <div class="position-grid">
        <div><small>CONTRACT TIMER</small><strong>LIVE ABOVE ↑</strong></div>
        <div><small>BTC PRICE</small><strong>${price:,.2f}</strong></div>
        <div><small>CONTRACT TARGET*</small><strong>{target_text}</strong></div>
        <div><small>PRICE VS TARGET</small><strong>{distance_text}</strong></div>
      </div><div class="position-note">Momentum is descriptive, not a prediction. *Target shown only when the Kalshi API supplies an interpretable strike.</div>
    </div>""", unsafe_allow_html=True)
    st.markdown('<div class="section-heading">Kalshi YES / NO · live quotes</div>', unsafe_allow_html=True)
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

    direction_score = np.clip((ret5 if pd.notna(ret5) else 0) * 18 + (ret15 if pd.notna(ret15) else 0) * 5, -100, 100)
    if abs(direction_score) < 8:
        context = "NO CLEAR EDGE — wait for confirmation"
    elif direction_score > 0:
        context = "UPSIDE MOMENTUM — only consider a long after checking Kalshi price and spread"
    else:
        context = "DOWNSIDE MOMENTUM — only consider a short/downside thesis after checking Kalshi price and spread"
    with st.expander("📊 Momentum & recent candles", expanded=False):
        st.info(context)
        st.write(f"Momentum score (heuristic): **{direction_score:+.1f}/100**. Not a calibrated probability.")
        st.metric("15m realized volatility", f"{vol15:.3f}%" if pd.notna(vol15) else "—")
        st.dataframe(candles.tail(10).sort_values("time", ascending=False), use_container_width=True, hide_index=True)

    st.markdown("### 🎯 Outcome + ⚡ Scalp intelligence")
    st.markdown('<div class="section-heading">Dual engine · 15-minute outcome + short-term scalps</div>', unsafe_allow_html=True)
    pred_col, scalp_col = st.columns(2)
    with pred_col:
        st.metric("🎯 Expiration outlook", engine["outcome"])
        st.caption("Directional lean only; NOT a calibrated probability. Exact settlement depends on Kalshi contract rules and price source.")
    with scalp_col:
        st.metric("⚡ Scalping setup", engine["scalp"])
        st.caption(engine["reason"])
    with st.expander("🐋 Whale activity · signal evidence", expanded=False):
        if whale_error:
            st.warning(f"Exchange trades unavailable: {whale_error}")
        else:
            sizes = [usd for _, usd in whale_trades]
            large = [(side, usd) for side, usd in whale_trades if usd >= 100000]
            st.write(f"Recent Coinbase trades sampled: **{len(whale_trades)}** · Trades ≥ $100k: **{len(large)}**")
            st.write("Aggressive trade pressure: **" + (f"{engine['pressure']:+.1%}" if engine['pressure'] is not None else "Unavailable"))
            st.caption("Large exchange trades are a proxy for whale-size activity, not proof of a specific whale wallet.")
        if chain_error:
            st.caption(f"Blockchain activity unavailable: {chain_error}")
        else:
            st.write(f"Bitcoin mempool: **{chain_count:,} unconfirmed transactions** · **{chain_vsize / 1e6:.2f} MB vsize**")
            st.caption("Mempool volume is blockchain activity, NOT identified whale transfers or exchange inflows. Wallet attribution is not provided by this public feed.")
        st.write("Kalshi top-five bid-depth balance: **" + (f"{engine['bid_balance']:+.1%}" if engine['bid_balance'] is not None else "Unavailable") + "**")
        st.write("YES spread: **" + (f"{engine['spread']:.1f}¢" if engine['spread'] is not None else "Unavailable") + "**")
        st.caption("Signals use sampled public data, not full historical Kalshi flow. NO automated orders are placed.")

    with st.expander("🧪 Paper signal tracker · session only", expanded=False):
        if "paper_signals" not in st.session_state:
            st.session_state.paper_signals = []
        if st.button("Record current signals", type="secondary"):
            st.session_state.paper_signals.append({"recorded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "ticker": market_ticker or "none", "btc": round(price, 2), "outcome_lean": engine["outcome"],
                "scalp_watch": engine["scalp"], "settled_result": "NOT VERIFIED"})
            st.session_state.paper_signals = st.session_state.paper_signals[-200:]
        if st.session_state.paper_signals:
            st.dataframe(pd.DataFrame(st.session_state.paper_signals), hide_index=True, use_container_width=True)
            st.download_button("Export paper signals (CSV)", pd.DataFrame(st.session_state.paper_signals).to_csv(index=False),
                               file_name="btc_kalshi_paper_signals.csv", mime="text/csv")
        st.caption("Records only signals while this Streamlit session remains active. Outcomes are NOT automatically settled or verified; do not interpret them as backtest accuracy.")


if selected_page == "📊 MARKET FLOW":
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

if selected_page == "📖 GUIDE":
    st.markdown("""
**How to use this dashboard**
- **LIVE CHART:** BTC candles, Kalshi quotes, countdown, outcome lean, scalping watch, and whale indicators.
- **MARKET FLOW:** Kalshi order book, bid depth, and YES/NO spread.
- **GUIDE:** Explains signals and limitations.

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
