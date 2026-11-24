"""Compact, independently refreshing Polymarket BTC 5-minute trading panel.
Public market data only. This module never places or signs orders.
"""
from __future__ import annotations
import json, time
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import requests
import streamlit as st

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
COINBASE = "https://api.exchange.coinbase.com"
SERIES = "btc-up-or-down-5m"
HEADERS = {"User-Agent": "BTC-Polymarket-5m-Research/1.0", "Accept": "application/json"}

@st.cache_data(ttl=5, show_spinner=False)
def discover_polymarket_btc_5m():
    r = requests.get(f"{GAMMA}/events", params={"series_slug": SERIES, "closed": "false", "limit": 500, "order": "endDate", "ascending": "true"}, headers=HEADERS, timeout=8)
    r.raise_for_status()
    now = datetime.now(timezone.utc).timestamp()
    active = []
    for event in r.json() if isinstance(r.json(), list) else []:
        try:
            start = pd.Timestamp(event.get("eventStartTime") or event.get("startTime")).timestamp()
            end = pd.Timestamp(event.get("endDate")).timestamp()
            if start <= now < end and event.get("markets"):
                active.append((end, event))
        except (TypeError, ValueError, OverflowError):
            continue
    return min(active, key=lambda x: x[0])[1] if active else None

@st.cache_data(ttl=1, show_spinner=False)
def get_polymarket_book(token_id):
    r = requests.get(f"{CLOB}/book", params={"token_id": str(token_id)}, headers=HEADERS, timeout=6)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=2, show_spinner=False)
