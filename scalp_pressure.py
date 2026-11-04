"""Observed BTC aggressive trade flow and short-horizon pressure *heuristics*.

Coinbase trade `side` must be inverted from maker to aggressor by the caller.
Executed prints reveal what just traded, NOT orders that will arrive later.
Keep this independent of Kalshi settlement probabilities and the YES/NO strike.
"""
from datetime import datetime
import math
import time


def _timestamp(value):
    try:
        if isinstance(value, (int, float)):
            result = float(value)
        else:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def merge_spot_tape(previous, incoming, now=None, keep_seconds=100):
    """Deduplicate successive REST samples; bounded, timestamped, no look-ahead."""
    now = time.time() if now is None else float(now)
    unique = {}
    for row in list(previous or []) + list(incoming or []):
        if not isinstance(row, dict):
            continue
        trade_id = str(row.get("id") or "")
        side = str(row.get("aggressor") or "").lower()
        when = _timestamp(row.get("time"))
        try:
            amount = float(row.get("notional"))
        except (TypeError, ValueError):
            continue
        if (not trade_id or side not in ("buy", "sell") or when is None or
                not 0 <= now - when <= keep_seconds or
                not math.isfinite(amount) or amount <= 0):
            continue
        # Keep the execution price for tape/price divergence. Older callers may
        # omit it; never substitute the latest spot quote for historical prints.
        try:
            px = float(row.get("price"))
            if not math.isfinite(px) or px <= 0:
                px = None
        except (TypeError, ValueError, OverflowError):
            px = None
        previous_price = unique.get(trade_id, {}).get("price")
        unique[trade_id] = {"id": trade_id, "aggressor": side,
                            "notional": amount, "time": row["time"]}
        if px is not None or previous_price is not None:
            unique[trade_id]["price"] = px if px is not None else previous_price
    return sorted(unique.values(), key=lambda r: _timestamp(r["time"]))[-2500:]


