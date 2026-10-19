"""Synthetic unit tests for the experimental, manual-only scalp exit logic."""
import unittest

from scalp_engine import (
    estimated_taker_fee_cents,
    entry_watch,
    marketable_exit,
    quote_trend,
    review_open_position,
)


def book(yes_bid=55, no_bid=43, qty=50):
    return {
        "market": {"status": "active"},
        "yes": [(yes_bid, qty), (yes_bid - 2, qty)],
        "no": [(no_bid, qty), (no_bid - 2, qty)],
        "yes_bid": yes_bid,
        "yes_ask": yes_bid + 2,
        "no_bid": no_bid,
        "no_ask": no_bid + 2,
        "book_error": None,
    }


def position(**update):
    result = dict(side="yes", ticker="KXBTC15M-TEST", quantity=10,
                  entry_price_cents=45, entry_fee_cents=0,
                  entry_score=55, opened_at=1000, peak_net_cents=0)
    result.update(update)
    return result


class TestScalpEngine(unittest.TestCase):
    def test_fee_rounding_per_order(self):
        self.assertEqual(estimated_taker_fee_cents(50, 1), 2)
        self.assertEqual(estimated_taker_fee_cents(50, 100), 175)

    def test_full_size_vwap_not_best_bid(self):
        b = book()
        b["yes"] = [(50, 5), (48, 10)]
        result = marketable_exit(b, "yes", 10)
        self.assertTrue(result["ok"])
        self.assertEqual(result["bid_vwap"], 49)

    def test_missing_depth_is_not_a_profitable_fill(self):
        b = book(qty=2)
        result = marketable_exit(b, "yes", 10)
        self.assertFalse(result["ok"])
        self.assertLess(result["visible"], 10)

    def test_bid_trend_requires_observed_history(self):
        self.assertIsNone(quote_trend([{"t": 100, "yes_bid": 51}], "yes", now=100))
        history = [{"t": 80, "yes_bid": 51}, {"t": 100, "yes_bid": 54}]
        self.assertEqual(quote_trend(history, "yes", now=100), 3)

    def test_entry_watch_requires_bid_confirmation(self):
        b = book(yes_bid=55)
        history = [{"t": 80, "yes_bid": 53}, {"t": 100, "yes_bid": 55}]
        # Mock the clock by making these values relative to current time.
        import time
        current = time.time()
        history = [{"t": current - 25, "yes_bid": 53}, {"t": current, "yes_bid": 55}]
        watch = entry_watch(b, 60, .80, {}, 400, history=history)
        self.assertEqual(watch["status"], "WATCH YES")
        self.assertFalse(watch["validated"])
        blocked = entry_watch(b, 60, .80, {"direction": "DOWN", "score": 60},
                              400, history=history)
        self.assertEqual(blocked["status"], "WAIT")

    def test_profit_target_is_net_after_fees_and_slippage(self):
        result = review_open_position(position(), book(yes_bid=55), 50, {}, 300,
                                      slippage_cents=1, target_cents=5, now=1100)
        self.assertTrue(result["actionable"])
        self.assertEqual(result["status"], "TAKE PROFIT")
        self.assertGreaterEqual(result["net_cents"], 5)

    def test_prepare_to_cash_on_bid_deterioration(self):
        history = [{"t": 1080, "yes_bid": 53}, {"t": 1100, "yes_bid": 51}]
        result = review_open_position(position(), book(yes_bid=51), 20, {}, 250,
                                      history=history, target_cents=6, now=1100)
        self.assertEqual(result["status"], "CASH OUT SOON")
        self.assertGreater(result["net_cents"], 0)

    def test_trailing_warning_uses_observed_net_peak(self):
        result = review_open_position(position(peak_net_cents=10), book(yes_bid=51),
                                      50, {}, 280, trail_cents=2,
                                      target_cents=8, now=1100)
        self.assertEqual(result["status"], "PROTECT PROFIT")

    def test_stale_quote_refuses_to_estimate_profit(self):
        result = review_open_position(position(), book(), 50, {}, 300,
                                      stale=True, now=1100)
        self.assertEqual(result["status"], "DATA STALE")
        self.assertIsNone(result["net_cents"])


if __name__ == "__main__":
    unittest.main()
