"""Independent BTC/Kalshi model arena and paper-only trade research.

The arena scores only pre-settlement snapshots against official settled results.
One fixed checkpoint per unique contract prevents multi-snapshot label inflation.
No private credentials, order creation, or real-money execution live here.
"""
from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import pandas as pd

EXPERTS = (
    ("stat_prob", "Volatility / strike"),
    ("analog_prob", "Historical analogs"),
    ("flow_prob", "Flow / candles"),
    ("market_prob", "Kalshi consensus"),
    ("base_prob_above", "Existing fusion"),
    ("adaptive_prob_above", "Adaptive learner"),
)
INDEPENDENT_WEIGHTS = (("stat_prob", 0.65), ("analog_prob", 0.25), ("flow_prob", 0.10))


def probability(value):
    """Return an actual finite probability, never silently turn NaN into 50%."""
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) and 0 <= value <= 1 else None


def number(value, fallback=None):
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return fallback
    return value if math.isfinite(value) else fallback


def independent_estimate(record):
    """Price an outcome without using its Kalshi quote (avoid circular 'edge')."""
    if probability(record.get("stat_prob")) is None:
        return None
    weighted = [(p, w) for key, w in INDEPENDENT_WEIGHTS
                if (p := probability(record.get(key))) is not None]
    if not weighted:
        return None
    total = sum(w for _, w in weighted)
    return sum(p * w for p, w in weighted) / total


def verified_snapshots(history):
    """Select a single causal snapshot, nearest 5m remaining, per market.

    We never average multiple checkpoints sharing the same settled result.
    Timestamp sorting is used only to order observations, not to form features.
    """
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return pd.DataFrame()
    required = {"ticker", "result", "recorded_utc", "remaining_sec"}
    if not required.issubset(history.columns):
        return pd.DataFrame()
    df = history.copy()
    df["result"] = df["result"].astype("string").str.lower()
    df["ticker"] = df["ticker"].astype("string")
    df["recorded_utc"] = pd.to_datetime(df["recorded_utc"], utc=True, errors="coerce")
    df["remaining_sec"] = pd.to_numeric(df["remaining_sec"], errors="coerce")
    df = df[df["result"].isin(["yes", "no"])
            & df["ticker"].notna() & df["recorded_utc"].notna()
            & df["remaining_sec"].between(61, 900, inclusive="both")].copy()
    if df.empty:
        return df
    df["_checkpoint_distance"] = (df["remaining_sec"] - 300).abs()
    df = df.sort_values(["ticker", "_checkpoint_distance", "recorded_utc"])
    df = df.drop_duplicates("ticker", keep="first")
    df = df.sort_values(["recorded_utc", "ticker"]).reset_index(drop=True)
    df["label_yes"] = df["result"].eq("yes").astype(int)
    return df


def _brier(y, p):
    return float(np.mean((np.asarray(y, dtype=float) - np.asarray(p, dtype=float)) ** 2))


def _wilson_bounds(correct, total):
    if total == 0:
        return None, None
    z = NormalDist().inv_cdf(0.975)
    p = correct / total
    den = 1.0 + z*z / total
    center = (p + z*z/(2*total)) / den
    radius = z * math.sqrt(p*(1-p)/total + z*z/(4*total*total)) / den
    return max(0.0, center-radius), min(1.0, center+radius)


def score_models(history):
    """Descriptive settled-market scores; NOT a simulated return or profitability."""
    df = verified_snapshots(history)
    if df.empty:
        return []
    output = []
    for key, name in EXPERTS:
        if key not in df.columns:
            continue
        p = pd.to_numeric(df[key], errors="coerce")
        mask = p.notna() & p.between(0, 1)
        if not mask.any():
            continue
        y = df.loc[mask, "label_yes"].to_numpy(dtype=int)
        preds = p.loc[mask].to_numpy(dtype=float)
        n = len(y)
        wins = int(np.sum((preds >= .5) == y))
        low, high = _wilson_bounds(wins, n)
        output.append({
            "Model": name, "Markets": n, "Brier ↓": round(_brier(y, preds), 4),
            "Hit rate": round(100*wins/n, 1),
            "95% hit CI": f"{100*low:.0f}–{100*high:.0f}%",
            "Status": "PROVISIONAL" if n < 100 else "OBSERVED",
            "key": key,
        })
    return sorted(output, key=lambda row: (row["Markets"] < 30, row["Brier ↓"]))


def validate_blend(history):
    """Fixed-rule chronological *evaluation*, no fitted weights or tuned thresholds.

    A blend only passes when 120 distinct resolved markets are available and
    it beats the old live prediction on *each* half of the last 120 contracts.
    This is a conservative deployment gate, not proof of future profitability.
    """
    df = verified_snapshots(history)
    if df.empty:
        return {"active": False, "status": "Collecting settled contracts", "n": 0}
    records = []
    for _, row in df.iterrows():
        base = probability(row.get("adaptive_prob_above"))
        if base is None:
            base = probability(row.get("base_prob_above"))
        independent = independent_estimate(row)
        if base is None or independent is None:
            continue
        records.append((int(row["label_yes"]), base, .7*base + .3*independent))
    n = len(records)
    result = {"active": False, "status": f"Collecting {n}/120 comparable markets", "n": n,
              "recent_base_brier": None, "recent_blend_brier": None, "improvement": None}
    if n < 120:
        return result
    recent = np.array(records[-120:], dtype=float)
    if len(set(recent[:, 0].astype(int))) < 2:
        result["status"] = "Awaiting YES and NO settlement examples"
        return result
    delta = []
    for sample in (recent[:60], recent[60:]):
        original = _brier(sample[:, 0], sample[:, 1])
        blended = _brier(sample[:, 0], sample[:, 2])
        delta.append(original - blended)
    result.update(recent_base_brier=_brier(recent[:, 0], recent[:, 1]),
                  recent_blend_brier=_brier(recent[:, 0], recent[:, 2]),
                  improvement=float(min(delta)))
    passes = all(gain >= 0.0015 for gain in delta)
    result["active"] = passes
    result["status"] = ("VALIDATED ON RECORDED MARKETS" if passes else
                        "OFF: No consistent Brier improvement")
    return result


