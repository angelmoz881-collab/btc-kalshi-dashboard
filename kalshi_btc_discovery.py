"""Discover the live Kalshi 15-minute BTC contract without guessing tickers.

Uses documented /markets plus /events?with_nested_markets=true, on the
existing and Kalshi's canonical public Trade API host. Only OPEN, currently
trading KXBTC15M contracts may be selected. Unopened and expired contracts
are never silently substituted for live tickers.
"""
from datetime import datetime, timezone
from collections.abc import Mapping

SERIES = "KXBTC15M"
HOSTS = (
    "https://api.elections.kalshi.com/trade-api/v2",
    "https://external-api.kalshi.com/trade-api/v2",
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
    if status != "open":
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


def _load_pages(get, host, endpoint, params, errors, max_pages=3):
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


def discover_btc_markets(get, now=None, hosts=HOSTS):
    """Return {"markets": [...], "source": ..., "errors": [...], "status": ...}.

    A selected ticker is always an actual market ticker provided by Kalshi,
    never a generated ticker and never merely an event/series ticker.
    """
    now = _utc(now) if now is not None else datetime.now(timezone.utc)
    errors = []
    for host in hosts:
        rows = _load_pages(
            get, host, "markets",
            {"series_ticker": SERIES, "status": "open", "mve_filter": "exclude", "limit": 200},
            errors,
        )
        valid = {}
        for m in rows:
            if isinstance(m, Mapping):
                item = dict(m)
                # Endpoint explicitly filters to status=open. Some API variants
                # omit status on an abbreviated item; the filter is authoritative.
                item.setdefault("status", "open")
                if live_btc_market(item, now):
                    valid[item["ticker"]] = item
        if valid:
            return _result(valid, "Kalshi markets", errors)
        # When /markets is temporarily empty, query the parent events with
        # nested markets instead of fabricating an active 15m ticker.
        events = _load_pages(
            get, host, "events",
            {"series_ticker": SERIES, "status": "open",
             "with_nested_markets": "true", "limit": 200},
            errors,
        )
        for event in events:
            if not isinstance(event, Mapping) or str(event.get("series_ticker") or SERIES).upper() != SERIES:
                continue
            for m in event.get("markets") or []:
                if not isinstance(m, Mapping):
                    continue
                item = dict(m)
                item.setdefault("status", str(event.get("status") or "open"))
                if live_btc_market(item, now):
                    valid[item["ticker"]] = item
        if valid:
            return _result(valid, "Kalshi nested events", errors)
    return {
        "markets": [], "source": "none", "errors": errors,
        "status": ("Kalshi API lookup failed or returned no usable markets"
                   if errors else "Kalshi returned no currently open BTC 15-minute contracts"),
    }


def _result(markets, source, errors):
    ordered = sorted(markets.values(), key=lambda m: (close_time(m), m["ticker"]))
    return {"markets": ordered, "source": source, "errors": errors, "status": "LIVE"}
