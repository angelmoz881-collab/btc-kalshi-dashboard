"""Live external-bot consensus gate for KXBTC15M, NOT a local-model ensemble.

Only independently configured, authenticated third-party providers count as bots.
Cotes/SpectralEdge is a documented provider; optional second/third feeds must
publish independent, real-time signals via the documented JSON contract.
Each provider gets at most one vote, no matter how many signals it emits.
Neither same-provider model versions nor local algorithms increase the vote total.

This module can only read external predictions. It never places Kalshi orders.
"""
from __future__ import annotations

from datetime import datetime, timezone
from ipaddress import ip_address
from urllib.parse import urlsplit

import requests

MAX_AGE_SECONDS = 90
MIN_DISTINCT_PROVIDERS = 2
COTES_HOST = "https://api.cotes.ai"
COTES_SOURCE = "SpectralEdge / Cotes AI"


def _now(now=None):
    return now if now is not None else datetime.now(timezone.utc)


def _utc(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _direction(raw):
    if not isinstance(raw, str):
        return None
    return {"UP": "YES", "YES": "YES", "ABOVE": "YES",
            "DOWN": "NO", "NO": "NO", "BELOW": "NO"}.get(raw.strip().upper())


def _confidence(raw):
    try:
        p = float(raw)
        if p > 1:
            p /= 100
        if 0.0 <= p <= 1.0:
            return p
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def _valid_time(raised_at, now, ttl):
    t = _utc(raised_at)
    if t is None:
        return None
    seconds_old = (now - t).total_seconds()
    if seconds_old < -5 or seconds_old > ttl:
        return None
    return int(max(0, seconds_old))


def _vote(source, ticker, side, confidence, time_value, *, now, max_age=MAX_AGE_SECONDS):
    age = _valid_time(time_value, now, max_age)
    side = _direction(side)
    conf = _confidence(confidence)
    if age is None or not side or conf is None or conf < 0.55:
        return None
    return {"Source": source, "Ticker": ticker, "Vote": side,
            "Confidence": round(conf*100, 1), "Age (s)": age}


def parse_cotes(payload, ticker, *, now=None, max_age=MAX_AGE_SECONDS):
    """Extract ONE latest eligible Cotes signal for the EXACT Kalshi ticker."""
    now = _now(now)
    if (not isinstance(payload, dict) or payload.get("ticker") != ticker
            or payload.get("state") != "live"
            or not isinstance(payload.get("signals"), list)):
        return None
    eligible = []
    for entry in payload["signals"]:
        if not isinstance(entry, dict):
            continue
        if entry.get("ticker") != ticker or entry.get("outcome") not in ("pending", None):
            continue
        v = _vote(COTES_SOURCE, ticker, entry.get("side"), entry.get("confidence"),
                  entry.get("raised_at"), now=now, max_age=max_age)
        if v:
            eligible.append((entry["raised_at"], v))
    if not eligible:
        return None
    # Multiple emissions by the same provider are a single vote: latest wins.
    return max(eligible, key=lambda item: item[0])[1]


def parse_partner(payload, ticker, source, *, now=None, max_age=MAX_AGE_SECONDS):
    """Partner feed schema: {"ticker","side","confidence","timestamp"}.

    The feed must be a separately operated prediction service. Kalshi quotes
    or renamed copies of the same Cotes signal are not independent votes.
    """
    if not isinstance(payload, dict) or payload.get("ticker") != ticker:
        return None
    if payload.get("status", "live") != "live":
        return None
    return _vote(source, ticker, payload.get("side"), payload.get("confidence"),
                 payload.get("timestamp"), now=_now(now), max_age=max_age)


def _partner_url(url):
    parsed = urlsplit(str(url or ""))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        return None
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "api.cotes.ai"} or host.endswith((".local", ".localhost", ".internal")):
        return None
    try:
        addr = ip_address(host)
        # HTTP links to private or local IPs must never be fetched.
        if not addr.is_global:
            return None
    except ValueError:
        pass
    return url


