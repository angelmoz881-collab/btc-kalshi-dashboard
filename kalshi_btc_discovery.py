"""Discover the live Kalshi 15-minute BTC contract without guessing tickers.

Uses documented /markets plus /events?with_nested_markets=true, on the
existing and Kalshi's canonical public Trade API host. Only OPEN, currently
trading KXBTC15M contracts may be selected. Unopened and expired contracts
are never silently substituted for live tickers.
"""
from datetime import datetime, timezone, timedelta
from collections.abc import Mapping

SERIES = "KXBTC15M"
HOSTS = (
    # Preferred documented public endpoint; older elections host is fallback.
    "https://external-api.kalshi.com/trade-api/v2",
    "https://api.elections.kalshi.com/trade-api/v2",
)


def _utc(value):
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, ValueError, OSError):
            return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def close_time(market):
    for field in ("close_time", "expiration_time", "expected_expiration_time",
                  "latest_expiration_time", "close_ts"):
        value = _utc(market.get(field))
        if value is not None:
            return value
    return None


def live_btc_market(market, now=None):
    if not isinstance(market, Mapping):
        return False
    ticker = str(market.get("ticker") or "").upper()
    if not ticker.startswith(SERIES + "-"):
        return False
    status = str(market.get("status") or "").lower()
    if status not in ("active", "open"):
        return False
    now = _utc(now) if now is not None else datetime.now(timezone.utc)
    closing = close_time(market)
    if closing is None or (closing - now).total_seconds() <= 2:
        return False
    opening = _utc(market.get("open_time") or market.get("open_ts"))
    # Status is also required: a future listing isn't a tradable window.
    if opening is not None and opening > now:
        return False
    return True


def _load_pages(get, host, endpoint, params, errors, max_pages=2):
    """Fetch a bounded number of cursor pages, stopping once data is nonempty."""
    cursor = None
    seen = set()
    collected = []
    for _ in range(max_pages):
        query = dict(params)
        if cursor:
            query["cursor"] = cursor
        try:
            response = get(f"{host}/{endpoint}", params=query, timeout=8)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, Mapping) or not isinstance(payload.get(endpoint), list):
                errors.append(f"{host.split('/')[2]} {endpoint}: unexpected API response")
                break
            collected.extend(payload[endpoint])
            # Surface actual empty responses to distinguish "no live markets"
            # from a response format problem or a connectivity failure.
            cursor = payload.get("cursor")
            if not cursor or not isinstance(cursor, str) or cursor in seen:
                break
            seen.add(cursor)
        except Exception as exc:
            response_obj = getattr(exc, "response", None)
            status_code = getattr(response_obj, "status_code", None)
            err = f"HTTP {status_code}" if status_code else type(exc).__name__
            errors.append(f"{host.split('/')[2]} {endpoint}: {err}")
            break
    return collected


def _event_candidates(now):
    """Candidate EVENT tickers only; never invent or select a market ticker."""
    quarter = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    # Kalshi's 15m event tickers encode their window time. Try nearby
    # boundaries, then rely entirely on Kalshi's actual returned child market.
    return [
        (quarter + timedelta(minutes=15 * step)).strftime(
            "KXBTC15M-%y%b%d%H%M"
        ).upper()
        for step in (0, 1, 2, -1)
    ]


def _from_event_response(payload, now):
    """Accept both /events response layouts (nested or top-level markets)."""
    if not isinstance(payload, Mapping):
        return []
    event = payload.get("event") or {}
    if not isinstance(event, Mapping):
        return []
    if str(event.get("series_ticker") or SERIES).upper() != SERIES:
        return []
    markets = event.get("markets")
    if not isinstance(markets, list):
        markets = payload.get("markets") or []
    accepted = []
    for m in markets:
        if not isinstance(m, Mapping):
            continue
        item = dict(m)
        item.setdefault("status", event.get("status") or "open")
        if live_btc_market(item, now):
            accepted.append(item)
    return accepted


def _direct_event_lookup(get, host, now, errors):
    """Try published 15-minute event windows via Kalshi; verify child markets.

    A candidate event identifier is NOT a market ticker. We only return the
    real market ticker from the API after validating its trading status/times.
    """
    results = {}
    for event_id in _event_candidates(now):
        try:
            r = get(
                f"{host}/events/{event_id}",
                params={"with_nested_markets": "true"}, timeout=4,
            )
            if getattr(r, "status_code", None) == 404:
                continue
            r.raise_for_status()
            payload = r.json()
            for item in _from_event_response(payload, now):
                results[item["ticker"]] = item
        except Exception as exc:
            response = getattr(exc, "response", None)
            code = getattr(response, "status_code", None)
            if code != 404:
                errors.append(
                    f"{host.split('/')[2]} direct event: HTTP {code}"
                    if code else f"{host.split('/')[2]} direct event: {type(exc).__name__}"
                )
                # A connection failure is not fixed by asking this host for
                # four adjacent events.
                if code in (403, 429, 500, 502, 503, 504) or code is None:
                    break
    return results


def discover_btc_markets(get, now=None, hosts=HOSTS):
    """Find Kalshi-confirmed currently-open BTC 15-minute market tickers.

    Three Kalshi routes are attempted: filtered /markets, nested /events,
    then direct /events/{event_ticker} around the current UTC window.
    """
    now = _utc(now) if now is not None else datetime.now(timezone.utc)
    errors = []
    diagnostics = []
    for host in hosts:
        rows = _load_pages(
            get, host, "markets",
            {"series_ticker": SERIES, "status": "open", "limit": 200},
            errors,
        )
        valid = {}
        for m in rows:
            if isinstance(m, Mapping):
                item = dict(m)
                item.setdefault("status", "active")
                if live_btc_market(item, now):
                    valid[item["ticker"]] = item
        diagnostics.append(f"{host.split('/')[2]} markets: {len(rows)} returned / {len(valid)} usable")
        if valid:
            return _result(valid, "Kalshi markets", errors, diagnostics)

        events = _load_pages(
            get, host, "events",
            {"series_ticker": SERIES, "status": "open",
             "with_nested_markets": "true", "limit": 200},
            errors,
        )
        for event in events:
            if not isinstance(event, Mapping) or str(event.get("series_ticker") or SERIES).upper() != SERIES:
                continue
            nested = event.get("markets") or []
            for m in nested:
                if not isinstance(m, Mapping):
                    continue
                item = dict(m)
                item.setdefault("status", event.get("status") or "open")
                if live_btc_market(item, now):
                    valid[item["ticker"]] = item
        diagnostics.append(f"{host.split('/')[2]} events: {len(events)} returned / {len(valid)} usable")
        if valid:
            return _result(valid, "Kalshi nested events", errors, diagnostics)

        direct = _direct_event_lookup(get, host, now, errors)
        diagnostics.append(f"{host.split('/')[2]} direct events: {len(direct)} usable")
        if direct:
            return _result(direct, "Kalshi direct event", errors, diagnostics)

    return {
        "markets": [], "source": "none", "errors": errors,
        "diagnostics": diagnostics,
        "status": ("Kalshi API request errors" if errors
                   else "Kalshi returned no currently open KXBTC15M contracts"),
    }


def _result(markets, source, errors, diagnostics=None):
    ordered = sorted(markets.values(), key=lambda m: (close_time(m), m["ticker"]))
    return {"markets": ordered, "source": source, "errors": errors,
            "diagnostics": diagnostics or [], "status": "LIVE"}
