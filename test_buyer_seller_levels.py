"""Synthetic, deterministic checks for BTC spot buyer/seller level radar."""
import inspect
import unittest

import pandas as pd

from buyer_seller_levels import analyze_buyer_seller_pressure

NOW = pd.Timestamp("2026-10-20T19:00:00Z")


def bars(mode="in_range"):
    rows = []
    for i in range(62):
        t = NOW - pd.Timedelta(minutes=62 - i)
        # Small alternating price candles, without trend or prior breakout.
        base = 100.0 + (0.12 if i % 2 else -0.12)
        rows.append({
            "time": t, "open": base, "high": 100.65, "low": 99.35,
            "close": base, "volume": 100.0,
        })
    if mode == "breakout_up":
        rows[-1].update(open=100.3, high=103.3, low=100.0, close=103.1, volume=1200)
    elif mode == "breakout_down":
        rows[-1].update(open=99.6, high=100.0, low=96.7, close=96.9, volume=1200)
    elif mode == "failed_up":
        rows[-1].update(open=100.2, high=103.2, low=99.3, close=99.5, volume=1200)
    elif mode == "failed_down":
        rows[-1].update(open=99.8, high=100.7, low=96.8, close=100.4, volume=1200)
    elif mode == "unconfirmed":
        rows[-1].update(open=100.3, high=103.3, low=100.0, close=103.1, volume=100)
    return pd.DataFrame(rows)


def executed(side, number=40):
    return [{
        "aggressor": side,
        "notional": 1000.0,
        "id": str(i),
        "time": (NOW - pd.Timedelta(seconds=i)).isoformat(),
    } for i in range(number)]


class LevelPressureTest(unittest.TestCase):
    def test_break_above_with_volume_and_buyers(self):
        result = analyze_buyer_seller_pressure(bars("breakout_up"), executed("buy"), now=NOW)
        self.assertEqual(result["bias"], "BUYERS")
        self.assertIn("VOLUME-CONFIRMED BREAK ABOVE", result["setup"])
        self.assertGreater(result["volume_ratio"], 1.25)
        self.assertGreater(result["tape_imbalance"], .9)

    def test_break_down_with_volume_and_sellers(self):
        result = analyze_buyer_seller_pressure(bars("breakout_down"), executed("sell"), now=NOW)
        self.assertEqual(result["bias"], "SELLERS")
        self.assertIn("VOLUME-CONFIRMED BREAK BELOW", result["setup"])

    def test_rejection_at_high_is_not_confirmed_breakout(self):
        result = analyze_buyer_seller_pressure(bars("failed_up"), executed("sell"), now=NOW)
        self.assertEqual(result["bias"], "SELLERS")
        self.assertIn("FAILED BREAK ABOVE", result["setup"])

    def test_rejection_below_is_possible_buyers(self):
        result = analyze_buyer_seller_pressure(bars("failed_down"), executed("buy"), now=NOW)
        self.assertEqual(result["bias"], "BUYERS")
        self.assertIn("FAILED BREAK BELOW", result["setup"])

    def test_price_alone_cannot_confirm_breakout(self):
        result = analyze_buyer_seller_pressure(bars("unconfirmed"), [], now=NOW)
        self.assertIn("NEEDS CONFIRMATION", result["setup"])
        self.assertNotEqual(result["bias"], "BUYERS")

    def test_trade_imbalance_needs_recent_samples(self):
        old = executed("buy", 40)
        for trade in old:
            trade["time"] = (NOW - pd.Timedelta(minutes=10)).isoformat()
        result = analyze_buyer_seller_pressure(bars("breakout_up"), old, now=NOW)
        self.assertIsNone(result["tape_imbalance"])
        self.assertEqual(result["tape_count"], 0)

    def test_duplicate_tape_ids_are_not_double_counted(self):
        trade = executed("sell", 1)[0]
        result = analyze_buyer_seller_pressure(bars(), [trade] * 40, now=NOW)
        self.assertEqual(result["tape_count"], 1)
        self.assertIsNone(result["tape_imbalance"])

    def test_conflicting_aggressor_volume_blocks_direction(self):
        result = analyze_buyer_seller_pressure(bars("breakout_up"), executed("sell"), now=NOW)
        self.assertEqual(result["status"], "CONFLICT · WAIT")

    def test_unfinished_current_minute_not_confirmed(self):
        pending = bars()
        next_bar = {
            "time": NOW, "open": 100.4, "high": 104.0,
            "low": 100.1, "close": 103.8, "volume": 2000,
        }
        pending = pd.concat([pending, pd.DataFrame([next_bar])], ignore_index=True)
        result = analyze_buyer_seller_pressure(pending, executed("buy"), now=NOW)
        self.assertNotIn("BREAK ABOVE", result["setup"])

    def test_no_strike_or_kalshi_fusion_inputs(self):
        sig = inspect.signature(analyze_buyer_seller_pressure)
        for forbidden in ("strike", "kalshi", "odds", "fusion"):
            self.assertNotIn(forbidden, sig.parameters)
        result = analyze_buyer_seller_pressure(bars(), [], now=NOW)
        self.assertEqual(result["horizon"], "next 1–5 min")

    def test_stale_data_cannot_signal(self):
        self.assertEqual(analyze_buyer_seller_pressure(bars("breakout_up"), stale=True, now=NOW)["status"], "UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