def _get(url, *, token=None, params=None, session=None):
    cli = session if session is not None else requests
    headers = {"Accept": "application/json", "User-Agent": "BTC-Bot-Consensus/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + str(token)
    response = cli.get(url, headers=headers, params=params, timeout=6,
                       allow_redirects=False)
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Non-object signal response")
    return payload


def fetch_external_votes(ticker, config, *, now=None, session=None):
    """Return (votes, status) from explicitly configured independent providers.

    Config is the secret dictionary; providers 2 and 3 require different hosts.
    Failures never become YES/NO, and credential contents are never returned.
    """
    now = _now(now)
    if not isinstance(ticker, str) or not ticker.startswith("KXBTC15M-"):
        return [], ["Waiting for exact KXBTC15M market ticker"]
    votes, status = [], []
    cotes_key = config.get("COTES_API_KEY")
    if cotes_key:
        try:
            payload = _get(COTES_HOST + "/v1/contests/active", token=cotes_key,
                           params={"series": "KXBTC15M"}, session=session)
            vote = parse_cotes(payload, ticker, now=now)
            if vote:
                votes.append(vote)
                status.append("Cotes: live verified signal")
            else:
                status.append("Cotes: no fresh signal for this ticker")
        except (requests.RequestException, RuntimeError, ValueError):
            status.append("Cotes: API temporarily unavailable")
    else:
        status.append("Cotes: API key not configured")

    unique_hosts = {"api.cotes.ai"}
    for number in (2, 3):
        address = _partner_url(config.get(f"BOT_SIGNAL_URL_{number}"))
        bearer = config.get(f"BOT_SIGNAL_TOKEN_{number}")
        if not address:
            status.append(f"Partner {number}: HTTPS feed not configured")
            continue
        host = urlsplit(address).hostname.lower().rstrip(".")
        if host in unique_hosts:
            status.append(f"Partner {number}: duplicate host, cannot count twice")
            continue
        unique_hosts.add(host)
        try:
            data = _get(address, token=bearer, params={"ticker": ticker}, session=session)
            source = f"Partner {number} · {host}"
            vote = parse_partner(data, ticker, source, now=now)
            if vote:
                votes.append(vote)
                status.append(f"Partner {number}: live verified signal")
            else:
                status.append(f"Partner {number}: stale or mismatched signal")
        except (requests.RequestException, RuntimeError, ValueError):
            status.append(f"Partner {number}: API temporarily unavailable")
    return votes, status


def vote_consensus(votes, *, ticker, model_probability=None,
                   min_voters=MIN_DISTINCT_PROVIDERS, local_veto=True):
    """ONLY external provider votes decide side; local estimate can VETO, not vote.

    A contradictory bot blocks trading. Missing provider is not counted as approval.
    Rejects duplicate provider names and market mismatches defensively.
    """
    valid = []
    seen = set()
    for item in votes or []:
        if not isinstance(item, dict) or item.get("Ticker") != ticker:
            continue
        source, side = item.get("Source"), item.get("Vote")
        if not isinstance(source, str) or not source or source in seen or side not in ("YES", "NO"):
            continue
        try:
            age = float(item.get("Age (s)", float("inf")))
            conf = float(item.get("Confidence", 0))
        except (TypeError, ValueError, OverflowError):
            continue
        if not 0 <= age <= MAX_AGE_SECONDS or not 55 <= conf <= 100:
            continue
        seen.add(source)
        valid.append(item)
    yes = sum(v["Vote"] == "YES" for v in valid)
    no = sum(v["Vote"] == "NO" for v in valid)
    vote_count = len(valid)
    base = {"status": "WAIT", "side": None, "yes": yes, "no": no,
            "total": vote_count, "required": min_voters, "votes": valid,
            "reason": ""}
    if vote_count < min_voters:
        base["reason"] = f"Only {vote_count}/{min_voters} distinct external bots reporting"
        return base
    if yes and no:
        base["reason"] = "External bots disagree; no directional prediction"
        return base
    direction = "YES" if yes == vote_count else "NO"
    if local_veto:
        p = _confidence(model_probability)
        # Existing internal model never supplies an agreeing vote or direction.
        # When it strongly contradicts, abstain.
        if p is not None and ((direction == "YES" and p < .35) or
                              (direction == "NO" and p > .65)):
            base["reason"] = "Local market/risk analysis strongly contradicts external bots"
            return base
    return dict(base, status="AGREE", side=direction,
                reason=f"{vote_count} distinct external feeds agree on {direction}")


def apply_consensus_to_engine(engine, consensus):
    """Replace public OUTCOME call with external consensus; leave research models visible."""
    updated = dict(engine)
    updated["original_model_outcome"] = engine.get("outcome", "UNCERTAIN")
    updated["external_consensus"] = consensus
    if consensus.get("status") == "AGREE":
        side = consensus["side"]
        updated["outcome"] = "ABOVE · BOT AGREEMENT" if side == "YES" else "BELOW · BOT AGREEMENT"
    else:
        updated["outcome"] = "WAIT · NO EXTERNAL BOT AGREEMENT"
        updated["trade_review"] = {"summary": "NO TRADE · external bot agreement missing",
                                   "reason": consensus.get("reason", "Not enough live bot votes")}
    # A separate early-exit trading worker must use the same consensus gate; no
    # automated order submission occurs anywhere in the BTC dashboard.
    updated["scalp"] = "WAIT"
    return updated
