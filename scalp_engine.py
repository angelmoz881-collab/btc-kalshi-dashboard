"""Cost-aware, manual-execution Kalshi BTC scalp research and exit monitoring.

This is deliberately separate from hold-to-settlement probability estimation.
Signals are heuristics, not calibrated short-term market-price predictions.
All cash-out P&L uses the sell-side bids and visible size, never midpoint/ask.
"""
import math
import time


def _number(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def estimated_taker_fee_cents(price_cents, quantity, multiplier=1.0):
    """Indicative standard Kalshi prediction-contract taker fee, rounded per order.

    Current official fees, series-specific multipliers, and actual trade receipts
    take precedence. This is not a universal fee quote.
    """
    p = _number(price_cents)
    m = _number(multiplier)
    q = _number(quantity)
    if p is None or q is None or m is None or not (0 <= p <= 100 and q > 0 and m >= 0):
        return None
    return int(math.ceil(max(0, 0.07 * m * q * (p / 100.0) * (1 - p / 100.0) * 100 - 1e-9)))


def marketable_exit(snapshot, side, quantity):
    """VWAP for selling the full size INTO visible YES/NO bids; no invented fills."""
    if not snapshot or snapshot.get("book_error") or str(side).lower() not in ("yes", "no"):
        return None
    q = _number(quantity)
    if q is None or q <= 0:
        return None
    bids = snapshot.get(str(side).lower()) or []
    levels = []
    for item in bids:
        try:
            price, size = _number(item[0]), _number(item[1])
            if price is not None and size is not None and 0 < price < 100 and size > 0:
                levels.append((price, size))
        except (TypeError, IndexError, KeyError):
            continue
    levels.sort(key=lambda item: item[0], reverse=True)
    visible = sum(size for _, size in levels)
    if visible + 1e-9 < q:
        return {"ok": False, "reason": "Not enough visible bid depth to sell the entire position",
                "visible": visible, "needed": q, "best_bid": levels[0][0] if levels else None}
    remaining, total = q, 0.0
    for price, size in levels:
        filled = min(remaining, size)
        total += filled * price
        remaining -= filled
        if remaining <= 1e-9:
            break
    return {"ok": True, "bid_vwap": total / q, "best_bid": levels[0][0],
            "visible": visible, "needed": q}


def quote_trend(history, side, now=None):
    """Change in actual sell-side bid over >=12 seconds. Missing != flat."""
    if str(side).lower() not in ("yes", "no"):
        return None
    now = time.time() if now is None else float(now)
    key = str(side).lower() + "_bid"
    valid = [(float(x["t"]), _number(x.get(key))) for x in history or []
             if isinstance(x, dict) and _number(x.get("t")) is not None and
             _number(x.get(key)) is not None and 0 <= now - float(x["t"]) <= 60]
    if not valid:
        return None
    valid.sort()
    old = [row for row in valid if row[0] <= now - 12]
    recent = [row for row in valid if row[0] >= now - 8]
    if not old or not recent:
        return None
    return round(recent[-1][1] - old[-1][1], 3)


def entry_watch(snapshot, score, candle_agreement, reversal, remaining_sec,
                history=None, stale=False, minimum_depth=5):
    """Separate, experimental near-term scalp WATCH; NOT an execution order."""
    result = {"status": "WAIT", "side": None, "reason": "No verified short-horizon entry edge",
              "validated": False}
    if stale or not snapshot or snapshot.get("book_error"):
        result["reason"] = "Quote or BTC feed stale / Kalshi order book unavailable"
        return result
    if (snapshot.get("market") or {}).get("status") not in ("active", "open"):
        result["reason"] = "Market is not open"
        return result
    remain = _number(remaining_sec)
    if remain is None or remain < 150 or remain > 900:
        result["reason"] = "Too close to expiration or invalid close time for short exits"
        return result
    score = _number(score)
    agreement = _number(candle_agreement)
    if score is None or agreement is None or abs(score) < 48 or agreement < 0.6:
        result["reason"] = "Momentum and completed-candle confirmation too weak"
        return result
    side = "yes" if score > 0 else "no"
    opposing = "DOWN" if side == "yes" else "UP"
    rev = reversal or {}
    if rev.get("direction") == opposing and (_number(rev.get("score")) or 0) >= 50:
        result["reason"] = "Opposing reversal evidence: avoid chasing the move"
        return result
    bid, ask = _number(snapshot.get(side + "_bid")), _number(snapshot.get(side + "_ask"))
    if bid is None or ask is None or not (0 < bid <= ask < 100) or ask - bid > 4:
        result["reason"] = "Spread wide / invalid buy and sell quotes"
        return result
    depth = marketable_exit(snapshot, side, minimum_depth)
    if not depth or not depth["ok"]:
        result["reason"] = "Insufficient executable exit-side depth"
        return result
    bid_move = quote_trend(history, side)
    if bid_move is None:
        result["reason"] = "Collecting at least 12 seconds of Kalshi bid movement"
        return result
    if bid_move < 0.5:
        result["reason"] = "Kalshi sell bids have not confirmed the BTC move"
        return result
    result.update(status=f"WATCH {side.upper()}", side=side.upper(),
                  reason=f"Experimental setup: score {score:+.0f}, bid +{bid_move:.1f}¢, spread {ask-bid:.1f}¢. No validated positive expectancy.")
    return result


def review_open_position(position, snapshot, score, reversal, remaining_sec,
                         history=None, stale=False, slippage_cents=1.0,
                         target_cents=4.0, trail_cents=2.0, stop_cents=8.0,
                         max_hold_sec=180.0, now=None):
    """Conservative manual cash-out warning and modeled net proceeds for FULL size.

    Position: ticker, side, quantity, entry_price_cents, entry_fee_cents, opened_at,
    peak_net_cents (per contract), entry_score. Never submits trades.
    """
    now = time.time() if now is None else float(now)
    out = {"status": "NO QUOTE", "reason": "Missing sell quote", "net_cents": None,
           "net_total_dollars": None, "exit_bid_cents": None, "breakeven_bid_cents": None,
           "target_bid_cents": None, "peak_net_cents": _number(position.get("peak_net_cents")) or 0,
           "actionable": False}
    side = str(position.get("side", "")).lower()
    q = _number(position.get("quantity"))
    entry = _number(position.get("entry_price_cents"))
    entry_fee = _number(position.get("entry_fee_cents"))
    remain = _number(remaining_sec)
    if side not in ("yes", "no") or q is None or q < 1 or entry is None or not (0 < entry < 100):
        out.update(status="INVALID POSITION", reason="Enter an actual filled side, size, and purchase price")
        return out
    if entry_fee is None or entry_fee < 0:
        out.update(status="INVALID POSITION", reason="Entry fee must be nonnegative")
        return out
    if stale:
        out.update(status="DATA STALE", reason="Do not act on a cached bid; refresh or check Kalshi directly")
        return out
    if remain is None or remain <= 0:
        out.update(status="EXPIRED", reason="Market closed; check settlement or a previously filled exit")
        return out
    if (snapshot or {}).get("market", {}).get("status") not in ("active", "open"):
        out.update(status="MARKET CLOSED", reason="Market not open for manual exit")
        return out
    exit_book = marketable_exit(snapshot, side, q)
    if not exit_book or not exit_book.get("ok"):
        out.update(status="LIQUIDITY WARNING",
                   reason=(exit_book or {}).get("reason", "No live executable bid ladder"),
                   visible=(exit_book or {}).get("visible", 0))
        return out
    bid = float(exit_book["bid_vwap"])
    exit_fee = estimated_taker_fee_cents(bid, q)
    if exit_fee is None:
        return out
    slip = max(0.0, _number(slippage_cents) or 0.0)
    target = max(0.0, _number(target_cents) or 0.0)
    trail = max(0.0, _number(trail_cents) or 0.0)
    stop = max(0.0, _number(stop_cents) or 0.0)
    elapsed = max(0.0, now - (_number(position.get("opened_at")) or now))
    net_total = (bid - entry - slip) * q - entry_fee - exit_fee
    net = net_total / q
    old_peak = max(0.0, _number(position.get("peak_net_cents")) or 0.0)
    peak = max(old_peak, net)
    current_score = _number(score) or 0
    entry_score = _number(position.get("entry_score"))
    directional_score = current_score * (1 if side == "yes" else -1)
    initial_dir_score = (entry_score * (1 if side == "yes" else -1)) if entry_score is not None else None
    score_fading = initial_dir_score is not None and initial_dir_score - directional_score >= 18
    opposing = "DOWN" if side == "yes" else "UP"
    rev = reversal or {}
    reversal_against = rev.get("direction") == opposing and (_number(rev.get("score")) or 0) >= 50
    quote_delta = quote_trend(history, side, now)
    bid_falling = quote_delta is not None and quote_delta <= -1.0
    warning = score_fading or directional_score <= 10 or reversal_against or bid_falling
    reasons = []
    if score_fading: reasons.append("entry momentum weakening")
    if directional_score <= 10: reasons.append("directional support weak")
    if reversal_against: reasons.append("opposing reversal clues")
    if bid_falling: reasons.append(f"sell bid {quote_delta:+.1f}¢ vs recent history")
    if not reasons: reasons.append("profit/risk thresholds monitored")
    out.update(net_cents=net, net_total_dollars=net_total / 100.0,
               exit_bid_cents=bid, best_bid_cents=exit_book["best_bid"],
               exit_fee_cents=exit_fee, entry_fee_cents=entry_fee,
               breakeven_bid_cents=entry + slip + (entry_fee + exit_fee) / q,
               target_bid_cents=entry + slip + (entry_fee + exit_fee) / q + target,
               peak_net_cents=peak, bid_move_cents=quote_delta,
               elapsed_sec=elapsed, available_depth=exit_book["visible"],
               actionable=True)
    if net >= target and target > 0:
        status = "TAKE PROFIT"
        reason = "Target reached at visible bids after estimated fees and slippage; submit a manual exit before quotes change"
    elif net > 0 and peak - net >= trail and peak > 0 and trail > 0:
        status = "PROTECT PROFIT"
        reason = "Net profit has fallen from the best observed sellable level; " + ", ".join(reasons)
    elif remain <= 75:
        status = "EXIT WINDOW CLOSING"
        reason = "Less than 75 seconds remain; no reliable time to recover before the contract closes"
    elif net > 0 and (bid_falling or reversal_against or directional_score < 0):
        status = "CASH OUT SOON"
        reason = "Positive net at visible bids but adverse early warning: " + ", ".join(reasons)
    elif net > 0 and net >= 0.6 * target and warning:
        status = "PREPARE TO CASH"
        reason = "Positive net is close to target and conditions are deteriorating: " + ", ".join(reasons)
    elif net <= -stop and stop > 0:
        status = "STOP LOSS REVIEW"
        reason = "Estimated loss exceeded manual loss budget. An immediate sale may lock in this loss."
    elif elapsed >= max_hold_sec:
        status = "TIME EXIT REVIEW"
        reason = "Configured maximum scalp duration elapsed; reassess rather than holding to settlement"
    else:
        status = "MONITOR EXIT"
        reason = "Exit estimate based on full-position visible bids, not a guaranteed fill"
    out.update(status=status, reason=reason)
    return out
