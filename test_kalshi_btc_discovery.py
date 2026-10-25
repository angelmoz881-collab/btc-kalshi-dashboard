"""Deterministic regression checks for resilient Kalshi KXBTC15M discovery."""
import unittest
from datetime import datetime, timedelta, timezone
from kalshi_btc_discovery import _event_candidates, close_time, discover_btc_markets, live_btc_market

NOW = datetime(2026, 10, 24, 17, 0, tzinfo=timezone.utc)
TICKER = "KXBTC15M-26OCT241715-15"


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def market(ticker=TICKER, status="active", close_in=600, **changes):
    obj = {
        "ticker": ticker, "status": status,
        "open_time": iso(NOW - timedelta(minutes=5)),
        "close_time": iso(NOW + timedelta(seconds=close_in)),
        "title": "BTC price up in next 15 mins?",
    }
    obj.update(changes)
    return obj


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class FakeAPI:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def __call__(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        value = self.handler(url, params)
        if isinstance(value, Exception):
            raise value
        return FakeResponse(value)


class BTCDiscoveryTest(unittest.TestCase):
    def test_selects_nearest_currently_open_contract(self):
        nearer = market(close_in=300)
        later = market(ticker="KXBTC15M-26OCT241730-30", close_in=900)
        api = FakeAPI(lambda url, p: {"markets": [later, nearer], "cursor": ""})
        answer = discover_btc_markets(api, now=NOW, hosts=["https://api.test/trade-api/v2"])
        self.assertEqual(answer["markets"][0]["ticker"], TICKER)
        self.assertEqual(answer["status"], "LIVE")
        self.assertEqual(api.calls[0][1]["series_ticker"], "KXBTC15M")
        self.assertEqual(api.calls[0][1]["status"], "open")
        self.assertEqual(nearer["status"], "active")

    def test_real_kalshi_active_market_response_no_longer_discarded(self):
        # Matches the live KXBTC15M /markets payload verified Oct 24, 2026.
        ref_now = datetime(2026, 10, 25, 4, 20, tzinfo=timezone.utc)
        confirmed = {
            "ticker": "KXBTC15M-26OCT250030-30",
            "event_ticker": "KXBTC15M-26OCT250030",
            "status": "active",
            "open_time": "2026-10-25T04:15:00Z",
            "close_time": "2026-10-25T04:30:00Z",
            "expiration_time": "2026-11-01T04:30:00Z",
            "floor_strike": 80744.94,
            "title": "BTC price up in next 15 mins?",
        }
        api = FakeAPI(lambda url, p: {"markets": [confirmed], "cursor": ""})
        result = discover_btc_markets(api, now=ref_now, hosts=["https://api.test"])
        self.assertEqual(result["status"], "LIVE")
        self.assertEqual(result["markets"][0]["ticker"], confirmed["ticker"])
        self.assertEqual(result["source"], "Kalshi markets")
        self.assertEqual(api.calls[0][1]["status"], "open")

    def test_active_nested_event_market_is_accepted(self):
        def handler(url, p):
            if url.endswith("/markets"):
                return {"markets": [], "cursor": ""}
            return {"events": [{
                "series_ticker": "KXBTC15M", "status": "active",
                "markets": [market(status="active")],
            }], "cursor": ""}
        result = discover_btc_markets(FakeAPI(handler), now=NOW, hosts=["https://api.test"])
        self.assertEqual(result["markets"][0]["ticker"], TICKER)

    def test_direct_event_uses_kalshi_eastern_clock_not_utc(self):
        # Verified API event: 2026-10-25T04:30:00Z maps to 00:30 EDT.
        now = datetime(2026, 10, 25, 4, 20, tzinfo=timezone.utc)
        candidates = _event_candidates(now)
        self.assertIn("KXBTC15M-26OCT250030", candidates)
        self.assertNotIn("KXBTC15M-26OCT250430", candidates)

    def test_uses_nested_events_when_market_list_empty(self):
        def handler(url, p):
            if url.endswith("/markets"):
                return {"markets": [], "cursor": ""}
            return {"events": [{"series_ticker": "KXBTC15M", "status": "open",
                                "markets": [market()]}], "cursor": ""}
        api = FakeAPI(handler)
        answer = discover_btc_markets(api, now=NOW, hosts=["https://api.test"])
        self.assertEqual(answer["markets"][0]["ticker"], TICKER)
        self.assertEqual(answer["source"], "Kalshi nested events")
        self.assertEqual(api.calls[1][1]["with_nested_markets"], "true")

    def test_fails_over_to_second_host(self):
        def handler(url, p):
            if url.startswith("https://broken.test"):
                return OSError("Temporary upstream failure")
            if url.endswith("/markets"):
                return {"markets": [market()], "cursor": ""}
            return {"events": [], "cursor": ""}
        api = FakeAPI(handler)
        answer = discover_btc_markets(api, now=NOW, hosts=["https://broken.test", "https://good.test"])
        self.assertEqual(answer["markets"][0]["ticker"], TICKER)
        self.assertTrue(answer["errors"])
        self.assertEqual(answer["source"], "Kalshi markets")

    def test_does_not_select_closed_expired_unopened_or_wrong_series(self):
        candidates = [
            market(status="settled"),
            market(ticker="KXETH15M-26OCT241715-15"),
            market(close_in=-5),
            market(status="unopened"),
            market(open_time=iso(NOW + timedelta(minutes=2))),
            market(close_time="not a date"),
        ]
        api = FakeAPI(lambda url, p: (
            {"markets": candidates, "cursor": ""}
            if url.endswith("/markets") else {"events": [], "cursor": ""}
        ))
        answer = discover_btc_markets(api, now=NOW, hosts=["https://api.test"])
        self.assertFalse(answer["markets"])
        self.assertEqual(answer["source"], "none")

    def test_market_status_and_open_time_are_both_required(self):
        self.assertFalse(live_btc_market(market(status="unopened"), now=NOW))
        self.assertFalse(live_btc_market(market(open_time=iso(NOW + timedelta(seconds=30))), now=NOW))
        self.assertTrue(live_btc_market(market(), now=NOW))

    def test_expiration_time_can_substitute_for_missing_close_time(self):
        m = market(close_time=None, expiration_time=iso(NOW + timedelta(minutes=8)))
        self.assertTrue(live_btc_market(m, now=NOW))
        self.assertEqual(close_time(m).minute, 8)

    def test_supports_epoch_close_ts(self):
        m = market(close_time=None, close_ts=int((NOW + timedelta(minutes=4)).timestamp()))
        self.assertTrue(live_btc_market(m, now=NOW))

    def test_ticker_not_in_nested_market_is_not_fabricated(self):
        api = FakeAPI(lambda url, p: (
            {"markets": [], "cursor": ""} if url.endswith("/markets") else
            {"events": [{"event_ticker": "KXBTC15M-26OCT241715", "status": "open",
                         "markets": []}], "cursor": ""}
        ))
        result = discover_btc_markets(api, now=NOW, hosts=["https://api.test"])
        self.assertEqual(result["markets"], [])

    def test_direct_event_lookup_recovers_live_market(self):
        """Both listing endpoints empty; verified event lookup returns actual child market."""
        def handler(url, p):
            if url.endswith("/markets"):
                return {"markets": [], "cursor": ""}
            if url.endswith("/events"):
                return {"events": [], "cursor": ""}
            if "/events/KXBTC15M-" in url:
                return {"event": {"event_ticker": url.rsplit("/", 1)[-1],
                                  "series_ticker": "KXBTC15M", "status": "open",
                                  "markets": [market()]}}
            return {"events": [], "cursor": ""}
        api = FakeAPI(handler)
        result = discover_btc_markets(api, now=NOW, hosts=["https://api.test"])
        self.assertEqual(result["markets"][0]["ticker"], TICKER)
        self.assertEqual(result["source"], "Kalshi direct event")
        self.assertTrue(any("/events/KXBTC15M-" in u for u, _ in api.calls))

    def test_direct_event_supports_markets_in_top_level_response(self):
        def handler(url, p):
            if url.endswith("/markets"):
                return {"markets": [], "cursor": ""}
            if url.endswith("/events"):
                return {"events": [], "cursor": ""}
            return {"event": {"series_ticker": "KXBTC15M", "status": "open"},
                    "markets": [market()]}
        result = discover_btc_markets(FakeAPI(handler), now=NOW, hosts=["https://api.test"])
        self.assertEqual(result["source"], "Kalshi direct event")
        self.assertEqual(result["markets"][0]["ticker"], TICKER)

    def test_does_not_fabricate_market_from_event_name(self):
        api = FakeAPI(lambda url, p:
            {"markets": [], "cursor": ""} if url.endswith("/markets") else
            {"events": [], "cursor": ""} if url.endswith("/events") else
            {"event": {"series_ticker": "KXBTC15M",
                       "event_ticker": "KXBTC15M-26OCT241900", "status": "open",
                       "markets": []}}
        )
        result = discover_btc_markets(api, now=NOW, hosts=["https://api.test"])
        self.assertEqual(result["markets"], [])

    def test_missing_response_data_is_not_a_fake_success(self):
        api = FakeAPI(lambda url, p: {"data": []})
        result = discover_btc_markets(api, now=NOW, hosts=["https://api.test"])
        self.assertEqual(result["markets"], [])
        self.assertTrue(result["errors"])

    def test_pagination_follows_cursor_without_generating_ids(self):
        def handler(url, params):
            if url.endswith("/events"):
                return {"events": [], "cursor": ""}
            if params.get("cursor") == "next":
                return {"markets": [market()], "cursor": ""}
            return {"markets": [], "cursor": "next"}
        api = FakeAPI(handler)
        result = discover_btc_markets(api, now=NOW, hosts=["https://api.test"])
        self.assertEqual(result["markets"][0]["ticker"], TICKER)
        self.assertEqual(len(api.calls), 2)


if __name__ == "__main__":
    unittest.main()
