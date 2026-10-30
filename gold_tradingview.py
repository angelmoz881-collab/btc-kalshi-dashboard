"""Independent TradingView gold display. NOT a machine-readable price feed.

TradingView's official widget supplies its own XAU/USD quotes and user controls.
The bot's Kalshi signals MUST continue to use authenticated Pyth candles/quotes.
"""
import json
import math
import time
from datetime import datetime, timezone

import requests

import streamlit as st
import streamlit.components.v1 as components



@st.cache_data(ttl=25, show_spinner=False)
def _gold_spot_quote():
    """Independent spot quote for visual diagnostics ONLY; never for settlement."""
    response = requests.get("https://api.gold-api.com/price/XAU", timeout=7)
    response.raise_for_status()
    item = response.json()
    price = float(item["price"])
    if not math.isfinite(price) or price <= 0:
        raise ValueError("Invalid spot gold price")
    raw_stamp = item.get("updatedAt")
    if not raw_stamp:
        raise ValueError("Missing provider update time")
    updated = datetime.fromisoformat(str(raw_stamp).replace("Z", "+00:00"))
    if updated.tzinfo is None:
        raise ValueError("Unzoned provider update time")
    age = time.time() - updated.timestamp()
    if age < -60 or age > 120:
        raise ValueError("Spot quote is stale or has an invalid timestamp")
    return price, max(0, age), updated.strftime("%H:%M:%S UTC")


def render_spot_quote_panel():
    """Refresh independently of the TradingView embed and the main app's trading loop."""
    try:
        price, age, stamp = _gold_spot_quote()
    except (requests.RequestException, KeyError, ValueError, TypeError, OverflowError) as exc:
        st.caption("Independent spot quote unavailable: " + str(exc))
        return
    st.metric("Independent XAU/USD spot quote · display only", f"${price:,.2f}",
              help="Gold-API spot reference. Not the Pyth/Kalshi settlement feed and not used by the prediction or automatic-order engine.")
    st.caption(f"Gold-API updated {stamp} · checked age {age:.0f}s · not a trade signal")


_gold_quote_fragment = getattr(st, "fragment", None) or getattr(st, "experimental_fragment", None)
if _gold_quote_fragment is not None:
    render_spot_quote_panel = _gold_quote_fragment(run_every=30)(render_spot_quote_panel)


def render_tradingview_gold():
    st.markdown("### Gold live chart · TradingView")
    render_spot_quote_panel()
    st.caption(
        "OANDA:XAUUSD spot gold · TradingView-hosted visual chart. "
        "Select 1m / 5m / 15m / Daily / Weekly inside the chart. "
        "This is NOT the Kalshi/Pyth settlement feed and is NOT used to calculate trades."
    )
    # Official TradingView embed. Its market stream lives in this component;
    # call it OUTSIDE the 2-second Streamlit fragment so chart/zoom never reset.
    settings = {
        "autosize": True,
        "symbol": "OANDA:XAUUSD",
        "interval": "1",
        "timezone": "Etc/UTC",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "backgroundColor": "#0b0b11",
        "gridColor": "rgba(160,165,185,0.08)",
        "hide_top_toolbar": False,
        "hide_legend": False,
        "allow_symbol_change": False,
        "save_image": False,
        "calendar": False,
        "withdateranges": True,
        "support_host": "https://www.tradingview.com",
    }
    html = (
        '<!doctype html><html><head><meta name="viewport" '
        'content="width=device-width,initial-scale=1">'
        '<style>html,body{margin:0;background:#0b0b11;overflow:hidden;}'
        '.tradingview-widget-container,.tradingview-widget-container__widget'
        '{width:100%;height:100%;min-height:480px;}'
        'body{height:100vh;}</style></head><body>'
        '<div class="tradingview-widget-container">'
        '<div class="tradingview-widget-container__widget"></div>'
        '<script type="text/javascript" '
        'src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>'
        + json.dumps(settings, separators=(",", ":"))
        + '</script></div></body></html>'
    )
    components.html(html, height=540, scrolling=False)
    st.caption(
        "TradingView's spot XAU/USD quote may differ from the Pyth GOLD contract "
        "reference. For the actual Kalshi strike and expiry decisions, use the "
        "separate verified Pyth analysis below. Chart availability and latency "
        "depend on TradingView/OANDA and your connection."
    )
