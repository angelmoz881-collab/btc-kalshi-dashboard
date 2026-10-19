"""Automatic research-only paper entry/exit lifecycle on observed Kalshi quotes."""
import time

from scalp_engine import estimated_taker_fee_cents, marketable_exit, review_open_position


def marketable_entry(snapshot, side, quantity=1):
    """Executable-at-snapshot buy VWAP from opposite-side bid depth."""
    side = str(side).lower()
    if side not in ("yes", "no") or not snapshot or snapshot.get("book_error"):
        return None
    opposite = "no" if side == "yes" else "yes"
    bids = (snapshot.get(opposite) or [])
    converted = {"market": snapshot.get("market"), "book_error": snapshot.get("book_error"),
                 side: [(100 - float(price), float(size)) for price, size in bids
                        if 0 < float(price) < 100 and float(size) > 0]}
    # Unlike selling, BUY consumes cheapest implied asks first. Do not use
    # marketable_exit's descending price order.
    try:
        qty = float(quantity)
        asks = sorted(converted[side], key=lambda x: x[0])
        if qty <= 0 or not asks or sum(q for _, q in asks) + 1e-8 < qty:
            return None
        left, cost = qty, 0
        for price, available in asks:
            take = min(left, available)
            cost += price * take
            left -= take
            if left <= 1e-8:
                break
        return cost / qty
    except (ValueError, TypeError):
        return None


def paper_step(state, ticker, snapshot, watch, score, reversal, remaining_sec,
               history, stale=False, now=None, slippage_cents=1,
               target_cents=5, trail_cents=2, stop_cents=8,
               max_hold_sec=180):
    """A single deterministic research tick. Return state, event; NO real orders.

    Quote-derived paper buys only after two separate confirmed watches at least
    two seconds apart. Paper exits are valued at OBSERVED sell bids, and are not
    treated as real fills. Closed trades block reentry on the same 15m ticker.
    """
    now = time.time() if now is None else float(now)
    state = dict(state or {})
    state.setdefault("history", [])
    event = None
    active = state.get("position")
    if active is not None:
        if stale or active.get("ticker") != ticker or not snapshot:
            state["exit_review"] = {"status": "DATA STALE", "actionable": False,
                                    "reason": "No fresh quote for paper position"}
            return state, event
        report = review_open_position(
            active, snapshot, score, reversal, remaining_sec, history=history,
            stale=stale, slippage_cents=slippage_cents, target_cents=target_cents,
            trail_cents=trail_cents, stop_cents=stop_cents, max_hold_sec=max_hold_sec, now=now,
        )
        state["exit_review"] = report
        if report.get("actionable"):
            active["peak_net_cents"] = report["peak_net_cents"]
            state["position"] = active
        terminal = {"TAKE PROFIT", "PROTECT PROFIT", "CASH OUT SOON",
                    "STOP LOSS REVIEW", "EXIT WINDOW CLOSING", "TIME EXIT REVIEW"}
        if report.get("actionable") and report["status"] in terminal:
            event = dict(ticker=ticker, side=active["side"].upper(), entry_cents=active["entry_price_cents"],
                         exit_cents=report["exit_bid_cents"], net_cents=report["net_cents"],
                         entered_at=active["opened_at"], exited_at=now, label="SIMULATED",
                         exit_reason=report["status"])
            state["history"] = (state["history"] + [event])[-100:]
            state["position"] = None
            state["cooldown_ticker"] = ticker
            state["last_closed"] = event
        elif report["status"] in ("EXPIRED", "MARKET CLOSED"):
            event = {"ticker": ticker, "side": active["side"].upper(),
                     "label": "PAPER INCOMPLETE", "exit_reason": "No verified exit fill",
                     "entered_at": active["opened_at"], "exited_at": now, "net_cents": None}
            state["history"] = (state["history"] + [event])[-100:]
            state["position"] = None
            state["cooldown_ticker"] = ticker
            state["last_closed"] = event
        return state, event

    state["exit_review"] = None
    side = str((watch or {}).get("side") or "").lower()
    if stale or not ticker or state.get("cooldown_ticker") == ticker or not snapshot:
        state["arming"] = None
        return state, event
    if side not in ("yes", "no") or (watch or {}).get("status") != "WATCH " + side.upper():
        state["arming"] = None
        return state, event
    remaining = float(remaining_sec or 0)
    if remaining < 150:
        state["arming"] = None
        return state, event
    ask = marketable_entry(snapshot, side, quantity=1)
    if ask is None or ask >= 99.0 or ask <= 1.0:
        state["arming"] = None
        return state, event
    arm = state.get("arming") or {}
    if arm.get("ticker") != ticker or arm.get("side") != side:
        state["arming"] = {"ticker": ticker, "side": side, "since": now}
        return state, event
    if now - float(arm.get("since", now)) < 2:
        return state, event
    # A synthetic 1-contract position is NOT a real account position or fill.
    state["position"] = {
        "ticker": ticker, "side": side, "quantity": 1,
        "entry_price_cents": ask,
        "entry_fee_cents": estimated_taker_fee_cents(ask, 1),
        "opened_at": now, "entry_score": score, "peak_net_cents": 0,
        "source": "SIMULATED",
    }
    state["arming"] = None
    event = {"ticker": ticker, "side": side.upper(), "price_cents": ask, "label": "SIMULATED ENTRY",
             "reason": "Two confirmed entry watches; hypothetical ask only",
             "time": now}
    return state, event
