"""Synthetic verification for automatic paper scalp and read-only fill reconciliation."""
import unittest
from decimal import Decimal

from auto_scalp import marketable_entry, paper_step
from kalshi_account import reconstruct_position
from scalp_engine import estimated_taker_fee_cents


def snapshot(yes=55, no=43, size=30):
    return {"market": {"status": "active"}, "book_error": None,
            "yes": [(yes, size)], "no": [(no, size)],
            "yes_bid": yes, "yes_ask": 100-no, "no_bid": no, "no_ask": 100-yes}


def buy(side, count, price, fee, time):
    return {"ticker": "KXBTC15M-TEST", "side": side, "action": "buy",
            "count_fp": str(count), f"{side}_price_dollars": str(Decimal(str(price))/100),
            "fee_cost": str(Decimal(str(fee))/100), "ts": time}


def sell(side, count, price, time):
    return {"ticker": "KXBTC15M-TEST", "side": side, "action": "sell",
            "count_fp": str(count), f"{side}_price_dollars": str(Decimal(str(price))/100),
            "fee_cost": "0", "ts": time}


class TestAutoScalp(unittest.TestCase):
    def test_entry_uses_opposite_bid_at_implied_ask(self):
        s = snapshot(yes=55, no=43)
        self.assertEqual(marketable_entry(s, "yes"), 57)
        self.assertEqual(marketable_entry(s, "no"), 45)

    def test_paper_only_arms_then_enters(self):
        s = snapshot(yes=55, no=43)
        watch = {"status": "WATCH YES", "side": "YES"}
        state, event = paper_step({}, "KXBTC15M-TEST", s, watch, 60, {}, 400, [], now=1000)
        self.assertIsNone(state.get("position"))
        self.assertIsNone(event)
        state, event = paper_step(state, "KXBTC15M-TEST", s, watch, 60, {}, 400, [], now=1003)
        self.assertEqual(event["label"], "SIMULATED ENTRY")
        self.assertEqual(state["position"]["entry_price_cents"], 57)
        self.assertEqual(state["position"]["quantity"], 1)
        self.assertEqual(state["position"]["entry_fee_cents"], estimated_taker_fee_cents(57, 1))

    def test_paper_closes_and_cools_down(self):
        s = snapshot()
        watch = {"status": "WATCH YES", "side": "YES"}
        state, _ = paper_step({}, "KXBTC15M-TEST", s, watch, 60, {}, 400, [], now=1000)
        state, _ = paper_step(state, "KXBTC15M-TEST", s, watch, 60, {}, 400, [], now=1003)
        # New executable sell bids significantly above the synthetic entry ask.
        updated = snapshot(yes=72, no=25)
        state, event = paper_step(state, "KXBTC15M-TEST", updated, watch, 60,
                                  {}, 350, [], now=1020)
        self.assertEqual(event["label"], "SIMULATED")
        self.assertEqual(event["exit_reason"], "TAKE PROFIT")
        self.assertIsNone(state["position"])
        self.assertEqual(state["cooldown_ticker"], "KXBTC15M-TEST")
        next_state, event = paper_step(state, "KXBTC15M-TEST", updated, watch,
                                       60, {}, 300, [], now=1050)
        self.assertIsNone(next_state.get("position"))
        self.assertIsNone(event)

    def test_paper_blocked_for_stale_or_missing_depth(self):
        watch = {"status": "WATCH YES", "side": "YES"}
        state, event = paper_step({}, "KXBTC15M-TEST", snapshot(), watch,
                                  60, {}, 400, [], stale=True, now=1000)
        self.assertIsNone(state.get("arming"))
        state, event = paper_step({}, "KXBTC15M-TEST", {"market": {"status": "active"},
            "book_error": None, "no": [], "yes": [(55, 10)]}, watch, 60, {}, 400,
                                  [], now=1000)
        self.assertIsNone(state.get("position"))

    def test_real_fills_reconstruct_after_partial_exit(self):
        position = {"ticker": "KXBTC15M-TEST", "position_fp": "3.00"}
        fills = [buy("yes", 4, 45, 8, 100), buy("yes", 2, 55, 4, 105),
                 sell("yes", 3, 60, 110)]
        result, error = reconstruct_position(position, fills)
        self.assertIsNone(error)
        self.assertEqual(result["source"], "KALSHI LIVE")
        self.assertEqual(result["quantity"], 3)
        # FIFO: 1 @45 and 2 @55 -> average 51.667 cents.
        self.assertAlmostEqual(result["entry_price_cents"], 155/3)
        self.assertAlmostEqual(result["entry_fee_cents"], 6)

    def test_real_opposite_side_requires_reconciliation(self):
        position = {"ticker": "KXBTC15M-TEST", "position_fp": "2"}
        fills = [buy("yes", 3, 45, 6, 100), buy("no", 1, 50, 3, 105)]
        result, error = reconstruct_position(position, fills)
        self.assertIsNone(result)
        self.assertIn("Opposite", error)

    def test_real_insufficient_history_is_not_fake_cost_basis(self):
        position = {"ticker": "KXBTC15M-TEST", "position_fp": "-3"}
        result, error = reconstruct_position(position, [buy("no", 1, 48, 2, 100)])
        self.assertIsNone(result)
        self.assertIn("does not reconcile", error)

    def test_real_no_long_position(self):
        self.assertIsNone(reconstruct_position({"ticker":"KXBTC15M-TEST","position_fp":"0"}, [])[0])


if __name__ == "__main__":
    unittest.main()
