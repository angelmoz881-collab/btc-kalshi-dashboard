"""Kalshi READ-ONLY account inventory discovery for scalp monitoring.

Credential material is pulled from Streamlit Secrets on the SERVER. Nothing in
this module writes to Kalshi, submits orders, or persists keys to GitHub.
"""
import base64
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import time

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa

BASE_URL = "https://api.elections.kalshi.com"
PREFIX = "/trade-api/v2"
HTTP = requests.Session()


def _decimal(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def sign_headers(key_id, private_pem, method, path, now_ms=None):
    """Kalshi signs timestamp + HTTP method + URL path (no query string)."""
    if not key_id or not private_pem:
        raise ValueError("Kalshi read-only API key not configured")
    now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    private_pem = str(private_pem).replace("\\n", "\n")
    key = serialization.load_pem_private_key(private_pem.encode(), password=None)
    message = f"{now_ms}{method.upper()}{path.split('?')[0]}".encode()
    if isinstance(key, ed25519.Ed25519PrivateKey):
        sig = key.sign(message)
    elif isinstance(key, rsa.RSAPrivateKey):
        sig = key.sign(message, padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                            salt_length=hashes.SHA256().digest_size),
                       hashes.SHA256())
    else:
        raise ValueError("Unsupported Kalshi key type; use Ed25519 or RSA")
    return {"KALSHI-ACCESS-KEY": str(key_id),
            "KALSHI-ACCESS-TIMESTAMP": str(now_ms),
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode("ascii"),
            "Accept": "application/json"}


def _get(endpoint, params, key_id, private_pem, timeout=7):
    if endpoint not in ("portfolio/positions", "portfolio/fills"):
        raise ValueError("Read-only portfolio endpoint only")
    path = PREFIX + "/" + endpoint
    headers = sign_headers(key_id, private_pem, "GET", path)
    response = HTTP.get(BASE_URL + path, params=params, headers=headers, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Unexpected portfolio response")
    return data


def get_btc_open_positions(key_id, private_pem, max_pages=5):
    """Return all nonzero KXBTC15M positions for the primary Kalshi subaccount."""
    cursor = None
    positions = []
    for _ in range(max_pages):
        params = {"limit": 200, "count_filter": "position", "settlement_status": "unsettled"}
        if cursor:
            params["cursor"] = cursor
        payload = _get("portfolio/positions", params, key_id, private_pem)
        positions.extend(row for row in payload.get("market_positions", [])
                         if str(row.get("ticker", "")).startswith("KXBTC15M-")
                         and (_decimal(row.get("position_fp", row.get("position"))) or Decimal(0)) != 0)
        cursor = payload.get("cursor")
        if not cursor:
            return positions
    raise ValueError("Position result pagination exceeded safety limit")


def get_market_fills(ticker, key_id, private_pem, max_pages=5):
    """Read recent fills; do not reconstruct a cost basis with truncated history."""
    if not str(ticker).startswith("KXBTC15M-"):
        raise ValueError("Only BTC 15-minute market fills are supported")
    cursor = None
    fills = []
    for _ in range(max_pages):
        params = {"limit": 200, "ticker": ticker}
        if cursor:
            params["cursor"] = cursor
        payload = _get("portfolio/fills", params, key_id, private_pem)
        fills.extend(row for row in payload.get("fills", [])
                     if str(row.get("ticker") or row.get("market_ticker")) == ticker)
        cursor = payload.get("cursor")
        if not cursor:
            return fills
    raise ValueError("Fill history pagination exceeded safety limit")


def _fill_side_price_cents(fill, side):
    dollar = _decimal(fill.get(f"{side}_price_dollars"))
    if dollar is not None:
        return dollar * 100
    fixed = _decimal(fill.get(f"{side}_price_fixed"))
    if fixed is not None:
        return fixed * 100
    price = _decimal(fill.get(f"{side}_price"))
    if price is not None:
        return price
    # Kalshi legacy fill.price is the traded outcome-side price in integer cents.
    return _decimal(fill.get("price"))


def _fill_time(fill):
    stamp = fill.get("created_time")
    if stamp:
        try:
            return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError):
            pass
    raw = _decimal(fill.get("ts"))
    if raw is not None:
        return float(raw / 1000 if raw > Decimal("1e11") else raw)
    return None


def _fill_qty(fill):
    return _decimal(fill.get("count_fp", fill.get("count")))


def reconstruct_position(market_position, fills, entry_score=None):
    """Build cost-basis from documented fills, independently verify exchange shares.

    Only straightforward buys and sells of the owned contract are supported.
    Opposite-side fills, missing fee data, and incomplete history cannot be
    represented faithfully: return an unavailable basis rather than guess.
    """
    ticker = str(market_position.get("ticker") or "")
    signed = _decimal(market_position.get("position_fp", market_position.get("position")))
    if signed is None or signed == 0 or not ticker.startswith("KXBTC15M-"):
        return None, "No supported open BTC 15m position"
    side = "yes" if signed > 0 else "no"
    wanted = abs(signed)
    ordered = sorted((x for x in fills if str(x.get("ticker") or x.get("market_ticker")) == ticker),
                     key=lambda x: (_fill_time(x) or 0, str(x.get("fill_id", ""))))
    if not ordered:
        return None, "No fill history available for actual cost basis"
    lots = []
    for item in ordered:
        item_side = str(item.get("side") or item.get("outcome_side") or "").lower()
        action = str(item.get("action") or "").lower()
        qty = _fill_qty(item)
        fee = _decimal(item.get("fee_cost"))
        ts = _fill_time(item)
        if item_side not in ("yes", "no") or action not in ("buy", "sell") or qty is None or qty <= 0:
            return None, "Incomplete fill details: cost basis unavailable"
        if item_side != side:
            return None, "Opposite-side fills need reconciliation; cost basis unavailable"
        if action == "buy":
            price = _fill_side_price_cents(item, side)
            if price is None or not (0 < price < 100):
                return None, "Unknown executed fill price: cost basis unavailable"
            if fee is None or fee < 0:
                return None, "Missing actual buy fee: cost basis unavailable"
            lots.append([qty, price, fee * 100, ts])
        else:
            left = qty
            while left > 0 and lots:
                lot = lots[0]
                removal = min(left, lot[0])
                fraction = removal / lot[0]
                lot[2] *= (1 - fraction)
                lot[0] -= removal
                left -= removal
                if lot[0] <= Decimal("0.00000001"):
                    lots.pop(0)
            if left > Decimal("0.00000001"):
                return None, "Unmatched historical sale: cost basis unavailable"
    held = sum((lot[0] for lot in lots), Decimal(0))
    if abs(held - wanted) > Decimal("0.000001"):
        return None, "Fill history does not reconcile with the exchange position"
    if not lots:
        return None, "No remaining bought lots"
    cost_cents = sum((lot[0] * lot[1] for lot in lots), Decimal(0))
    entry_fee_cents = sum((lot[2] for lot in lots), Decimal(0))
    opened = min((lot[3] for lot in lots if lot[3] is not None), default=time.time())
    return {
        "ticker": ticker, "side": side, "quantity": float(held),
        "entry_price_cents": float(cost_cents / held),
        "entry_fee_cents": float(entry_fee_cents),
        "opened_at": float(opened), "entry_score": entry_score,
        "peak_net_cents": 0.0, "source": "KALSHI LIVE",
    }, None