def _ask_vwap(book, side, contracts=1):
    """Kalshi publishes YES and NO *bids*; the opposing bid implies an ask.

    Returns None when the displayed liquidity cannot fill the whole quantity.
    """
    if not isinstance(book, dict) or side not in ("YES", "NO"):
        return None
    opposing = book.get("no" if side == "YES" else "yes") or []
    asks = []
    for row in opposing:
        try:
            price, qty = float(row[0]), float(row[1])
            if 0 <= price <= 100 and qty > 0:
                asks.append((100-price, qty))
        except (TypeError, ValueError, IndexError):
            continue
    asks.sort()
    remaining, paid = float(contracts), 0.0
    for price, qty in asks:
        take = min(remaining, qty)
        paid += price*take
        remaining -= take
        if remaining < 1e-9:
            return paid/float(contracts)
    return None


def paper_edge_review(independent, snapshot, validated, *,
                      min_edge_cents=10, candle_stale=False,
                      market_stale=False, venues=0, dispersion_bps=None,
                      remaining_sec=None, volatility_15m_pct=None):
    """A strict research filter for ONE hypothetical hold-to-settlement contract.

    Fee is a conservative *allowance*, not the live Kalshi fee schedule.
    A paper candidate is never an authorization to enter a real trade.
    """
    result = {"status": "NO TRADE", "side": None, "net_ev_cents": None,
              "entry_cents": None, "reason": "Independent outcome probability unavailable"}
    p = probability(independent)
    if p is None or snapshot is None:
        return result
    reasons = []
    if not validated:
        reasons.append("Insufficient demonstrated improvement over existing bot")
    if candle_stale or market_stale:
        reasons.append("Stale BTC or Kalshi market data")
    if not isinstance(snapshot, dict) or snapshot.get("book_error"):
        reasons.append("Order book unavailable")
    status = (snapshot.get("market") or {}).get("status") if isinstance(snapshot, dict) else None
    if status not in ("active", "open"):
        reasons.append("Market is not open")
    remain = number(remaining_sec)
    if remain is None or remain <= 60 or remain > 900:
        reasons.append("Too close to expiry or missing expiry timestamp")
    dispersion = number(dispersion_bps)
    if number(venues, 0) < 3 or dispersion is None or dispersion > 12:
        reasons.append("Reference-exchange consensus is insufficient")
    if number(volatility_15m_pct) is None or volatility_15m_pct > 1.0:
        reasons.append("Volatility shock or unavailable 15-minute volatility")

    candidates = []
    for side, win_p in (("YES", p), ("NO", 1-p)):
        try:
            ask = number(snapshot.get(side.lower()+"_ask"))
            bid = number(snapshot.get(side.lower()+"_bid"))
            book_ask = _ask_vwap(snapshot, side)
            if (ask is None or bid is None or book_ask is None
                    or not 0 < bid <= ask < 100 or ask-bid > 4):
                continue
            entry = max(ask, book_ask)
            if book_ask > ask + 1:
                continue
            # 3c fee allowance and 2c adverse fill buffer, not a fee promise.
            fee_buffer, slippage_buffer = 3.0, 2.0
            ev = 100*win_p - entry - fee_buffer - slippage_buffer
            candidates.append((ev, side, entry))
        except (TypeError, ValueError):
            continue
    if not candidates:
        reasons.append("Wide/missing quotes or insufficient executable depth")
    else:
        ev, side, entry = max(candidates)
        result.update(side=side, net_ev_cents=round(ev, 2), entry_cents=round(entry, 2))
        if ev < max(10.0, float(min_edge_cents)):
            reasons.append("Estimated net edge below 10¢ minimum")
    if reasons:
        result["reason"] = " · ".join(reasons)
        return result
    result.update(status="PAPER CANDIDATE", reason="Research only; verify actual fees, depth, and settlement rules")
    return result


def analyze_arena(history, engine, snapshot, *,
                  min_edge_cents=10, candle_stale=False, market_stale=False,
                  volatility_15m_pct=None):
    """Create one safe, dashboard-ready comparison of the competing models."""
    model = engine if isinstance(engine, dict) else {}
    feature = {
        "stat_prob": (model.get("stat") or {}).get("prob"),
        "analog_prob": (model.get("analog") or {}).get("prob"),
        "flow_prob": model.get("flow_prob"),
    }
    independent = independent_estimate(feature)
    validation = validate_blend(history)
    old = probability(model.get("prob_above"))
    blend = .7*old + .3*independent if old is not None and independent is not None else None
    proxy = model.get("brti_proxy") or {}
    paper = paper_edge_review(independent, snapshot, validation["active"],
                              min_edge_cents=min_edge_cents, candle_stale=candle_stale,
                              market_stale=market_stale, venues=proxy.get("count", 0),
                              dispersion_bps=proxy.get("dispersion_bps"),
                              remaining_sec=model.get("remaining_sec"),
                              volatility_15m_pct=volatility_15m_pct)
    scoreboard = score_models(history)
    leader = next((row["Model"] for row in scoreboard if row["Markets"] >= 30), None)
    return {"independent_p": independent, "blend_p": blend, "blend_active": validation["active"],
            "validation": validation, "paper": paper, "scoreboard": scoreboard, "leader": leader,
            "baseline_p": old, "scored_markets": len(verified_snapshots(history))}
