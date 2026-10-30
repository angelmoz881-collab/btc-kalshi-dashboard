"""Gold price-action research: completed HTF swings, turning zones, confirmed candles.

All levels are calculated on OHLC data, never Kalshi contract odds. GC=F futures
and Pyth XAU/USD are different price series: mixed-source levels are not overlaid.
"""
import math
import time

import numpy as np
import pandas as pd
import requests
import streamlit as st

from gold_data_quality import PRO_HISTORY_URL, PRO_SYMBOL

YAHOO_GOLD = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"


def _ohlc(frame):
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    d = frame.copy()
    d["time"] = pd.to_datetime(d["time"], utc=True, errors="coerce")
    for c in ("open", "high", "low", "close"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    if "volume" not in d:
        d["volume"] = 0.0
    d["volume"] = pd.to_numeric(d["volume"], errors="coerce").fillna(0.0)
    d = d.dropna(subset=["time", "open", "high", "low", "close"])
    d = d[(d["low"] > 0) & (d["high"] >= d[["open", "close", "low"]].max(axis=1)) &
          (d["low"] <= d[["open", "close"]].min(axis=1))]
    return d.sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)


def completed(frame, resolution="1min", now=None):
    """Exclude in-progress bars before making swing or candle claims."""
    d = _ohlc(frame)
    if d.empty:
        return d
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    ts = d["time"]
    if resolution == "W":
        start = ts.dt.normalize() - pd.to_timedelta(ts.dt.day_of_week, unit="D")
        end = start + pd.Timedelta(days=7)
    elif resolution == "D":
        end = ts.dt.normalize() + pd.Timedelta(days=1)
    else:
        end = ts + pd.Timedelta(resolution)
    return d[end <= now].reset_index(drop=True)


def resample_ohlc(frame, interval="5min", now=None):
    d = _ohlc(frame)
    if d.empty:
        return d
    d = d.set_index("time")
    out = d.resample(interval, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["open", "high", "low", "close"]).reset_index()
    return completed(out, interval, now=now)


def swing_points(frame, wings=2):
    """Strict confirmed local turning points; latest wings bars are never pivots."""
    d = _ohlc(frame)
    highs, lows = [], []
    for i in range(wings, len(d) - wings):
        h, low = float(d.at[i, "high"]), float(d.at[i, "low"])
        if h > d["high"].iloc[i - wings:i].max() and h > d["high"].iloc[i + 1:i + wings + 1].max():
            highs.append((i, h))
        if low < d["low"].iloc[i - wings:i].min() and low < d["low"].iloc[i + 1:i + wings + 1].min():
            lows.append((i, low))
    return highs, lows


def structure(frame):
    highs, lows = swing_points(frame)
    if len(highs) < 2 or len(lows) < 2:
        return {"trend": "INSUFFICIENT", "highs": len(highs), "lows": len(lows)}
    hh = highs[-1][1] > highs[-2][1]
    lh = highs[-1][1] < highs[-2][1]
    hl = lows[-1][1] > lows[-2][1]
    ll = lows[-1][1] < lows[-2][1]
    direction = "UPTREND" if hh and hl else "DOWNTREND" if lh and ll else "RANGE / MIXED"
    return {
        "trend": direction, "highs": len(highs), "lows": len(lows),
        "last_high": round(highs[-1][1], 2), "last_low": round(lows[-1][1], 2),
        "swing_labels": ("HH / HL" if hh and hl else "LH / LL" if lh and ll else
                         ("HH" if hh else "LH" if lh else "EQH") + " / " +
                         ("HL" if hl else "LL" if ll else "EQL")),
    }


@st.cache_data(ttl=1800, show_spinner=False)
def _pyth_context(api_key):
    if not api_key:
        raise PermissionError("PYTH_PRO_API_KEY not configured")
    now = int(time.time())
    results = []
    for resolution, days in (("D", 540), ("W", 1100)):
        r = requests.get(
            PRO_HISTORY_URL,
            params={"symbol": PRO_SYMBOL, "from": now - days * 86400,
                    "to": now, "resolution": resolution},
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            timeout=12,
        )
        r.raise_for_status()
        body = r.json()
        if body.get("s") != "ok":
            raise ValueError("Pyth Pro historical " + resolution + " candles unavailable")
        rows = []
        for i, stamp in enumerate(body.get("t") or []):
            try:
                o, h, low, c = (float(body[k][i]) for k in ("o", "h", "l", "c"))
                if all(math.isfinite(x) and x > 0 for x in (o, h, low, c)):
                    rows.append({"time": pd.to_datetime(int(stamp), unit="s", utc=True),
                                 "open": o, "high": h, "low": low, "close": c})
            except (ValueError, TypeError, IndexError, KeyError, OverflowError):
                continue
        results.append(completed(pd.DataFrame(rows), resolution))
    if min(map(len, results)) < 18:
        raise ValueError("Insufficient completed Pyth Pro daily/weekly candles")
    return results[0], results[1]


