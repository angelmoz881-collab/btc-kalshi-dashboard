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

exec(compile(_source, "2_Gold.py", "exec"), globals(), globals())
