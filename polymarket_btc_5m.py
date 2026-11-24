"""Polymarket BTC Up/Down 5-minute live market monitor.

Read-only public market data. This module never places or signs orders.
"""
from __future__ import annotations

import json
import math
import time
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


@st.cache_data(ttl=2, show_spinner=False)
def discover_polymarket_btc_5m():
    response = requests.get(
        f"{GAMMA}/events",
        params={"series_slug": SERIES, "closed": "false", "limit": 500,
                "order": "endDate", "ascending": "true"},
        headers=HEADERS, timeout=8,
    )
    response.raise_for_status()
    events = response.json()
    now = datetime.now(timezone.utc).timestamp()
    active = []
    for event in events if isinstance(events, list) else []:
        try:
            start = pd.Timestamp(event.get("eventStartTime") or event.get("startTime")).timestamp()
            end = pd.Timestamp(event.get("endDate")).timestamp()
            if start <= now < end and event.get("markets"):
                active.append((end, event))
        except (TypeError, ValueError, OverflowError):
            continue
    if not active:
        return None
    return min(active, key=lambda row: row[0])[1]


@st.cache_data(ttl=1, show_spinner=False)
def get_polymarket_book(token_id):
    response = requests.get(
        f"{CLOB}/book", params={"token_id": str(token_id)},
        headers=HEADERS, timeout=6,
    )
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=2, show_spinner=False)
def get_coinbase_btc_1m():
    response = requests.get(
        f"{COINBASE}/products/BTC-USD/candles",
        params={"granularity": 60}, headers=HEADERS, timeout=8,
    )
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list) or len(rows) < 20:
        raise ValueError("Not enough recent Coinbase candles")
    frame = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"])
    frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
    for col in ["low", "high", "open", "close", "volume"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame.dropna().sort_values("time").reset_index(drop=True)


def _levels(book, side):
    rows = book.get(side) or []
    parsed = []
    for row in rows:
        try:
            price = float(row.get("price"))
            size = float(row.get("size"))
            if 0 < price < 1 and size > 0:
                parsed.append((price, size))
        except (TypeError, ValueError, AttributeError):
            continue
    return sorted(parsed, key=lambda item: item[0], reverse=(side == "bids"))


def _book_metrics(book):
    bids, asks = _levels(book, "bids"), _levels(book, "asks")
    bid = bids[0][0] if bids else None
    ask = asks[0][0] if asks else None
    bid_depth = sum(q for _, q in bids[:5])
    ask_depth = sum(q for _, q in asks[:5])
    total = bid_depth + ask_depth
    imbalance = (bid_depth - ask_depth) / total if total else None
    return {
        "bids": bids, "asks": asks, "bid": bid, "ask": ask,
        "bid_depth": bid_depth, "ask_depth": ask_depth,
        "imbalance": imbalance,
    }


def _technical_read(frame):
    """Short-window price-action context; deliberately uncalibrated."""
    c = frame["close"].astype(float)
    if len(c) < 20:
        return {"bias": "WAIT", "score": 0.0, "r5": None, "r15": None, "rsi": None}
    r5 = float(c.iloc[-1] / c.iloc[-6] - 1)
    r15 = float(c.iloc[-1] / c.iloc[-16] - 1)
    ema5 = float(c.ewm(span=5, adjust=False).mean().iloc[-1])
    ema15 = float(c.ewm(span=15, adjust=False).mean().iloc[-1])
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain.iloc[-1] / max(float(loss.iloc[-1]), 1e-12)
    rsi = float(100 - 100 / (1 + rs))
    # 15m trend is context; 5m return and EMA alignment determine the short call.
    score = 0.0
    score += float(np.tanh(r5 / 0.0015)) * 0.45
    score += float(np.tanh(r15 / 0.0030)) * 0.25
    score += (0.20 if ema5 > ema15 else -0.20)
    score += float(np.clip((rsi - 50) / 50, -1, 1)) * 0.10
    if score >= 0.22:
        bias = "UP"
    elif score <= -0.22:
        bias = "DOWN"
    else:
        bias = "WAIT"
    return {"bias": bias, "score": score, "r5": r5, "r15": r15, "rsi": rsi,
            "price": float(c.iloc[-1]), "ema5": ema5, "ema15": ema15}


def render_polymarket_btc_5m():
    st.markdown("### ₿ Polymarket BTC · 5-minute market")
    st.caption("Live BTC Up/Down contract · public Polymarket order books · read-only research panel")
    try:
        event = discover_polymarket_btc_5m()
    except Exception as exc:
        st.error(f"Could not load the Polymarket 5-minute market: {type(exc).__name__}: {exc}")
        st.caption("The existing BTC/Kalshi panels are unaffected.")
        return
    if not event:
        st.warning("No currently active BTC 5-minute Polymarket event was returned. Refresh in a few seconds.")
        return

    markets = event.get("markets") or []
    market = markets[0] if markets else {}
    try:
        token_ids = market.get("clobTokenIds") or []
        outcomes = market.get("outcomes") or ["Up", "Down"]
        if isinstance(token_ids, str):
            token_ids = json.loads(token_ids)
        if isinstance(outcomes, str):
            outcomes = json.loads(outcomes)
        token_map = {str(name).lower(): token_ids[i] for i, name in enumerate(outcomes)
                     if i < len(token_ids)}
        up_token = token_map.get("up")
        down_token = token_map.get("down")
        if not up_token or not down_token:
            raise ValueError("Polymarket did not return both Up and Down outcome tokens")
    except Exception as exc:
        st.error(f"Market token data is incomplete: {exc}")
        return

    try:
        up_book = _book_metrics(get_polymarket_book(up_token))
        down_book = _book_metrics(get_polymarket_book(down_token))
        up_error = down_error = None
    except Exception as exc:
        up_book = down_book = None
        up_error = f"{type(exc).__name__}: {exc}"

    try:
        candles = get_coinbase_btc_1m()
        tech = _technical_read(candles)
        spot = float(tech.get("price") or candles["close"].iloc[-1])
    except Exception as exc:
        candles, tech, spot = None, {"bias": "WAIT", "score": 0.0}, None
        st.warning(f"BTC spot/candle feed unavailable: {type(exc).__name__}: {exc}")

    start_raw = event.get("eventStartTime") or event.get("startTime")
    end_raw = event.get("endDate")
    start_ts = pd.Timestamp(start_raw).timestamp() if start_raw else None
    end_ts = pd.Timestamp(end_raw).timestamp() if end_raw else None
    now_ts = time.time()
    seconds_left = max(0, int(end_ts - now_ts)) if end_ts else None
    slug = event.get("slug") or market.get("slug")
    question = market.get("question") or event.get("title") or "Bitcoin Up or Down — 5 minutes"

    st.markdown(f"**{question}**")
    if slug:
        st.markdown(f"[Open this market on Polymarket](https://polymarket.com/event/{slug})")

    if seconds_left is not None:
        mm, ss = divmod(seconds_left, 60)
        st.caption(f"Market window · {datetime.fromtimestamp(start_ts, timezone.utc).strftime('%H:%M:%S UTC') if start_ts else '—'} "
                   f"to {datetime.fromtimestamp(end_ts, timezone.utc).strftime('%H:%M:%S UTC')} · "
                   f"{mm:02d}:{ss:02d} remaining")

    if up_book and down_book:
        up_mid = ((up_book["bid"] + up_book["ask"]) / 2
                  if up_book["bid"] is not None and up_book["ask"] is not None
                  else up_book["ask"] if up_book["ask"] is not None else up_book["bid"])
        down_mid = ((down_book["bid"] + down_book["ask"]) / 2
                    if down_book["bid"] is not None and down_book["ask"] is not None
                    else down_book["ask"] if down_book["ask"] is not None else down_book["bid"])
        cols = st.columns(4)
        cols[0].metric("BTC spot · Coinbase", f"${spot:,.2f}" if spot else "—")
        cols[1].metric("UP best ask", f"${up_book['ask']:.3f}" if up_book["ask"] is not None else "—")
        cols[2].metric("DOWN best ask", f"${down_book['ask']:.3f}" if down_book["ask"] is not None else "—")
        cols[3].metric("Market time left", f"{mm:02d}:{ss:02d}" if seconds_left is not None else "—")

        a, b = st.columns(2)
        with a:
            st.markdown("#### 🟢 UP contract")
            st.metric("Bid / ask", f"{up_book['bid']:.3f} / {up_book['ask']:.3f}"
                      if up_book["bid"] is not None and up_book["ask"] is not None else "—")
            st.metric("Top-5 bid depth", f"{up_book['bid_depth']:,.1f}")
            st.metric("Top-5 ask depth", f"{up_book['ask_depth']:,.1f}")
            st.caption(f"Top-5 depth imbalance: {up_book['imbalance']:+.1%}" if up_book["imbalance"] is not None else "UP depth imbalance unavailable")
        with b:
            st.markdown("#### 🔴 DOWN contract")
            st.metric("Bid / ask", f"{down_book['bid']:.3f} / {down_book['ask']:.3f}"
                      if down_book["bid"] is not None and down_book["ask"] is not None else "—")
            st.metric("Top-5 bid depth", f"{down_book['bid_depth']:,.1f}")
            st.metric("Top-5 ask depth", f"{down_book['ask_depth']:,.1f}")
            st.caption(f"Top-5 depth imbalance: {down_book['imbalance']:+.1%}" if down_book['imbalance'] is not None else "DOWN depth imbalance unavailable")

        if up_mid is not None and down_mid is not None:
            st.markdown("#### Market-implied pricing")
            p1, p2, p3 = st.columns(3)
            p1.metric("UP midpoint", f"{up_mid:.1%}")
            p2.metric("DOWN midpoint", f"{down_mid:.1%}")
            p3.metric("UP + DOWN", f"{up_mid + down_mid:.1%}")
            st.caption("Midpoints are displayed market prices, not the bot's probability forecast. Spread, fees and liquidity affect executable prices.")
    elif up_error:
        st.warning(f"Polymarket order book temporarily unavailable: {up_error}")

    if tech.get("price") is not None:
        st.markdown("#### BTC price-action read")
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("5m technical bias", tech["bias"])
        d2.metric("5m momentum", f"{tech['r5']:+.3%}" if tech.get("r5") is not None else "—")
        d3.metric("15m context", f"{tech['r15']:+.3%}" if tech.get("r15") is not None else "—")
        d4.metric("RSI · 1m candles", f"{tech['rsi']:.1f}" if tech.get("rsi") is not None else "—")
        st.caption("This is an unvalidated technical bias, not a calibrated chance of winning. The 15m trend is context; short-term momentum is used only for this 5m market.")
        chart = candles.tail(90).set_index("time")[["close"]]
        st.line_chart(chart, height=210, use_container_width=True)

    with st.expander("Market details and settlement rules", expanded=False):
        st.write("**Market slug:**", slug or "not returned")
        st.write("**Event starts:**", start_raw or "not returned")
        st.write("**Event ends:**", end_raw or "not returned")
        st.write("**Resolution source:**", market.get("resolutionSource") or "Polymarket market metadata")
        st.caption("Polymarket's recurring BTC 5-minute series uses separate Up and Down outcome tokens. Confirm the market's displayed rules before trading; this panel does not submit orders.")
    st.caption("Auto-refresh follows the dashboard's normal refresh cycle. Market discovery and order-book snapshots are fetched independently from Kalshi.")
