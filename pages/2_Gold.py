# Gold Auto Trader loader.
# Source is stored as plain text chunks in the repo to avoid compressed-payload corruption.
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
_parts = []
for _i in range(1, 8):
    _parts.append((_root / f"gold_auto_source_{_i}.txt").read_text(encoding="utf-8"))
_source = "".join(_parts)

# Adapt the BTC bot's fast live-refresh pattern to Gold.
# Keep heavy work cached while Pyth/Kalshi quotes and the model rerender every 2–5 seconds.
def _replace_once(old, new):
    global _source
    if old not in _source:
        raise RuntimeError(f"Gold refresh patch target not found: {old[:80]!r}")
    _source = _source.replace(old, new, 1)

_replace_once(
    '@st.cache_data(ttl=4, show_spinner=False)\ndef fetch_open_gold_markets',
    '@st.cache_data(ttl=3, show_spinner=False)\ndef fetch_open_gold_markets',
)
_replace_once(
    '@st.cache_data(ttl=2, show_spinner=False)\ndef fetch_pyth_gold',
    '@st.cache_data(ttl=1, show_spinner=False)\ndef fetch_pyth_gold',
)
_replace_once(
    '@st.cache_data(ttl=15, show_spinner=False)\ndef fetch_gold_proxy_history',
    '@st.cache_data(ttl=2, show_spinner=False)\ndef fetch_gold_proxy_history',
)
_replace_once(
    '@st.cache_data(ttl=2, show_spinner=False)\ndef fetch_market',
    '@st.cache_data(ttl=1, show_spinner=False)\ndef fetch_market',
)
_replace_once(
    'with st.sidebar:\n    st.markdown("### Auto-trading controls")\n',
    'with st.sidebar:\n'
    '    st.markdown("### Auto-trading controls")\n'
    '    refresh_mode = st.selectbox(\n'
    '        "Live refresh speed",\n'
    '        ["Ultra · 2s", "Fast · 3s", "Balanced · 5s", "Paused"],\n'
    '        index=0,\n'
    '        help="Uses Streamlit fragments so the live Gold section updates without rebuilding the whole page.",\n'
    '    )\n'
    '    live_run_every = {"Ultra · 2s": 2, "Fast · 3s": 3, "Balanced · 5s": 5, "Paused": None}[refresh_mode]\n'
    '    st.caption("Gold reference, Kalshi quotes/order book and model signals use this interval. Heavy history is cached separately.")\n',
)
_replace_once(
    '@_fragment(run_every=5)\n    def _live_gold_auto_fragment():',
    '@_fragment(run_every=live_run_every)\n    def _live_gold_auto_fragment():',
)
_replace_once(
    "st.caption(f\"Updated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} · Auto trading only runs while this Streamlit session is active unless you deploy a separate always-on worker.\")",
    "st.caption(f\"Updated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} · Live refresh: {refresh_mode} · Auto trading only runs while this Streamlit session is active unless you deploy a separate always-on worker.\")",
)

# The expiration countdown is browser-clocked from Kalshi's absolute expiry.
# Streamlit can rerun every 2–5 seconds without resetting the countdown.
_replace_once(
    '    q4.metric("Time left", f"{mins:02d}:{secs:02d}")\n',
    '    with q4:\n'
    '        from gold_trader_chart import render_gold_expiry_timer\n'
    '        render_gold_expiry_timer(market.get("close_time") or market.get("expiration_time"), ticker=ticker)\n',
)

_replace_once(
'''    chart = candles.tail(180).copy()
    chart["time"] = pd.to_datetime(chart["time"], utc=True)
    chart = chart.set_index("time")
    st.markdown("### Gold momentum proxy")
    st.line_chart(pd.DataFrame({
        "GC=F close": chart["close"],
        "EMA 5": chart["close"].ewm(span=5, adjust=False).mean(),
        "EMA 15": chart["close"].ewm(span=15, adjust=False).mean(),
    }), height=280, use_container_width=True)
    st.caption("Pyth XAU/USD is used for current strike distance when authenticated. If unavailable, GC=F is shown only as a temporary research proxy; DEMO/LIVE auto-orders remain blocked.")
''',
'''    from gold_trader_chart import render_gold_trader_chart
    render_gold_trader_chart(
        candles,
        strike=strike,
        current_ref=model.get("current"),
        ticker=ticker,
        refresh_label=refresh_mode,
    )
''',
)


