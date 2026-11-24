"""Guarded Kalshi BTC 15-minute live order execution.

Orders are explicit user-click actions, limit-priced and immediate-or-cancel.
No credentials are stored in source control. Demo is the default environment.
"""
import base64
import time
import uuid
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa

PREFIX = "/trade-api/v2"
LIVE_URL = "https://external-api.kalshi.com"
DEMO_URL = "https://demo-api.kalshi.co"


def _private_key(pem):
    if not pem:
        raise ValueError("Kalshi trading private key is not configured")
    return serialization.load_pem_private_key(str(pem).replace("\\n", "\n").encode(), password=None)


def _headers(key_id, pem, method, path):
    if not key_id:
        raise ValueError("Kalshi trading API key ID is not configured")
    now_ms = str(int(time.time() * 1000))
    key = _private_key(pem)
    message = f"{now_ms}{method.upper()}{path.split('?')[0]}".encode()
    if isinstance(key, ed25519.Ed25519PrivateKey):
        signature = key.sign(message)
    elif isinstance(key, rsa.RSAPrivateKey):
        signature = key.sign(message, padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=hashes.SHA256().digest_size
        ), hashes.SHA256())
    else:
        raise ValueError("Unsupported Kalshi private key type")
    return {
        "KALSHI-ACCESS-KEY": str(key_id),
        "KALSHI-ACCESS-TIMESTAMP": now_ms,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("ascii"),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def place_btc_limit_ioc(key_id, private_pem, environment, ticker, outcome,
                        intent, quantity, yes_price_cents, timeout=10):
    """Submit one bounded BTC15M order. No automatic retries on POST.

    V2 event orders quote the YES book only:
      buy YES / sell NO => bid YES
      buy NO / sell YES => ask YES
    """
    ticker = str(ticker or "").upper()
    outcome = str(outcome or "").lower()
    intent = str(intent or "").lower()
    if not ticker.startswith("KXBTC15M-"):
        raise ValueError("Live execution is restricted to KXBTC15M markets")
    if outcome not in ("yes", "no") or intent not in ("buy", "sell"):
        raise ValueError("Unsupported outcome or order intent")
    try:
        qty = Decimal(str(quantity))
        cents = Decimal(str(yes_price_cents))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Quantity and price must be valid numbers")
    if not qty.is_finite() or qty < 1 or qty > 5 or qty != qty.to_integral_value():
        raise ValueError("Quantity must be 1–5 contracts in whole-contract increments")
    if not cents.is_finite() or cents < 1 or cents > 99:
        raise ValueError("YES limit price must be between 1¢ and 99¢")

    # The V2 API exposes a single YES-referenced book. Convert the desired
    # outcome action into a bid/ask on that book.
    book_side = "bid" if (outcome == "yes" and intent == "buy") or (outcome == "no" and intent == "sell") else "ask"
    base = DEMO_URL if str(environment).lower() == "demo" else LIVE_URL
    path = PREFIX + "/portfolio/events/orders"
    body = {
        "ticker": ticker,
        "client_order_id": str(uuid.uuid4()),
        "side": book_side,
        "count": format(qty, ".2f"),
        "price": format(cents / Decimal(100), ".4f"),
        "time_in_force": "immediate_or_cancel",
        "self_trade_prevention_type": "taker_at_cross",
        "post_only": False,
        "cancel_order_on_pause": True,
        "subaccount": 0,
        "exchange_index": 0,
    }
    response = requests.post(
        base + path, json=body,
        headers=_headers(key_id, private_pem, "POST", path),
        timeout=timeout,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {"message": "Kalshi returned a non-JSON response"}
    if response.status_code != 201:
        # Do not include request headers or credential material in the error.
        err = payload.get("message") or payload.get("code") or f"HTTP {response.status_code}"
        raise RuntimeError(f"Kalshi rejected the order: {err} (HTTP {response.status_code})")
    return {
        "order_id": payload.get("order_id"),
        "client_order_id": body["client_order_id"],
        "ticker": ticker,
        "outcome": outcome.upper(),
        "intent": intent.upper(),
        "book_side": book_side,
        "limit_yes_cents": float(cents),
        "requested_count": float(qty),
        "fill_count": float(Decimal(str(payload.get("fill_count", "0")))),
        "remaining_count": float(Decimal(str(payload.get("remaining_count", "0")))),
        "average_fill_price": payload.get("average_fill_price"),
        "average_fee_paid": payload.get("average_fee_paid"),
        "environment": str(environment).lower(),
    }
