"""Independent TradingView gold display. NOT a machine-readable price feed.

TradingView's official widget supplies its own XAU/USD quotes and user controls.
The bot's Kalshi signals MUST continue to use authenticated Pyth candles/quotes.
"""
import json

import streamlit as st
import streamlit.components.v1 as components


def render_tradingview_gold():
    st.markdown("### Gold live chart · TradingView")
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