@st.cache_data(ttl=1800, show_spinner=False)
def _futures_context():
    r = requests.get(YAHOO_GOLD, params={"interval": "1d", "range": "2y"},
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
    r.raise_for_status()
    result = (r.json().get("chart", {}).get("result") or [None])[0]
    if not result:
        raise ValueError("GC=F daily history unavailable")
    q = result["indicators"]["quote"][0]
    rows = []
    for i, stamp in enumerate(result.get("timestamp") or []):
        try:
            values = [float(q[k][i]) for k in ("open", "high", "low", "close")]
            if all(math.isfinite(v) and v > 0 for v in values):
                rows.append(dict(zip(("open", "high", "low", "close"), values)),
                            time=pd.to_datetime(int(stamp), unit="s", utc=True))
        except (ValueError, TypeError, IndexError, KeyError):
            continue
    daily = completed(pd.DataFrame(rows), "D")
    # Weekly futures series is aggregated only from completed daily sessions.
    weekly = daily.set_index("time").resample("W-MON", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna().reset_index()
    return daily, completed(weekly, "W")


def load_context(api_key):
    """Return Pyth context when entitled, otherwise visibly marked GC research."""
    try:
        daily, weekly = _pyth_context(str(api_key or "").strip())
        return daily, weekly, "Pyth Pro XAU/USD", None
    except Exception as exc:
        pyth_error = str(exc)
    try:
        daily, weekly = _futures_context()
        return daily, weekly, "Yahoo GC=F · research only", pyth_error
    except Exception as exc:
        return pd.DataFrame(), pd.DataFrame(), "Unavailable", pyth_error + "; " + str(exc)


def _atr(frame, period=14):
    d = _ohlc(frame)
    if len(d) < 2:
        return 0.0
    prev = d["close"].shift()
    tr = pd.concat([d["high"] - d["low"], (d["high"] - prev).abs(),
                    (d["low"] - prev).abs()], axis=1).max(axis=1)
    return float(tr.tail(period).mean())


def turning_zones(intraday, daily=None, weekly=None, *, source_matched=False, price=None):
    """Cluster confirmed swing pivots into price ranges; count nonadjacent touches."""
    d = completed(intraday, "1min")
    if len(d) < 30:
        return []
    price = float(price if price is not None else d["close"].iloc[-1])
    five = resample_ohlc(d, "5min")
    atr = max(_atr(five), price * 0.00008)
    candidates = []
    for frame, interval, multiplier, name in (
        (five, "5m", 1.0, "5m"),
        (resample_ohlc(d, "15min"), "15m", 1.4, "15m"),
        (daily if source_matched else None, "D", 3.0, "Daily"),
        (weekly if source_matched else None, "W", 4.0, "Weekly"),
    ):
        if frame is None or len(frame) < 8:
            continue
        highs, lows = swing_points(frame, wings=2)
        width = max(atr * 0.42 * multiplier, price * 0.000035)
        for kind, points in (("RESISTANCE", highs), ("SUPPORT", lows)):
            for i, level in points[-45:]:
                if abs(level - price) > max(atr * 35, price * 0.035):
                    continue
                candidates.append({"kind": kind, "level": level, "width": width,
                                   "weight": 1 + (1 if interval in ("D", "W") else 0),
                                   "tf": name, "age": len(frame) - 1 - i})
    clusters = []
    for c in sorted(candidates, key=lambda x: x["level"]):
        existing = next((z for z in clusters if z["kind"] == c["kind"] and
                         abs(z["center"] - c["level"]) <= max(z["half"], c["width"]) * 1.2), None)
        if existing is None:
            clusters.append({"kind": c["kind"], "center": c["level"], "half": c["width"],
                             "touches": 1, "strength": c["weight"], "tf": [c["tf"]],
                             "age": c["age"]})
        else:
            total = existing["strength"] + c["weight"]
            existing["center"] = ((existing["center"] * existing["strength"] +
                                   c["level"] * c["weight"]) / total)
            existing["half"] = max(existing["half"], c["width"])
            existing["strength"] = total
            existing["touches"] += 1
            existing["age"] = min(existing["age"], c["age"])
            if c["tf"] not in existing["tf"]:
                existing["tf"].append(c["tf"])
    # Keep the nearest credible zones, without displaying every pivot as a line.
    clusters.sort(key=lambda z: (abs(z["center"] - price) / max(atr, .01) -
                                 .25 * min(z["touches"], 5) -
                                 .4 * ("Daily" in z["tf"] or "Weekly" in z["tf"])))
    output = []
    for z in clusters:
        if any(abs(z["center"] - (kept["low"] + kept["high"]) / 2) < max(z["half"], (kept["high"] - kept["low"]) / 2) * 1.4
               and z["kind"] == kept["kind"] for kept in output):
            continue
        output.append({"kind": z["kind"], "low": round(z["center"] - z["half"], 2),
                       "high": round(z["center"] + z["half"], 2),
                       "touches": z["touches"], "tf": "/".join(z["tf"])})
        if len(output) == 6:
            break
    return sorted(output, key=lambda z: z["low"])


def candle_confirmations(intraday, zones, now=None):
    """Doji needs next-bar direction; hammers/stars need next close beyond wick."""
    findings = []
    for interval, name in (("1min", "1m"), ("5min", "5m")):
        bars = completed(intraday, "1min", now=now) if name == "1m" else resample_ohlc(intraday, interval, now=now)
        if len(bars) < 4:
            continue
        start = max(1, len(bars) - 12)
        for i in range(start, len(bars) - 1):
            b = bars.iloc[i]
            nxt = bars.iloc[i + 1]
            span = max(float(b["high"] - b["low"]), 1e-8)
            body = abs(float(b["close"] - b["open"]))
            bottom = min(float(b["close"]), float(b["open"]))
            top = max(float(b["close"]), float(b["open"]))
            low_wick = (bottom - b["low"]) / span
            high_wick = (b["high"] - top) / span
            doji = body / span <= 0.12
            hammer = low_wick >= .52 and high_wick <= .18 and body / span <= .40
            star = high_wick >= .52 and low_wick <= .18 and body / span <= .40
            bull_engulf = (bars.iloc[i - 1]["close"] < bars.iloc[i - 1]["open"] and
                           b["close"] > b["open"] and b["open"] <= bars.iloc[i - 1]["close"] and
                           b["close"] >= bars.iloc[i - 1]["open"])
            bear_engulf = (bars.iloc[i - 1]["close"] > bars.iloc[i - 1]["open"] and
                           b["close"] < b["open"] and b["open"] >= bars.iloc[i - 1]["close"] and
                           b["close"] <= bars.iloc[i - 1]["open"])
            for z in zones:
                if b["low"] > z["high"] or b["high"] < z["low"]:
                    continue
                direction, pattern = None, None
                if z["kind"] == "SUPPORT":
                    if hammer and nxt["close"] > b["high"]:
                        direction, pattern = "BULLISH", "Hammer + follow-through"
                    elif bull_engulf and nxt["close"] > b["close"]:
                        direction, pattern = "BULLISH", "Bullish engulfing + follow-through"
                    elif doji and nxt["close"] > b["high"]:
                        direction, pattern = "BULLISH", "Doji + bullish breakout"
                else:
                    if star and nxt["close"] < b["low"]:
                        direction, pattern = "BEARISH", "Shooting star + follow-through"
                    elif bear_engulf and nxt["close"] < b["close"]:
                        direction, pattern = "BEARISH", "Bearish engulfing + follow-through"
                    elif doji and nxt["close"] < b["low"]:
                        direction, pattern = "BEARISH", "Doji + bearish breakdown"
                if direction:
                    findings.append({
                        "time": int(pd.Timestamp(b["time"]).timestamp()),
                        "confirmed_at": int(pd.Timestamp(nxt["time"]).timestamp()),
                        "direction": direction, "pattern": pattern, "tf": name,
                        "zone": z["kind"], "price": round(float(b["close"]), 2),
                    })
                    break
    return sorted(findings, key=lambda x: (x["confirmed_at"], x["tf"] == "5m"), reverse=True)[:5]


def analyze_gold_structure(intraday, daily, weekly, *, intraday_source, context_source, now=None):
    d = completed(intraday, "1min", now=now)
    day = completed(daily, "D", now=now)
    week = completed(weekly, "W", now=now)
    clock = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    clock = clock.tz_localize("UTC") if clock.tzinfo is None else clock.tz_convert("UTC")
    # Sessions close on weekends and holidays; reject truly stale HTF history.
    day_recent = len(day) > 0 and clock - day["time"].iloc[-1] <= pd.Timedelta(days=7)
    week_recent = len(week) > 0 and clock - week["time"].iloc[-1] <= pd.Timedelta(days=22)
    dtrend = structure(day) if len(day) >= 18 and day_recent else {"trend": "INSUFFICIENT"}
    wtrend = structure(week) if len(week) >= 18 and week_recent else {"trend": "INSUFFICIENT"}
    ready = dtrend["trend"] not in ("INSUFFICIENT",) and wtrend["trend"] not in ("INSUFFICIENT",)
    source_matched = (str(intraday_source) == "Pyth Pro XAU/USD" and
                      str(context_source) == "Pyth Pro XAU/USD") or (
                      str(intraday_source).startswith("Yahoo GC=F") and
                      str(context_source).startswith("Yahoo GC=F"))
    if ready and dtrend["trend"] == wtrend["trend"] and dtrend["trend"] in ("UPTREND", "DOWNTREND"):
        bias = dtrend["trend"]
    elif ready:
        bias = "MIXED"
    else:
        bias = "UNAVAILABLE"
    price = float(d["close"].iloc[-1]) if len(d) else None
    zones = turning_zones(d, day, week, source_matched=source_matched, price=price) if price else []
    patterns = candle_confirmations(d, zones, now=now) if zones else []
    return {
        "daily": dtrend, "weekly": wtrend, "bias": bias,
        "zones": zones, "patterns": patterns,
        "source_matched": source_matched,
        "context_source": str(context_source),
        "intraday_source": str(intraday_source),
        "research_only": not source_matched or "Pyth" not in str(intraday_source),
    }
