import time
from datetime import datetime, timezone
import requests
import pandas as pd
import numpy as np
import streamlit as st
import json
import streamlit.components.v1 as components

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

def price_cents(value, dollar_field=False):
    if value is None or value == "":
        return None
    try:
        v = float(value)
        return v * 100 if dollar_field else v
    except (ValueError, TypeError):
        return None

def market_quote(market, side, kind):
    # Prefer explicit dollar fields; older API responses use integer cents.
    for key in (f"{side}_{kind}_dollars", f"{side}_{kind}"):
        if key in market and market[key] is not None:
            return price_cents(market[key], key.endswith("_dollars"))
    return None

def levels(book, side):
    """Handle both Kalshi legacy cent books and newer dollar-string books."""
    key = f"{side}_dollars" if book.get(f"{side}_dollars") is not None else side
    rows = book.get(key) or []
    dollar_field = key.endswith("_dollars")
    result = []
    for row in rows:
        if isinstance(row, dict):
            if row.get("price_dollars") is not None:
                raw_price, is_dollars = row["price_dollars"], True
            elif row.get("price") is not None:
                raw_price, is_dollars = row["price"], dollar_field
            else:
                continue
            qty = row.get("quantity", row.get("count", row.get("size", 0)))
        elif isinstance(row, (list, tuple)) and len(row) >= 2:
            raw_price, qty = row[:2]
            is_dollars = dollar_field
        else:
            continue
        price = price_cents(raw_price, is_dollars)
        try:
            qty = float(qty)
        except (TypeError, ValueError):
            continue
        if price is not None and 0 <= price <= 100 and qty > 0:
            result.append((price, qty))
    return sorted(result, key=lambda item: item[0], reverse=True)

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

tab1, tab2, tab3 = st.tabs(["Live dashboard", "Kalshi order flow", "How to interpret"])

