"""Resolve the BTC15M target from Kalshi's market metadata, not Coinbase spot.

This module never manufactures a strike from the ticker, live BTC quote,
market-implied odds, or an earlier contract. If Kalshi has not published the
opening benchmark target, return None and explain why.
"""
import math
import re


def _price(value):
    if isinstance(value, bool) or isinstance(value, (dict, list, tuple)):
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", "").replace("$", "")
    try:
        amount = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return amount if math.isfinite(amount) and 1000.0 < amount < 1000000.0 else None


def kalshi_btc_target(market):
    """Return (target, source field). No cross-market or spot-price fallback."""
    if not isinstance(market, dict):
        return None, "NO MARKET METADATA"
    for field in ("floor_strike", "cap_strike", "strike_price",
                  "functional_strike"):
        value = _price(market.get(field))
        if value is not None:
            return value, field
    custom = market.get("custom_strike")
    if isinstance(custom, dict):
        for field in ("floor_strike", "strike_price", "target_price", "price"):
            value = _price(custom.get(field))
            if value is not None:
                return value, "custom_strike." + field

    # Use only explicit target-price text from the selected Kalshi market.
    # Never extract an arbitrary dollar amount from settlement rules or title.
    for field in ("yes_sub_title", "subtitle"):
        text = str(market.get(field) or "")
        match = re.search(
            r"(?:target|strike|price to beat)\s*(?:price)?\s*[:=]?\s*"
            r"\$\s*([0-9]{1,3}(?:,[0-9]{3})+(?:\.\d+)?|[0-9]{4,6}(?:\.\d+)?)",
            text, flags=re.IGNORECASE,
        )
        if match:
            value = _price(match.group(1))
            if value is not None:
                return value, field + " explicit target"
    return None, "TARGET NOT YET PUBLISHED BY KALSHI"


def same_contract_target(ticker, full_market, listed_markets):
    """Get target from full market; if absent, use matching same-ticker listing.

    A ticker match is mandatory. Cross-window targets are NOT interchangeable.
    """
    found, source = kalshi_btc_target(full_market)
    if found is not None:
        return found, source
    for market in listed_markets or []:
        if not isinstance(market, dict):
            continue
        if str(market.get("ticker") or "") != str(ticker):
            continue
        found, key = kalshi_btc_target(market)
        if found is not None:
            return found, "same-ticker listing." + key
    return None, source
