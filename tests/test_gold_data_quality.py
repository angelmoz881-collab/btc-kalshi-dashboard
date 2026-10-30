"""Gold feed regression tests: do not silently turn stale GC into a live bet."""
import sys
import types
from pathlib import Path

import pandas as pd

# Feed quality can be tested without a running Streamlit application.
sys.modules.setdefault("streamlit", types.SimpleNamespace(
    cache_data=lambda **kwargs: (lambda fn: fn)
))
from gold_data_quality import assess_candles, load_gold_candles
import gold_data_quality as gdq


def candles(n=70, last=1_780_000_000, skip=None):
    skip = set(skip or ())
    times = [last - (n - 1 - i) * 60 for i in range(n) if i not in skip]
    return pd.DataFrame({
        "time": pd.to_datetime(times, unit="s", utc=True),
        "open": [4300.] * len(times),
        "high": [4301.] * len(times),
        "low": [4299.] * len(times),
        "close": [4300.] * len(times),
        "volume": [1.] * len(times),
    })


def test_recent_continuous_pyth_ohlc_is_eligible():
    df = candles()
    state = assess_candles(df, source="Pyth Pro XAU/USD",
                           now=1_780_000_040)
    assert state["fresh"]
    assert state["is_pyth_candles"]
    assert state["candle_age_sec"] == 40


def test_stale_timestamp_blocks_model_eligibility():
    state = assess_candles(candles(), source="Pyth Pro XAU/USD",
                           now=1_780_000_400)
    assert not state["fresh"]
    assert "old" in state["reason"]


def test_one_current_tick_cannot_hide_missing_candles():
    df = candles(skip=range(53, 68))
    state = assess_candles(df, source="Yahoo GC=F (delayed research proxy)",
                           now=1_780_000_040)
    assert not state["fresh"]


def test_pyth_history_failure_never_launders_gc_as_pyth(monkeypatch):
    def fail(key):
        raise PermissionError("no Pyth history key")
    monkeypatch.setattr(gdq, "fetch_pyth_pro_candles", fail)
    df, quality = load_gold_candles("", lambda: candles(), max_age_sec=135)
    # Avoid testing network access; pass a lambda with known current bars.
    assert quality["is_pyth_candles"] is False
    assert "no Pyth history key" in quality["pyth_pro_error"]


def test_loader_source_compiles_after_text_patches():
    # Compilation-only test: no requests, no real orders, and no Streamlit UI.
    root = Path(__file__).resolve().parents[1]
    loader = (root / "pages" / "2_Gold.py").read_text(encoding="utf-8")
    prefix = loader.rsplit('exec(compile(_source, "2_Gold.py", "exec"), globals(), globals())', 1)[0]
    namespace = {"__file__": str(root / "pages" / "2_Gold.py")}
    exec(compile(prefix, "2_Gold_loader.py", "exec"), namespace, namespace)
    compile(namespace["_source"], "2_Gold_generated.py", "exec")
    assert "No verified current Pyth Gold candle" in namespace["_source"]


def test_tradingview_chart_stays_outside_fast_rerun_fragment():
    root = Path(__file__).resolve().parents[1]
    loader = (root / "pages" / "2_Gold.py").read_text(encoding="utf-8")
    prefix = loader.rsplit('exec(compile(_source, "2_Gold.py", "exec"), globals(), globals())', 1)[0]
    namespace = {"__file__": str(root / "pages" / "2_Gold.py")}
    exec(compile(prefix, "2_Gold_loader.py", "exec"), namespace, namespace)
    source = namespace["_source"]
    assert "render_tradingview_gold()" in source
    assert source.index("render_tradingview_gold()") < source.index(
        '_fragment = getattr(st, "fragment"'
    )
    assert "with st.expander(\"Pyth/Kalshi analysis chart" in source
    assert '@st.cache_data(ttl=30, show_spinner=False)\ndef fetch_gold_proxy_history' in source


def test_tradingview_widget_uses_official_embed_not_scraped_prices():
    from gold_tradingview import render_tradingview_gold
    import inspect
    source = inspect.getsource(render_tradingview_gold)
    assert "OANDA:XAUUSD" in source
    assert "external-embedding/embed-widget-advanced-chart.js" in source
    assert "requests" not in source