def spot_pressure_radar(tape, structure=None, snapshot=None, quote_history=None,
                        now=None, stale=False):
    """Spot buyer/seller *pressure*, not a forecast of unknown future orders.

    Use capped executed notional in the past 20s, with a prior 60s comparison.
    Kalshi bids only CONFIRM an independent spot signal; they never create it.
    """
    now = time.time() if now is None else float(now)
    result = {"status": "COLLECTING FLOW", "bias": "UNCLEAR", "strength": "NONE",
              "reason": "Waiting for recent spot trades", "buy_share": None,
              "imbalance": None, "previous_imbalance": None, "acceleration": None,
              "buy_notional": None, "sell_notional": None, "recent_count": 0,
              "prior_count": 0, "pace_ratio": None, "kalshi_confirmation": "PENDING",
              "quote_move_cents": None, "spot_move_bps": None,
              "priced_trades": 0, "absorption_warning": False,
              "absorbed_side": None,
              "horizon": "next 30–90s (unvalidated)"}
    if stale:
        result.update(status="DATA STALE", reason="BTC trade or candle feed unavailable")
        return result
    rows = []
    for r in tape or []:
        if not isinstance(r, dict) or r.get("aggressor") not in ("buy", "sell"):
            continue
        when = _timestamp(r.get("time"))
        try:
            amount = float(r.get("notional"))
        except (TypeError, ValueError):
            continue
        if when is not None and 0 <= now - when <= 80 and math.isfinite(amount) and amount > 0:
            try:
                price = float(r.get("price"))
                if not math.isfinite(price) or price <= 0:
                    price = None
            except (TypeError, ValueError, OverflowError):
                price = None
            rows.append((now - when, str(r["aggressor"]), amount, price))
    recent = [r for r in rows if r[0] <= 20]
    prior = [r for r in rows if 20 < r[0] <= 80]
    result["recent_count"], result["prior_count"] = len(recent), len(prior)
    if len(recent) < 12 or not rows or min(r[0] for r in rows) > 12:
        result["reason"] = "Need at least 12 fresh BTC trades over the last 20 seconds"
        return result
    # Cap single massive executions so one print cannot dominate the signal.
    values = sorted(r[2] for r in rows)
    median = values[len(values) // 2]
    cap = max(median * 8, values[int((len(values)-1) * .9)])
    def sums(part):
        buy = sum(min(x[2], cap) for x in part if x[1] == "buy")
        sell = sum(min(x[2], cap) for x in part if x[1] == "sell")
        total = buy + sell
        return buy, sell, ((buy - sell) / total if total else 0.0)
    buy, sell, current = sums(recent)
    previous = sums(prior)[2] if len(prior) >= 12 else None
    delta = current - previous if previous is not None else None
    pace = (len(recent) / 20) / (len(prior) / 60) if len(prior) >= 12 else None
    result.update(buy_notional=buy, sell_notional=sell, imbalance=current,
                  buy_share=100 * buy / (buy + sell), previous_imbalance=previous,
                  acceleration=delta, pace_ratio=pace)
    # Executed flow alone cannot tell whether aggressive buyers actually moved
    # BTC higher. Compare *same-window* exchange trade prices, not delayed 1m
    # candles or Kalshi YES/NO quotes. Require enough time coverage and prints.
    priced = sorted((r for r in recent if r[3] is not None),
                    key=lambda r: r[0], reverse=True)
    result["priced_trades"] = len(priced)
    if len(priced) >= 12 and priced[0][0] - priced[-1][0] >= 8:
        oldest = sum(r[3] for r in priced[:3]) / 3
        newest = sum(r[3] for r in priced[-3:]) / 3
        result["spot_move_bps"] = 10000 * (newest / oldest - 1)
    structural = None
    if isinstance(structure, dict) and structure.get("status") != "UNAVAILABLE":
        try:
            structural = float(structure.get("evidence_score"))
            if not math.isfinite(structural):
                structural = None
        except (TypeError, ValueError):
            pass
    direction = "BUYERS" if current > 0 else "SELLERS"
    sign = 1 if current > 0 else -1
    aligned = structural is not None and structural * sign >= .25
    conflicted = structural is not None and structural * sign <= -.40
    advancing = delta is not None and delta * sign >= .12
    # Strong market buying into a falling trade price (or selling into a
    # rising one) may indicate absorption, not directional control. This is a
    # risk veto, NOT proof that a reversal or hidden order is present.
    price_move = result["spot_move_bps"]
    divergence = (price_move is not None and len(priced) >= 20
                  and abs(current) >= .35 and price_move * sign <= -1.5)
    if divergence:
        result.update(status="FLOW/PRICE DIVERGENCE · WAIT",
                      absorption_warning=True, absorbed_side=direction,
                      reason="Aggressive " + ("buying" if sign > 0 else "selling") +
                             " dominates, but BTC trade prices move the opposite way; possible absorption")
    elif abs(current) < .20:
        result.update(status="MIXED FLOW", reason="Executed buy/sell pressure is close to balanced")
    elif conflicted:
        result.update(status="CONFLICT · WAIT", reason="Spot executions oppose closed-candle structure")
    elif abs(current) >= .28 or (abs(current) >= .20 and (aligned or advancing)):
        strong = abs(current) >= .50 and len(recent) >= 20 and (aligned or advancing)
        result.update(status=("BUYING" if sign > 0 else "SELLING") + " PRESSURE BUILDING",
                      bias=direction, strength="STRONG" if strong else "MODERATE",
                      reason="Recent aggressive executions favor " + direction.lower()
                             + ("; flow accelerating" if advancing else "")
                             + ("; candle structure agrees" if aligned else ""))
    else:
        result.update(status="MIXED FLOW", reason="Directional imbalance not supported by other evidence")
    # Kalshi YES/NO prices are *not* spot buy/sell volume. Only use as a check.
    if result["bias"] in ("BUYERS", "SELLERS") and snapshot and not snapshot.get("book_error"):
        from scalp_engine import quote_trend
        side = "yes" if result["bias"] == "BUYERS" else "no"
        move = quote_trend(quote_history, side, now=now)
        result["quote_move_cents"] = move
        if move is not None:
            result["kalshi_confirmation"] = "CONFIRMING" if move >= .5 else (
                "OPPOSING" if move <= -.5 else "FLAT")
    return result