# Gold is settled on Pyth GOLD. GC=F is not interchangeable with Pyth candles.
# Fetch real Pyth Pro XAU/USD history when authorized; never treat Yahoo's
# regularMarketPrice metadata as an OHLC candle with real momentum/wicks.
_begin = _source.index("    # Yahoo's chart candles can lag the current quote")
_end = _source.index("    df = pd.DataFrame(rows)", _begin)
_source = _source[:_begin] + "    # Only actual one-minute OHLC bars are accepted.\\n" + _source[_end:]

_replace_once(
    'import streamlit as st\\n',
    'import streamlit as st\\nfrom gold_data_quality import load_gold_candles\\n',
)
_replace_once(
    '        candles = fetch_gold_proxy_history()\\n        pyth = gold_reference_with_fallback(candles)\\n',
    '        candles, candle_quality = load_gold_candles(\\n'
    '            _secret("PYTH_PRO_API_KEY", ""), fetch_gold_proxy_history, max_age_sec=135\\n'
    '        )\\n'
    '        pyth = gold_reference_with_fallback(candles)\\n',
)
_replace_once(
    '    model = build_gold_model(candles, pyth, snapshot, extra_buffer_cents=settings["extra_buffer"])',
    '    # Never compute a prediction from stale GC futures, an old Pyth quote, or\\n'
    '    # unverified candles. A freshly repainted screen is NOT a fresh data feed.\\n'
    '    quote_age = _safe_float(pyth.get("age_sec"))\\n'
    '    quote_ok = (pyth.get("is_settlement_reference", False) and quote_age is not None\\n'
    '                and 0 <= quote_age <= min(settings["max_quote_age"], 60))\\n'
    '    model_inputs_ready = candle_quality["fresh"] and candle_quality["is_pyth_candles"] and quote_ok\\n'
    '    model_candles = candles if model_inputs_ready else candles.iloc[0:0]\\n'
    '    model = build_gold_model(model_candles, pyth, snapshot, extra_buffer_cents=settings["extra_buffer"])\\n'
    '    if not model_inputs_ready:\\n'
    '        issue = candle_quality["reason"]\\n'
    '        if not candle_quality["is_pyth_candles"]:\\n'
    '            issue = "Pyth Pro 1m candles unavailable; GC=F is display-only"\\n'
    '        if not quote_ok:\\n'
    '            issue += "; Pyth Core settlement quote missing or stale"\\n'
    '        st.error("NO VERIFIED GOLD PREDICTION · " + issue)\\n'
    '    else:\\n'
    '        st.caption(f"✅ Pyth Pro 1m candles fresh ({candle_quality[\\"candle_age_sec\\"]:.0f}s old) · Pyth Core quote {quote_age:.1f}s old")',
)
_replace_once(
    '    side, edge, blockers = _execution_candidate(model, snapshot, settings, pyth)',
    '    side, edge, blockers = _execution_candidate(model, snapshot, settings, pyth)\\n'
    '    if not model_inputs_ready:\\n'
    '        blockers = list(blockers) + ["No verified current Pyth Gold candle + quote pair"]',
)
_replace_once(
    '        refresh_label=refresh_mode,\\n',
    '        refresh_label=refresh_mode,\\n'
    '        source_label=candle_quality["source"],\\n'
    '        candle_age_sec=candle_quality.get("candle_age_sec"),\\n',
)
_replace_once(
    '            "reference_quote_age_sec": pyth.get("age_sec"),',
    '            "reference_quote_age_sec": pyth.get("age_sec"),\\n'
    '            "candle_source": candle_quality["source"],\\n'
    '            "last_candle_utc": candle_quality.get("last_candle_utc"),\\n'
    '            "candle_age_sec": candle_quality.get("candle_age_sec"),\\n'
    '            "candle_fresh": candle_quality["fresh"],\\n'
    '            "candle_quality_reason": candle_quality["reason"],\\n'
    '            "pyth_pro_error": candle_quality.get("pyth_pro_error"),',
)

exec(compile(_source, "2_Gold.py", "exec"), globals(), globals())
