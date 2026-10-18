"""Unit tests for read-only Kalshi account pairing without network calls."""
import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa, padding
from cryptography.hazmat.primitives import hashes

from kalshi_connection import (
    KalshiConnectionError, headers, check_connection, credentials_from_secrets,
)


def make_ed_key():
    key = ed25519.Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    return key, pem


def test_ed25519_request_signatures():
    key, pem = make_ed_key()
    h = headers("key", pem, "get", "/trade-api/v2/portfolio/balance?limit=1", now_ms=123456)
    msg = b"123456GET/trade-api/v2/portfolio/balance"
    key.public_key().verify(base64.b64decode(h["KALSHI-ACCESS-SIGNATURE"]), msg)


def test_rsa_request_signatures():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    h = headers("key", pem, "GET", "/trade-api/v2/portfolio/balance", now_ms=223344)
    key.public_key().verify(base64.b64decode(h["KALSHI-ACCESS-SIGNATURE"]),
                            b"223344GET/trade-api/v2/portfolio/balance",
                            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                        salt_length=padding.PSS.DIGEST_LENGTH),
                            hashes.SHA256())


def test_no_mutating_requests():
    _, pem = make_ed_key()
    with pytest.raises(KalshiConnectionError, match="read-only"):
        headers("key", pem, "POST", "/trade-api/v2/portfolio/orders")
    with pytest.raises(KalshiConnectionError, match="Invalid API path"):
        headers("key", pem, "GET", "https://evil.example/trade-api/v2/portfolio/balance")


class DummyResponse:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self.data = {"balance": 1025} if data is None else data

    def json(self):
        return self.data


class DummySession:
    def __init__(self, result):
        self.result = result
        self.url = None

    def get(self, url, headers, timeout):
        self.url = url
        assert timeout == 8
        assert "KALSHI-ACCESS-SIGNATURE" in headers
        return self.result


def test_separate_prod_demo_credentials():
    keys = {"KALSHI_API_KEY_ID": "live-id",
            "KALSHI_PRIVATE_KEY": "live-pem",
            "KALSHI_DEMO_API_KEY_ID": "demo-id",
            "KALSHI_DEMO_PRIVATE_KEY": "demo-pem"}
    assert credentials_from_secrets(keys, "LIVE") == ("live-id", "live-pem")
    assert credentials_from_secrets(keys, "DEMO") == ("demo-id", "demo-pem")


def test_connection_never_exposes_balance():
    _, pem = make_ed_key()
    session = DummySession(DummyResponse())
    result = check_connection("DEMO", "test-id", pem, session=session)
    assert result == {"connected": True, "environment": "DEMO",
                      "credential_type": "API key", "trade_mode": "DISABLED"}
    assert session.url.startswith("https://external-api.demo.kalshi.co/")


def test_auth_rejection_without_api_body():
    _, pem = make_ed_key()
    session = DummySession(DummyResponse(401))
    with pytest.raises(KalshiConnectionError, match="Unauthorized"):
        check_connection("LIVE", "test-id", pem, session=session)
