"""Safety and statistical regression tests for the independent model arena."""
from datetime import datetime, timedelta, timezone

import pandas as pd

from arena_core import (
    _ask_vwap, analyze_arena, independent_estimate, paper_edge_review,
    score_models, validate_blend, verified_snapshots,
)


def history(n=140, strong_independent=True):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(n):
        yes = i % 2 == 0
        good = .9 if yes else .1
        old = .56 if yes else .44
        weak = .5 if yes else .5
        rows.append({
            "ticker": f"KXBTC15M-{i}", "recorded_utc": (start + timedelta(minutes=15*i)).isoformat(),
            "remaining_sec": 300, "result": "yes" if yes else "no",
            "stat_prob": good if strong_independent else weak,
            "analog_prob": good if strong_independent else weak,
            "flow_prob": good if strong_independent else weak,
            "market_prob": old, "base_prob_above": old,
            "adaptive_prob_above": old,
        })
    return pd.DataFrame(rows)


def snapshot():
    return {"market": {"status": "active"}, "book_error": None,
            "yes_bid": 58, "yes_ask": 60, "no_bid": 40, "no_ask": 42,
            "yes": [(58, 20)], "no": [(40, 20)]}


def test_one_snapshot_per_market_even_with_multiple_checkpoints():
    df = history(n=20)
    copy = df.copy()
    copy["remaining_sec"] = 100
    copy["recorded_utc"] = pd.to_datetime(copy["recorded_utc"], utc=True) + pd.Timedelta(seconds=15)
    doubled = pd.concat([df, copy], ignore_index=True)
    chosen = verified_snapshots(doubled)
    assert len(chosen) == 20
    assert (chosen["remaining_sec"] == 300).all()
    assert score_models(doubled)[0]["Markets"] == 20


def test_chronological_validation_requires_enough_unique_markets():
    assert validate_blend(history(80))["active"] is False
    passed = validate_blend(history(140))
    assert passed["active"] is True
    assert passed["recent_blend_brier"] < passed["recent_base_brier"]
    assert validate_blend(history(140, strong_independent=False))["active"] is False


def test_kalshi_orderbook_uses_opposite_bids_as_asks():
    assert _ask_vwap(snapshot(), "YES", 1) == 60
    assert _ask_vwap(snapshot(), "NO", 1) == 42
    assert _ask_vwap({"no": [(40, .5)]}, "YES", 1) is None


def test_no_trade_until_validated_and_feed_healthy():
    kwargs = {"remaining_sec": 300, "venues": 4, "dispersion_bps": 3,
              "volatility_15m_pct": .25, "min_edge_cents": 10}
    locked = paper_edge_review(.85, snapshot(), False, **kwargs)
    assert locked["status"] == "NO TRADE"
    assert locked["net_ev_cents"] > 10
    assert paper_edge_review(.85, snapshot(), True, **kwargs)["status"] == "PAPER CANDIDATE"
    assert paper_edge_review(.85, snapshot(), True, market_stale=True, **kwargs)["status"] == "NO TRADE"
    assert paper_edge_review(.85, snapshot(), True, venues=1, **{k:v for k,v in kwargs.items() if k != "venues"})["status"] == "NO TRADE"
    assert paper_edge_review(.85, snapshot(), True, remaining_sec=30, **{k:v for k,v in kwargs.items() if k != "remaining_sec"})["status"] == "NO TRADE"


def test_integration_without_real_kalshi_data():
    df = history()
    engine = {"prob_above": .56, "stat": {"prob": .9}, "analog": {"prob": .9},
              "flow_prob": .9, "remaining_sec": 300,
              "brti_proxy": {"count": 4, "dispersion_bps": 3}}
    output = analyze_arena(df, engine, snapshot(), volatility_15m_pct=.2)
    assert output["blend_active"]
    assert .6 < output["blend_p"] < 1
    assert output["paper"]["status"] == "PAPER CANDIDATE"
    assert 0 < independent_estimate({"stat_prob": .9, "analog_prob": .9}) < 1
