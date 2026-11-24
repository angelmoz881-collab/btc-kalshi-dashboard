"""Fail-closed Kalshi live scalp execution with a hard 20% portfolio cap.

Live execution is deliberately opt-in. Credentials are read only from Streamlit
Secrets/environment variables and must be a trading-enabled key with read + write::trade
scopes. Never place API secrets in source control or chat.

Orders use Kalshi's current V2 /portfolio/events/orders endpoint. A 201 response
is an accepted order, not proof of a complete fill; callers must reconcile fills
and positions before treating it as inventory.
"""
import base64
from decimal import Decimal, InvalidOperation, ROUND_DOWN
import time
import uuid

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa

BASE_URL = "https://external-api.kalshi.com"
PREFIX = "/trade-api/v2"
HTTP = requests.Session()
CENT = Decimal("0.01")
MAX_SCALP_FRACTION = Decimal("0.20")


def dec(value):
    try:
        out = Decimal(str(value))
        return out if out.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def _money(value, *, cents=False):
    x = dec(value)
    if x is None or x < 0:
        return None
    return x / 100 if cents else x


def _sign(key_id, private_pem, method, path):
    if not key_id or not private_pem:
        raise ValueError("Trading API credentials are not configured")
    pem = str(private_pem).replace("\\n", "\n")
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    ts = str(int(time.time() * 1000))
    msg = f"{ts}{method.upper()}{path.split('?')[0]}".encode()
    if isinstance(key, ed25519.Ed25519PrivateKey):
        signature = key.sign(msg)
    elif isinstance(key, rsa.RSAPrivateKey):
        signature = key.sign(msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                               salt_length=hashes.SHA256().digest_size),
                             hashes.SHA256())
    else:
        raise ValueError("Unsupported Kalshi private key type")
    return {
        "KALSHI-ACCESS-KEY": str(key_id),
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("ascii"),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _request(method, endpoint, key_id, private_pem, *, params=None, body=None, timeout=8):
    path = PREFIX + "/" + endpoint.lstrip("/")
    headers = _sign(key_id, private_pem, method, path)
    response = HTTP.request(method.upper(), BASE_URL + path, params=params,
                             json=body, headers=headers, timeout=timeout)
    response.raise_for_status()
    data = response.json() if response.content else {}
    if not isinstance(data, dict):
        raise ValueError("Unexpected Kalshi API response")
    return data


def _pages(endpoint, collection_key, key_id, private_pem, max_pages=10, params=None):
    cursor, rows = None, []
    for _ in range(max_pages):
        query = dict(params or {})
        query["limit"] = 200
        if cursor:
            query["cursor"] = cursor
        payload = _request("GET", endpoint, key_id, private_pem, params=query)
        batch = payload.get(collection_key)
        if not isinstance(batch, list):
            raise ValueError(f"Kalshi {collection_key} response is unavailable")
        rows.extend(batch)
        cursor = payload.get("cursor")
        if not cursor:
            return rows
    raise ValueError(f"Kalshi {collection_key} pagination safety limit exceeded")


def _position_exposure_dollars(row):
    # Prefer explicitly dollar-denominated exchange fields. Otherwise the
    # documented market_exposure field is integer cents.
    for name in ("market_exposure_dollars", "position_cost_dollars", "total_cost_dollars"):
        if name in row:
            value = dec(row.get(name))
            return abs(value) if value is not None else None
    for name in ("market_exposure", "position_cost", "total_cost", "event_exposure"):
        if name in row:
            value = dec(row.get(name))
            return abs(value) / 100 if value is not None else None
    return None


def _resting_buy_exposure_dollars(order):
    action = str(order.get("action") or "").lower()
    status = str(order.get("status") or "").lower()
    remaining = dec(order.get("remaining_count_fp", order.get("remaining_count", order.get("count_fp"))))
    if action != "buy" or status not in ("resting", "pending", "partially_filled", "partially_filled_resting"):
        return Decimal(0)
    if remaining is None or remaining <= 0:
        return Decimal(0)
    price = None
    for name in ("yes_price_dollars", "no_price_dollars", "price"):
        if order.get(name) is not None:
            price = _money(order.get(name))
            break
    if price is None:
        for name in ("yes_price", "no_price"):
            if order.get(name) is not None:
                price = _money(order.get(name), cents=True)
                break
    if price is None:
        raise ValueError("Cannot verify exposure for a resting buy order")
    return remaining * price


def get_portfolio_snapshot(key_id, private_pem):
    """Fetch and validate equity, all unsettled positions and resting orders."""
    balance_payload = _request("GET", "portfolio/balance", key_id, private_pem)
    balance_obj = balance_payload.get("balance") if isinstance(balance_payload.get("balance"), dict) else balance_payload
    # Kalshi balance and portfolio_value are returned in cents in the REST API.
    equity_raw = balance_obj.get("portfolio_value")
    equity = _money(equity_raw, cents=True)
    if equity is None or equity <= 0:
        raise ValueError("Portfolio equity is missing or invalid; live orders blocked")
    positions = _pages("portfolio/positions", "market_positions", key_id, private_pem,
                       params={"count_filter": "position", "settlement_status": "unsettled"})
    orders = _pages("portfolio/orders", "orders", key_id, private_pem,
                    params={"status": "resting"})
    position_exposure = Decimal(0)
    for row in positions:
        qty = dec(row.get("position_fp", row.get("position")))
        if qty is None:
            raise ValueError("An open position has an unreadable quantity; live orders blocked")
        if qty == 0:
            continue
        exposure = _position_exposure_dollars(row)
        if exposure is None:
            raise ValueError("An open position has no verifiable cost exposure; live orders blocked")
        position_exposure += exposure
    order_exposure = sum((_resting_buy_exposure_dollars(row) for row in orders), Decimal(0))
    return {
        "equity_dollars": equity,
        "cash_balance_dollars": _money(balance_obj.get("balance"), cents=True),
        "position_exposure_dollars": position_exposure,
        "resting_buy_exposure_dollars": order_exposure,
        "committed_dollars": position_exposure + order_exposure,
        "positions": positions,
        "orders": orders,
    }


def available_scalp_budget(snapshot, fraction=MAX_SCALP_FRACTION):
    """Remaining dollars beneath the portfolio-wide allocation cap."""
    equity = dec(snapshot.get("equity_dollars"))
    committed = dec(snapshot.get("committed_dollars"))
    pct = dec(fraction)
    if equity is None or equity <= 0 or committed is None or committed < 0:
        raise ValueError("Portfolio exposure cannot be verified; live orders blocked")
    if pct is None or pct <= 0 or pct > MAX_SCALP_FRACTION:
        raise ValueError("Scalp allocation may not exceed 20% of portfolio equity")
    cap = equity * pct
    return max(Decimal(0), cap - committed)


def contracts_for_budget(budget_dollars, price_cents, fee_buffer=Decimal("0.03")):
    """Whole-contract sizing including a conservative per-contract fee reserve."""
    budget = dec(budget_dollars)
    price = dec(price_cents)
    fee = dec(fee_buffer)
    if budget is None or price is None or fee is None or budget <= 0 or not (0 < price < 100) or fee < 0:
        return 0
    per_contract = price / 100 + fee
    if per_contract <= 0:
        return 0
    return int((budget / per_contract).to_integral_value(rounding=ROUND_DOWN))


def submit_ioc_order(key_id, private_pem, ticker, outcome_side, action,
                     price_cents, quantity, *, reduce_only=False):
    """Submit one V2 IOC limit order. outcome_side is yes/no; action buy/sell."""
    side = str(outcome_side).lower()
    action = str(action).lower()
    price = dec(price_cents)
    qty = dec(quantity)
    if not str(ticker).startswith("KXBTC15M-"):
        raise ValueError("Live scalp orders are restricted to KXBTC15M markets")
    if side not in ("yes", "no") or action not in ("buy", "sell"):
        raise ValueError("Invalid Kalshi outcome side or action")
    if price is None or not (0 < price < 100) or qty is None or qty <= 0:
        raise ValueError("Invalid live order price or quantity")
    # V2 quotes all orders from the YES book: bid buys YES/sells NO;
    # ask sells YES/buys NO.
    if (side, action) in (("yes", "buy"), ("no", "sell")):
        book_side, yes_price = "bid", price if side == "yes" else Decimal(100) - price
    else:
        book_side, yes_price = "ask", Decimal(100) - price if side == "no" else price
    body = {
        "ticker": ticker,
        "client_order_id": "btcscalp-" + uuid.uuid4().hex[:24],
        "side": book_side,
        "count": format(qty.quantize(CENT), "f"),
        "price": format((yes_price / 100).quantize(Decimal("0.0001")), "f"),
        "time_in_force": "immediate_or_cancel",
        "self_trade_prevention_type": "taker_at_cross",
        "post_only": False,
        "cancel_order_on_pause": True,
        "reduce_only": bool(reduce_only),
        "subaccount": 0,
    }
    return _request("POST", "portfolio/events/orders", key_id, private_pem, body=body)
