"""Regression tests for the Gold higher-timeframe and candle-zone research."""
import sys
import types

import pandas as pd

sys.modules.setdefault("streamlit", types.SimpleNamespace(
    cache_data=lambda **kwargs: (lambda fn: fn)
))

from gold_structure import (completed, structure, turning_zones, candle_confirmations,
                            analyze_gold_structure)


def sample(prices, *, end="2026-10-30T11:58:00Z", frequency="1min"):
    end = pd.Timestamp(end)
    stamps = pd.date_range(end=end, periods=len(prices), freq=frequency)
    return pd.DataFrame({
        "time": stamps, "open": prices, "high": [x + .7 for x in prices],
        "low": [x - .7 for x in prices], "close": prices,
        "volume": [1.] * len(prices),
    })


def test_completed_excludes_forming_daily_and_weekly_candle():
    df = sample([100, 101, 102], end="2026-10-30T00:00:00Z", frequency="1D")
    actual = completed(df, "D", now="2026-10-30T12:00:00Z")
    assert len(actual) == 2
    weeks = sample([100, 101, 102], end="2026-10-26T00:00:00Z", frequency="7D")
    actual_weeks = completed(weeks, "W", now="2026-10-30T12:00:00Z")
    assert len(actual_weeks) == 2


def test_confirmed_higher_highs_higher_lows_and_downtrend():
    import math
    up = sample([100 + .4 * i + 3 * math.sin(i * .7) for i in range(80)])
    down = sample([150 - .4 * i + 3 * math.sin(i * .7) for i in range(80)])
    assert structure(up)["trend"] == "UPTREND"
    assert structure(down)["trend"] == "DOWNTREND"


def test_zones_are_price_ranges_not_single_lines():
    import math
    bars = sample([200 + 2.5 * math.sin(i * .22) for i in range(350)])
    zones = turning_zones(bars, price=200)
    assert zones
    assert all(z["low"] < z["high"] for z in zones)
    assert all(z["kind"] in {"SUPPORT", "RESISTANCE"} for z in zones)


def test_hammer_requires_next_closed_candle_breakout_at_support():
    t = pd.date_range("2026-10-30T11:50:00Z", periods=5, freq="1min")
    frame = pd.DataFrame({
        "time": t,
        "open": [100.2, 100.3, 100.5, 100.7, 100.9],
        "high": [100.5, 100.5, 100.7, 101.0, 101.0],
        "low": [100.0, 100.0, 99.0, 100.6, 100.6],
        "close": [100.3, 100.4, 100.6, 100.9, 100.8],
    })
    zones = [{"kind": "SUPPORT", "low": 98.9, "high": 99.5}]
    signals = candle_confirmations(frame, zones, now="2026-10-30T11:56:00Z")
    assert signals
    assert any("Hammer" in p["pattern"] and p["direction"] == "BULLISH" for p in signals)
    frame.loc[3, "close"] = 100.65
    frame.loc[3, "high"] = 100.8
    signals = candle_confirmations(frame, zones, now="2026-10-30T11:56:00Z")
    assert not any("Hammer" in p["pattern"] for p in signals)


def test_mismatched_pyth_and_gc_sources_not_reported_as_valid_confluence():
    import math
    bars = sample([100 + 2 * math.sin(i * .24) for i in range(350)])
    d = sample([100 + .4 * i + math.sin(i * .7) for i in range(80)],
               end="2026-10-29T00:00:00Z", frequency="1D")
    w = sample([100 + .4 * i + math.sin(i * .7) for i in range(80)],
               end="2026-10-19T00:00:00Z", frequency="7D")
    state = analyze_gold_structure(bars, d, w,
        intraday_source="Pyth Pro XAU/USD",
        context_source="Yahoo GC=F · research only",
        now="2026-10-30T12:00:00Z")
    assert not state["source_matched"]
    assert state["research_only"]
