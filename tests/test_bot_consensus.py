"""Offline unit tests: real external-bot signals never fabricated by local models."""
from datetime import datetime, timedelta, timezone

from bot_consensus import (
    apply_consensus_to_engine, fetch_external_votes,
    parse_cotes, parse_partner, vote_consensus,
)

NOW = datetime(2026, 10, 18, 21, 0, tzinfo=timezone.utc)
TICKER = "KXBTC15M-26OCT182100-00"


def fmt(seconds_ago):
    return (NOW - timedelta(seconds=seconds_ago)).isoformat()


def cotes_data(side="up", age=7):
    return {"ticker": TICKER, "state": "live", "signals": [{
        "ticker": TICKER, "side": side, "confidence": 80.0,
        "raised_at": fmt(age), "outcome": "pending",
    }]}


def partner_data(side="YES", age=8):
    return {"ticker": TICKER, "side": side, "confidence": 0.78,
            "timestamp": fmt(age), "status": "live"}


def test_cotes_requires_exact_live_ticker_and_fresh_time():
    assert parse_cotes(cotes_data(), TICKER, now=NOW)["Vote"] == "YES"
    assert parse_cotes(cotes_data(age=91), TICKER, now=NOW) is None
    assert parse_cotes(cotes_data(), "DIFFERENT", now=NOW) is None
    data = cotes_data()
    data["state"] = "settled"
    assert parse_cotes(data, TICKER, now=NOW) is None


def test_multiple_signals_from_same_provider_count_as_one():
    data = cotes_data()
    data["signals"].append({
        "ticker": TICKER, "side": "down", "confidence": 90,
        "raised_at": fmt(2), "outcome": "pending",
    })
    latest = parse_cotes(data, TICKER, now=NOW)
    assert latest["Vote"] == "NO"


def test_no_fake_external_quorum_from_internal_model():
    only_one = parse_cotes(cotes_data(), TICKER, now=NOW)
    result = vote_consensus([only_one], ticker=TICKER, model_probability=.99, now=NOW)
    assert result["status"] == "WAIT"
    assert result["total"] == 1


def test_two_independent_bots_agree_and_local_model_only_vetoes():
    first = parse_cotes(cotes_data(), TICKER, now=NOW)
    second = parse_partner(partner_data(), TICKER, "Partner 2", now=NOW)
    result = vote_consensus([first, second], ticker=TICKER, model_probability=.52, now=NOW)
    assert result["status"] == "AGREE"
    assert result["side"] == "YES"
    assert result["yes"] == 2
    assert vote_consensus([first, second], ticker=TICKER,
                          model_probability=.1, now=NOW)["status"] == "WAIT"


def test_disagreement_or_duplicate_source_means_wait():
    a = parse_cotes(cotes_data(), TICKER, now=NOW)
    b = parse_partner(partner_data("NO"), TICKER, "Partner 2", now=NOW)
    assert vote_consensus([a, b], ticker=TICKER, now=NOW)["status"] == "WAIT"
    repeat = dict(a)
    assert vote_consensus([a, repeat], ticker=TICKER, now=NOW)["total"] == 1


def test_cached_votes_expire_at_display_time():
    a = parse_cotes(cotes_data(age=85), TICKER, now=NOW)
    b = parse_partner(partner_data(age=85), TICKER, "Partner 2", now=NOW)
    result = vote_consensus([a, b], ticker=TICKER, now=NOW+timedelta(seconds=10))
    assert result["status"] == "WAIT"
    assert result["total"] == 0


def test_external_feed_endpoints_require_https_and_distinct_hosts():
    class FakeResponse:
        status_code = 200
        def __init__(self, data):
            self.data = data
        def json(self):
            return self.data

    class FakeSession:
        def get(self, url, headers, params, timeout, allow_redirects):
            if "api.cotes.ai" in url:
                return FakeResponse(cotes_data())
            if "partner.example" in url:
                return FakeResponse(partner_data())
            raise RuntimeError("Unexpected outgoing request")

    config = {"COTES_API_KEY": "TEST_SECRET",
              "BOT_SIGNAL_URL_2": "https://partner.example/signal",
              "BOT_SIGNAL_URL_3": "https://partner.example/second"}
    votes, statuses = fetch_external_votes(TICKER, config, now=NOW, session=FakeSession())
    assert len(votes) == 2
    assert any("duplicate host" in s for s in statuses)
    assert vote_consensus(votes, ticker=TICKER, now=NOW)["status"] == "AGREE"


def test_no_direction_when_none_connected():
    votes, status = fetch_external_votes(TICKER, {}, now=NOW)
    result = vote_consensus(votes, ticker=TICKER, model_probability=.95, now=NOW)
    assert not votes and status
    assert result["side"] is None
    new = apply_consensus_to_engine({"outcome": "ABOVE", "scalp": "WAIT"}, result)
    assert new["outcome"].startswith("WAIT")
    assert new["trade_review"]["summary"].startswith("NO TRADE")
    assert new["original_model_outcome"] == "ABOVE"