with tab1:
    st.markdown("#### BTC / USD · Price action")
    st.caption("TradingView Lightweight Charts · drag to pan · pinch or scroll to zoom · crosshair for exact candle prices")
    window = st.radio("Visible history", ["15m", "30m", "1h", "3h", "6h"], index=2, horizontal=True)
    c1, c2 = st.columns(2)
    with c1:
        show_ema = st.toggle("EMA 5 / 15", value=True)
    with c2:
        chart_style = st.selectbox("Chart style", ["Candles", "Line"], label_visibility="collapsed")
    minutes = {"15m": 15, "30m": 30, "1h": 60, "3h": 180, "6h": 360}[window]
    view = candles.tail(minutes + 1).copy()
    # All timestamps are UTC epoch seconds, as required by Lightweight Charts.
    view["epoch"] = (view["time"].astype("int64") // 1_000_000_000).astype(int)
    bars = [{"time": int(r.epoch), "open": float(r.open), "high": float(r.high),
             "low": float(r.low), "close": float(r.close)} for r in view.itertuples()]
    line = [{"time": b["time"], "value": b["close"]} for b in bars]
    # Calculate EMAs from the entire history, not just the displayed window.
    all_ema5 = candles["close"].ewm(span=5, adjust=False).mean()
    all_ema15 = candles["close"].ewm(span=15, adjust=False).mean()
    ema5 = [{"time": int(t), "value": float(v)} for t, v in zip(view["epoch"], all_ema5.tail(len(view)))]
    ema15 = [{"time": int(t), "value": float(v)} for t, v in zip(view["epoch"], all_ema15.tail(len(view)))]
    payload = json.dumps({"bars": bars, "line": line, "ema5": ema5, "ema15": ema15,
                          "showEma": show_ema, "style": chart_style})
    chart_html = r"""
    <!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1" />
    <style>html,body{margin:0;background:#0c1929;color:#dbe6f6;font:13px system-ui;overflow:hidden}
    #chart{width:100%;height:530px;touch-action:pan-y;border:1px solid #2b405c;border-radius:14px}#legend{position:absolute;top:9px;left:12px;z-index:2;
    background:rgba(11,25,43,.93);border:1px solid #29435c;padding:9px 12px;border-radius:9px;pointer-events:none;font-variant-numeric:tabular-nums}
    #error{padding:18px;color:#fca5a5;display:none}</style></head><body>
    <div id="legend">BTC / USD · 1m</div><div id="chart"></div><div id="error"></div>
    <script src="https://unpkg.com/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js"></script>
    <script>
    const data=__DATA__;
    if(!window.LightweightCharts){document.getElementById('error').style.display='block';
      document.getElementById('error').textContent='Chart library could not load. Check your internet connection or browser content blocker.';
    }else{
      const root=document.getElementById('chart');
      const chart=LightweightCharts.createChart(root,{width:root.clientWidth,height:530,
        layout:{background:{type:'solid',color:'#0c1929'},textColor:'#c6d3e5',fontSize:12},
        grid:{vertLines:{color:'#1b2e44'},horzLines:{color:'#1b2e44'}},
        rightPriceScale:{borderColor:'#34445b',scaleMargins:{top:.08,bottom:.1}},
        timeScale:{borderColor:'#34445b',timeVisible:true,secondsVisible:false,rightOffset:3,
          fixLeftEdge:false,lockVisibleTimeRangeOnResize:true},
        crosshair:{mode:LightweightCharts.CrosshairMode.Normal,
          vertLine:{color:'#9ca3af',style:2,labelBackgroundColor:'#3b526d'},
          horzLine:{color:'#9ca3af',style:2,labelBackgroundColor:'#3b526d'}},
        handleScroll:{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:false},
        handleScale:{axisPressedMouseMove:true,mouseWheel:true,pinch:true},
        localization:{priceFormatter:p=>'$'+p.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}
      });
      const primary=data.style==='Candles'
        ?chart.addCandlestickSeries({upColor:'#38d6b0',downColor:'#ff6d83',borderVisible:false,
          wickUpColor:'#38d6b0',wickDownColor:'#ff6d83'})
        :chart.addLineSeries({color:'#60a5fa',lineWidth:2});
      primary.setData(data.style==='Candles'?data.bars:data.line);
      if(data.showEma){
        const e5=chart.addLineSeries({color:'#fbbf24',lineWidth:1,priceLineVisible:false,lastValueVisible:false});
        const e15=chart.addLineSeries({color:'#a78bfa',lineWidth:1,priceLineVisible:false,lastValueVisible:false});
        e5.setData(data.ema5);e15.setData(data.ema15);
      }
      chart.timeScale().fitContent();
      chart.subscribeCrosshairMove(param=>{
        const bar=param.seriesData.get(primary);
        if(!bar){document.getElementById('legend').textContent='BTC / USD · 1m';return;}
        const n=x=>Number(x).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
        document.getElementById('legend').textContent=bar.open===undefined
          ?'BTC / USD · $'+n(bar.value)
          :'O '+n(bar.open)+'  H '+n(bar.high)+'  L '+n(bar.low)+'  C '+n(bar.close);
      });
      new ResizeObserver(()=>chart.applyOptions({width:root.clientWidth})).observe(root);
    }
    </script></body></html>
    """.replace("__DATA__", payload)
    components.html(chart_html, height=550, scrolling=False)
    st.caption("Drag sideways to inspect older candles. Pinch to zoom on mobile; scroll to zoom on desktop. Use the time buttons to reset your view.")
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
        st.warning("No open BTC 15-minute market was detected. Check the sidebar or enter a ticker manually.")
        st.write("Open the Kalshi contract page and copy its market ticker. This avoids silently analyzing the wrong expiry or strike.")
    else:
        try:
            market = get_market(market_ticker)
            book = get_orderbook(market_ticker)
            st.subheader(str(market.get("title", market.get("subtitle", market_ticker))))
            st.caption(f"Kalshi contract: {market_ticker}")
            status = market.get("status", "unknown")
            close_time = market.get("close_time", market.get("expiration_time", "unknown"))
            strike = market.get("floor_strike", market.get("cap_strike", market.get("strike_price", "not provided")))
            a,b,c = st.columns(3)
            a.metric("Market status", str(status))
            b.metric("Close / expiry", str(close_time))
            c.metric("Strike field", str(strike))
            st.markdown("### YES / NO market prices")
            yes_bid = market_quote(market, "yes", "bid")
            yes_ask = market_quote(market, "yes", "ask")
            no_bid = market_quote(market, "no", "bid")
            no_ask = market_quote(market, "no", "ask")
            yes = levels(book, "yes")
            no = levels(book, "no")
            # The order book contains bids. The opposing side's bid implies an ask.
            if yes_bid is None and yes:
                yes_bid = yes[0][0]
            if no_bid is None and no:
                no_bid = no[0][0]
            if yes_ask is None and no_bid is not None:
                yes_ask = 100 - no_bid
            if no_ask is None and yes_bid is not None:
                no_ask = 100 - yes_bid
            def fmt_price(value):
                return f"{value:.1f}¢" if value is not None else "—"
            q1, q2 = st.columns(2)
            with q1:
                st.markdown("#### 🟢 YES")
                st.metric("Buy YES (ask)", fmt_price(yes_ask))
                st.caption(f"Sell YES (bid): {fmt_price(yes_bid)}")
            with q2:
                st.markdown("#### 🔴 NO")
                st.metric("Buy NO (ask)", fmt_price(no_ask))
                st.caption(f"Sell NO (bid): {fmt_price(no_bid)}")
            st.caption("These are market quotes in cents per contract, not predicted probabilities or guaranteed executable prices. An ask may be inferred as 100¢ minus the opposite bid.")
            yes_depth = sum(q for _, q in yes)
            no_depth = sum(q for _, q in no)
            total = yes_depth + no_depth
            imbalance = ((yes_depth - no_depth) / total * 100) if total else np.nan
            x,y,z = st.columns(3)
            x.metric("YES bid depth", f"{yes_depth:,.0f}" if yes else "—")
            y.metric("NO bid depth", f"{no_depth:,.0f}" if no else "—")
            z.metric("Depth imbalance", f"{imbalance:+.1f}%" if pd.notna(imbalance) else "Unavailable")
            if not yes and not no:
                st.warning("Kalshi returned no visible bid levels for this contract. This is not the same as a 0¢ YES/NO price. Check that the market is open and trading.")
            elif not yes or not no:
                st.info("Only one side currently has visible bids. The other side's ask can sometimes be inferred, but depth comparison is incomplete.")
            st.markdown("#### Visible order-book bids")
            lcol, rcol = st.columns(2)
            with lcol:
                st.markdown("**YES bids**")
                st.dataframe(pd.DataFrame(yes, columns=["Price (¢)", "Contracts"]), use_container_width=True, hide_index=True)
            with rcol:
                st.markdown("**NO bids**")
                st.dataframe(pd.DataFrame(no, columns=["Price (¢)", "Contracts"]), use_container_width=True, hide_index=True)
            st.subheader("Decision checklist")
            if abs(direction_score) < 8:
                st.warning("NO TRADE bias: BTC momentum is weak or mixed.")
            elif yes and no and pd.notna(imbalance) and np.sign(direction_score) == np.sign(imbalance) and abs(imbalance) >= min_edge:
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
