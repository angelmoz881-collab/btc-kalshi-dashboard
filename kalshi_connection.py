"""Authenticated Kalshi portfolio connectivity: READ ONLY.

Supports Kalshi's Ed25519 and RSA-PSS keys. This module exposes only GET
balance; no submit, cancel, withdraw, or trading functions exist here.
Do not print or log credentials and never commit PEM keys to GitHub.
"""
from __future__ import annotations

import base64
import time
from urllib.parse import urlsplit

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa

HOSTS = {
    "DEMO": "https://external-api.demo.kalshi.co",
    "LIVE": "https://external-api.kalshi.com",
}
BASE_PATH = "/trade-api/v2"


class KalshiConnectionError(RuntimeError):
    """Sanitized authentication failure with no key or response body."""


def _key(private_key_pem):
    if not isinstance(private_key_pem, str) or not private_key_pem.strip():
        raise KalshiConnectionError("Private key missing")
    pem = private_key_pem.replace("\\n", "\n")
    try:
        loaded = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    except (TypeError, ValueError):
        raise KalshiConnectionError("Invalid private key format") from None
    if not isinstance(loaded, (ed25519.Ed25519PrivateKey, rsa.RSAPrivateKey)):
        raise KalshiConnectionError("Unsupported private key algorithm")
    return loaded


def headers(key_id, private_key_pem, method, path, now_ms=None):
    if not isinstance(key_id, str) or not key_id.strip():
        raise KalshiConnectionError("Key ID missing")
    parsed = urlsplit(path)
    if not parsed.path.startswith(BASE_PATH + "/") or parsed.scheme or parsed.netloc:
        raise KalshiConnectionError("Invalid API path")
    method = method.upper()
    if method != "GET":
        raise KalshiConnectionError("This connection only supports read-only requests")
    timestamp = str(int(time.time()*1000) if now_ms is None else int(now_ms))
    msg = (timestamp + method + parsed.path).encode("utf-8")
    signer = _key(private_key_pem)
    if isinstance(signer, ed25519.Ed25519PrivateKey):
        signature = signer.sign(msg)
    else:
        signature = signer.sign(msg, padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ), hashes.SHA256())
    return {
        "KALSHI-ACCESS-KEY": key_id.strip(),
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("ascii"),
        "Accept": "application/json",
        "User-Agent": "BTC-Kalshi-ReadOnly-Link/1.0",
    }


def check_connection(environment, key_id, private_key_pem, *, session=None):
    """Verify credentials through Kalshi balance endpoint, without returning balance.

    The caller receives a small status only. Avoids leaking sensitive portfolio
    data or raw API response contents to the dashboard.
    """
    if environment not in HOSTS:
        raise KalshiConnectionError("Choose DEMO or LIVE")
    path = BASE_PATH + "/portfolio/balance"
    auth = headers(key_id, private_key_pem, "GET", path)
    client = session if session is not None else requests
    try:
        response = client.get(HOSTS[environment] + path, headers=auth, timeout=8)
    except requests.RequestException:
        raise KalshiConnectionError("Network unavailable or request timed out") from None
    if response.status_code == 401:
        raise KalshiConnectionError("Unauthorized: check API key, environment and private key")
    if response.status_code == 403:
        raise KalshiConnectionError("Access denied: verify account location or API permissions")
    if response.status_code >= 400:
        raise KalshiConnectionError(f"Kalshi authentication check returned HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError:
        raise KalshiConnectionError("Unexpected Kalshi response") from None
    if not isinstance(data, dict) or "balance" not in data:
        raise KalshiConnectionError("Balance response missing expected fields")
    return {"connected": True, "environment": environment, "credential_type": "API key",
            "trade_mode": "DISABLED"}


def credentials_from_secrets(secrets, environment):
    if environment == "DEMO":
        return secrets.get("KALSHI_DEMO_API_KEY_ID"), secrets.get("KALSHI_DEMO_PRIVATE_KEY")
    if environment == "LIVE":
        return secrets.get("KALSHI_API_KEY_ID"), secrets.get("KALSHI_PRIVATE_KEY")
    raise KalshiConnectionError("Invalid environment")