def get_coinbase_btc_1m():
    r = requests.get(f"{COINBASE}/products/BTC-USD/candles", params={"granularity": 60}, headers=HEADERS, timeout=8)
    r.raise_for_status()
    rows = r.json()
    if not isinstance(rows, list) or len(rows) < 20:
        raise ValueError("Not enough recent Coinbase candles")
    df = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    for col in ["low", "high", "open", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna().sort_values("time").reset_index(drop=True)

def _levels(book, side):
    out = []
    for row in book.get(side) or []:
        try:
            p, q = float(row.get("price")), float(row.get("size"))
            if 0 < p < 1 and q > 0:
                out.append((p, q))
        except (TypeError, ValueError, AttributeError):
            pass
    return sorted(out, key=lambda x: x[0], reverse=(side == "bids"))

def _book_metrics(book):
    bids, asks = _levels(book, "bids"), _levels(book, "asks")
    bid = bids[0][0] if bids else None
    ask = asks[0][0] if asks else None
    bd, ad = sum(q for _, q in bids[:5]), sum(q for _, q in asks[:5])
    total = bd + ad
    return {"bid": bid, "ask": ask, "spread": ask - bid if bid is not None and ask is not None else None,
            "bid_depth": bd, "ask_depth": ad, "imbalance": (bd - ad) / total if total else None,
            "mid": (bid + ask) / 2 if bid is not None and ask is not None else (ask if ask is not None else bid)}

def _technical_read(df):
    c = df["close"].astype(float)
    if len(c) < 20:
        return {"bias": "WAIT", "r5": None, "r15": None, "rsi": None, "price": float(c.iloc[-1])}
    r5, r15 = float(c.iloc[-1] / c.iloc[-6] - 1), float(c.iloc[-1] / c.iloc[-16] - 1)
    e5, e15 = float(c.ewm(span=5, adjust=False).mean().iloc[-1]), float(c.ewm(span=15, adjust=False).mean().iloc[-1])
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain.iloc[-1] / max(float(loss.iloc[-1]), 1e-12)
    rsi = float(100 - 100 / (1 + rs))
    score = float(np.tanh(r5 / .0015)) * .45 + float(np.tanh(r15 / .003)) * .25 + (.20 if e5 > e15 else -.20) + float(np.clip((rsi - 50) / 50, -1, 1)) * .10
    return {"bias": "UP" if score >= .22 else "DOWN" if score <= -.22 else "WAIT", "r5": r5, "r15": r15, "rsi": rsi, "price": float(c.iloc[-1])}

def _render_outcome(label, data):
    st.markdown(f"#### {label}")
    st.metric("Buy at ask", f"{data['ask']:.3f}" if data["ask"] is not None else "—")
    st.caption(f"Sell at bid: {data['bid']:.3f}" if data["bid"] is not None else "Sell at bid: —")
    st.caption(f"Spread: {data['spread']:.3f}" if data["spread"] is not None else "Spread: —")
    st.caption(f"Top-5 depth · bid {data['bid_depth']:,.0f} / ask {data['ask_depth']:,.0f} shares")
    imb = data["imbalance"]
    st.caption(f"Book pressure: {imb:+.1%}" if imb is not None else "Book pressure: —")
    if imb is not None:
        st.progress(float(np.clip((imb + 1) / 2, 0, 1)))

@st.fragment(run_every="1s")
def render_polymarket_btc_5m():
    """Refresh this panel every second without rerunning the main Streamlit app."""
    st.markdown("### ₿ POLY 5M")
    try:
        event = discover_polymarket_btc_5m()
    except Exception as exc:
        st.error(f"Market feed: {type(exc).__name__}: {exc}")
        return
    if not event:
        st.warning("No active BTC 5-minute market found. Checking again shortly.")
        return
    markets = event.get("markets") or []
    market = markets[0] if markets else {}
    try:
        tokens, outcomes = market.get("clobTokenIds") or [], market.get("outcomes") or ["Up", "Down"]
        if isinstance(tokens, str): tokens = json.loads(tokens)
        if isinstance(outcomes, str): outcomes = json.loads(outcomes)
        token_map = {str(name).lower(): tokens[i] for i, name in enumerate(outcomes) if i < len(tokens)}
        up_token, down_token = token_map.get("up"), token_map.get("down")
        if not up_token or not down_token: raise ValueError("Missing Up/Down outcome tokens")
    except Exception as exc:
        st.error(f"Market data incomplete: {exc}")
        return
    try:
        up, up_error = _book_metrics(get_polymarket_book(up_token)), None
    except Exception as exc:
        up, up_error = None, f"{type(exc).__name__}: {exc}"
    try:
        down, down_error = _book_metrics(get_polymarket_book(down_token)), None
    except Exception as exc:
        down, down_error = None, f"{type(exc).__name__}: {exc}"
    try:
        candles = get_coinbase_btc_1m()
        tech, spot = _technical_read(candles), float(candles["close"].iloc[-1])
    except Exception as exc:
        candles, tech, spot = None, {"bias": "WAIT"}, None
        st.caption(f"BTC feed unavailable: {type(exc).__name__}")
    start_raw, end_raw = event.get("eventStartTime") or event.get("startTime"), event.get("endDate")
    try:
        start_ts = pd.Timestamp(start_raw).timestamp() if start_raw else None
        end_ts = pd.Timestamp(end_raw).timestamp() if end_raw else None
    except (TypeError, ValueError, OverflowError):
        start_ts = end_ts = None
    remaining = max(0, int(end_ts - time.time())) if end_ts else None
    mm, ss = divmod(remaining or 0, 60)
    slug = event.get("slug") or market.get("slug")
    st.markdown(f"**{market.get('question') or event.get('title') or 'Bitcoin Up or Down — 5 minutes'}**")
    if slug: st.markdown(f"[Open market on Polymarket](https://polymarket.com/event/{slug})")
    cols = st.columns(3)
    cols[0].metric("BTC spot", "$" + f"{spot:,.2f}" if spot is not None else "—")
    cols[1].metric("Time left", f"{mm:02d}:{ss:02d}" if remaining is not None else "—")
    cols[2].metric("5m bias", tech.get("bias", "WAIT"))
    if start_ts and end_ts:
        st.caption(f"Market window {datetime.fromtimestamp(start_ts, timezone.utc):%H:%M:%S}–{datetime.fromtimestamp(end_ts, timezone.utc):%H:%M:%S} UTC")
    if up and down:
        left, right = st.columns(2)
        with left: _render_outcome("🟢 UP", up)
        with right: _render_outcome("🔴 DOWN", down)
        st.markdown("**Market pricing**")
        p = st.columns(3)
        p[0].metric("UP midpoint", f"{up['mid']:.1%}" if up["mid"] is not None else "—")
        p[1].metric("DOWN midpoint", f"{down['mid']:.1%}" if down["mid"] is not None else "—")
        p[2].metric("Combined", f"{up['mid'] + down['mid']:.1%}" if up["mid"] is not None and down["mid"] is not None else "—")
    else:
        st.warning("One or both order books are unavailable.")
        if up_error: st.caption(f"UP book: {up_error}")
        if down_error: st.caption(f"DOWN book: {down_error}")
    if tech.get("r5") is not None:
        st.markdown("**BTC momentum**")
        m = st.columns(3)
        m[0].metric("5m change", f"{tech['r5']:+.3%}")
        m[1].metric("15m context", f"{tech['r15']:+.3%}")
        m[2].metric("RSI", f"{tech['rsi']:.0f}")
    st.caption("Independent refresh: books ~1s · BTC candles ~2s · market discovery ~5s. Odds and technical bias are not guaranteed predictions. Read-only; no orders are placed.")
