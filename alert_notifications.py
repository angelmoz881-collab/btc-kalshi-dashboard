"""Small, opt-in alerts for existing BTC/Kalshi research signals.

This module does NOT create signals, place orders, or watch the market on its
own. Dashboard polling must be running for alerts to be evaluated/sent.
"""
from __future__ import annotations

import math
import time

import requests


EXIT_ALERTS = {
    "TAKE PROFIT": ("💰", 0),
    "PROTECT PROFIT": ("🛡️", 0),
    "CASH OUT SOON": ("⚠️", 0),
    "STOP LOSS REVIEW": ("🚨", 0),
    "EXIT WINDOW CLOSING": ("⏳", 0),
    "LIQUIDITY WARNING": ("🚨", 0),
    "DATA STALE": ("⚠️", 0),
    "PREPARE TO CASH": ("⚠️", 1),
    "TIME EXIT REVIEW": ("⏳", 1),
}


def _finite(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _alert(kind, ticker, source, event_id, title, detail, priority, icon):
    label = "LIVE" if source == "KALSHI LIVE" else "PAPER"
    return {
        "kind": kind, "key": f"{ticker}|{label}|{kind}|{event_id}",
        "ticker": ticker, "source": label, "title": title, "detail": detail,
        "priority": priority, "icon": icon,
        "message": f"{icon} BTC/Kalshi {label}: {title}\n"
                   f"Contract: {ticker}\n{detail}\n"
                   "Research alert; quotes and signals can change. No order placed.",
    }


def build_signal_alerts(ticker, watch=None, exit_report=None, pressure=None,
                        reversal=None, source="SIMULATED", stale=False):
    """Build alert candidates from existing outputs; never manufacture a signal."""
    if not ticker:
        return []
    events = []
    report = exit_report if isinstance(exit_report, dict) else {}
    status = str(report.get("status") or "")
    if status in EXIT_ALERTS:
        icon, priority = EXIT_ALERTS[status]
        details = []
        net = _finite(report.get("net_cents")) if report.get("actionable") else None
        total = _finite(report.get("net_total_dollars")) if report.get("actionable") else None
        if net is not None:
            details.append(f"Estimated net if sold: {net:+.1f}¢ per contract")
        if total is not None:
            details.append(f"Estimated total: ${total:+.2f}")
        reason = str(report.get("reason") or "").strip()
        if reason:
            details.append(reason[:250])
        if not details:
            details.append("Review the current market and your position.")
        events.append(_alert("exit", ticker, source, status, status,
                             "\n".join(details), priority, icon))

    if stale:
        return sorted(events, key=lambda x: x["priority"])

    # Existing entry_watch already checks momentum, spreads, depth, expiry, and
    # conflicting spot flow. Never alert on a WAIT or unclear signal.
    watch = watch if isinstance(watch, dict) else {}
    side = str(watch.get("side") or "").upper()
    if not report and side in ("YES", "NO") and watch.get("status") == "WATCH " + side:
        events.append(_alert("entry", ticker, source, side,
                             f"ENTRY WATCH {side}",
                             "Potential scalp setup; check actual bid/ask, fees and risk before acting.",
                             2, "🔔"))

    # Executed BTC flow measures recent transactions, NOT future buy/sell orders.
    pressure = pressure if isinstance(pressure, dict) else {}
    flow_status = str(pressure.get("status") or "")
    strength = str(pressure.get("strength") or "")
    if flow_status == "FLOW/PRICE DIVERGENCE · WAIT":
        details = str(pressure.get("reason") or "Possible aggressive-flow absorption.")
        events.append(_alert("pressure", ticker, source, "DIVERGENCE",
                             "FLOW/PRICE DIVERGENCE", details[:240], 1, "⚠️"))
    elif flow_status == "CONFLICT · WAIT":
        events.append(_alert("pressure", ticker, source, "CONFLICT",
                             "FLOW CONFLICT", str(pressure.get("reason") or "Candle and trade-flow signals disagree.")[:240],
                             2, "⚠️"))
    elif strength == "STRONG" and flow_status in ("BUYING PRESSURE BUILDING", "SELLING PRESSURE BUILDING"):
        direction = "BUYERS" if flow_status.startswith("BUYING") else "SELLERS"
        share = _finite(pressure.get("buy_share"))
        suffix = f" · observed buy share {share:.0f}%" if share is not None else ""
        events.append(_alert("pressure", ticker, source, direction,
                             f"{direction} PRESSURE BUILDING",
                             f"Strong recent BTC aggressor flow{suffix}. Not a confirmed future move.",
                             3, "📊"))

    reversal = reversal if isinstance(reversal, dict) else {}
    reverse_direction = str(reversal.get("direction") or "").upper()
    reverse_status = str(reversal.get("status") or "")
    reverse_score = _finite(reversal.get("score"))
    if (reverse_direction in ("UP", "DOWN") and reverse_score is not None
            and reverse_score >= 56
            and ("POSSIBLE REVERSAL" in reverse_status or "STRONG WATCH" in reverse_status)):
        events.append(_alert("reversal", ticker, source, reverse_direction,
                             f"POSSIBLE BTC REVERSAL {reverse_direction}",
                             f"Reversal evidence score {reverse_score:.0f}/100. Not a guaranteed turn.",
                             2, "🔄"))
    return sorted(events, key=lambda x: x["priority"])


def pick_new_alert(events, state=None, now=None, global_gap_sec=12):
    """At most one new alert per refresh; one alert per continuous episode.

    A signal must disappear before the same notification can be delivered
    again, and a per-key cooldown also applies after disappearance/re-entry.
    A changed exit status is a new episode. Priority-zero safety alerts can
    override the global gap.
    """
    now = time.time() if now is None else float(now)
    state = dict(state or {})
    available = {event["key"] for event in events}
    active = set(state.get("active", [])) & available
    last = dict(state.get("last", {}))
    global_last = float(state.get("global_last", -1e12))
    cooldowns = {"exit": 45, "entry": 150, "pressure": 180, "reversal": 180}
    selected = None
    for event in sorted(events, key=lambda x: x["priority"]):
        key = event["key"]
        if key in active:
            continue
        if now - float(last.get(key, -1e12)) < cooldowns.get(event["kind"], 180):
            continue
        if event["priority"] != 0 and now - global_last < global_gap_sec:
            continue
        selected = event
        active.add(key)
        last[key] = now
        global_last = now
        break
    # Bound per-session history; the market contract key prevents cross-market
    # suppression and old keys never accumulate indefinitely.
    last = dict(sorted(last.items(), key=lambda item: item[1], reverse=True)[:120])
    return selected, {"active": sorted(active), "last": last,
                      "global_last": global_last}


def send_telegram_message(bot_token, chat_id, message, post=None):
    """Best-effort Telegram delivery. NEVER return/log credentials or raw URLs."""
    if not bot_token or not chat_id or not message:
        return False
    sender = post or requests.post
    try:
        response = sender(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data={"chat_id": str(chat_id), "text": str(message)[:4096],
                  "disable_web_page_preview": "true"},
            timeout=3,
        )
        response.raise_for_status()
        payload = response.json()
        return isinstance(payload, dict) and payload.get("ok") is True
    except (requests.RequestException, ValueError, TypeError):
        # Some HTTP errors contain the Bot API URL (and thus the secret token).
        # Swallow them rather than surfacing raw exception details in the app.
        return False
