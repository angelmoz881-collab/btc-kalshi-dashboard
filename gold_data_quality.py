"""Freshness-checked candle feeds for Kalshi's Pyth-settled Gold contracts.

Yahoo GC=F is a futures research proxy, not a Pyth settlement feed.
Do not silently replace missing OHLC candles with a Yahoo metadata tick.
"""
import math
import time

import pandas as pd
import requests
import streamlit as st

PRO_HISTORY_URL = "https://pyth.dourolabs.app/v1/fixed_rate@200ms/history"
PRO_SYMBOL = "Metal.XAU/USD"


def assess_candles(candles, *, source, now=None, max_age_sec=135):
    """Return explicit data quality, independent of UI refresh or HTTP cache age."""
    now = time.time() if now is None else float(now)
    info = {
        "source": source,
        "is_pyth_candles": source == "Pyth Pro XAU/USD",
        "fresh": False,
        "last_candle_utc": None,
        "candle_age_sec": None,
        "reason": "",
    }
    if candles is None or candles.empty:
        info["reason"] = "No 1-minute Gold candles"
        return info

    stamps = pd.to_datetime(candles["time"], utc=True, errors="coerce")
    stamps = stamps.dropna().drop_duplicates().sort_values()
    if len(stamps) < 35:
        info["reason"] = f"Only {len(stamps)} valid candles (need at least 35)"
        return info

    last = stamps.iloc[-1]
    last_epoch = float(last.timestamp())
    info["last_candle_utc"] = last.isoformat()
    age = now - last_epoch
    info["candle_age_sec"] = max(0.0, age)
    if age < -60:
        info["reason"] = "Provider candle timestamp is in the future"
        return info
    if age > max_age_sec:
        info["reason"] = f"Last 1m candle is {age:.0f}s old (limit {max_age_sec}s)"
        return info

    # A single current-looking tick cannot conceal a gap in the OHLC history.
    recent = stamps[stamps >= pd.Timestamp.fromtimestamp(now - 20 * 60, tz="UTC")]
    if len(recent) < 12:
        info["reason"] = f"Only {len(recent)} distinct candles in the past 20m"
        return info
    intervals = stamps.iloc[-20:].diff().dt.total_seconds().dropna()
    if not intervals.empty and (intervals > 180).any():
        info["reason"] = "Gap over 3 minutes in the recent 1m candle history"
        return info

    info["fresh"] = True
    info["reason"] = "Recent 1m candle history verified"
    return info


@st.cache_data(ttl=12, show_spinner=False)
def fetch_pyth_pro_candles(api_key):
    """Authenticated Pyth Pro history; must not be confused with Pyth Core Hermes."""
    api_key = str(api_key or "").strip()
    if not api_key:
        raise PermissionError("PYTH_PRO_API_KEY is not configured")
    now = int(time.time())
    r = requests.get(
        PRO_HISTORY_URL,
        params={"symbol": PRO_SYMBOL, "from": now - 6 * 3600, "to": now, "resolution": "1"},
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        timeout=12,
    )
    if r.status_code in (401, 403):
        raise PermissionError("Pyth Pro history key invalid or not entitled to Metal.XAU/USD")
    r.raise_for_status()
    body = r.json()
    if body.get("s") != "ok":
        raise ValueError(f"Pyth Pro history unavailable: {body.get('s')}")
    times = body.get("t") or []
    rows = []
    for i, stamp in enumerate(times):
        try:
            o, h, low, c = (float(body[k][i]) for k in ("o", "h", "l", "c"))
            if all(math.isfinite(v) and v > 0 for v in (o, h, low, c)):
                rows.append({
                    "time": pd.to_datetime(int(stamp), unit="s", utc=True),
                    "open": o, "high": h, "low": low, "close": c,
                    "volume": 0.0,
                })
        except (KeyError, IndexError, ValueError, TypeError, OverflowError):
            continue
    if not rows:
        raise ValueError("Pyth Pro returned no valid XAU/USD candles")
    return (pd.DataFrame(rows).sort_values("time")
            .drop_duplicates("time", keep="last").tail(720).reset_index(drop=True))


def load_gold_candles(pro_api_key, gc_fallback, *, max_age_sec=135):
    """Prefer Pyth OHLC, fall back to visibly labeled GC research data only."""
    error = None
    try:
        df = fetch_pyth_pro_candles(pro_api_key)
        quality = assess_candles(df, source="Pyth Pro XAU/USD", max_age_sec=max_age_sec)
        if quality["fresh"]:
            return df, quality
        error = quality["reason"]
    except Exception as exc:
        error = str(exc)

    # Keep charts visible for diagnostics, but never qualify proxy for auto-entry.
    df = gc_fallback()
    quality = assess_candles(df, source="Yahoo GC=F (delayed research proxy)",
                             max_age_sec=max_age_sec)
    quality["pyth_pro_error"] = error
    return df, quality
