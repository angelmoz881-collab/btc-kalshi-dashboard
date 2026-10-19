"""Synthetic tests for independent BTC candle-only POSSIBLE outcome research."""
import unittest

from candle_possible import candle_possible_signal


def run(stat=.68, analog=.65, p_up=.73, agreement=.8, score=60,
        remaining=480, stale=False, reversal="LOW"):
    return candle_possible_signal(
        70000, 69900, remaining,
        {"p_up": p_up, "reversal_risk": reversal,
         "reasons": ["bullish engulfing on completed 5m candle", "EMA momentum rising"]},
        {"agreement": agreement, "outcome_score": score},
        {"prob": stat, "sigma_1m": .001},
        {"prob": analog, "effective_n": 35} if analog is not None else None,
        stale=stale,
    )


class CandlePossibleTest(unittest.TestCase):
    def test_bullish_candle_possible_above(self):
        result = run()
        self.assertEqual(result["status"], "POSSIBLE ABOVE")
        self.assertTrue(.60 < result["p_above"] < .75)
        self.assertFalse(result["calibrated"])
        self.assertIn("bullish engulfing", result["detail"])

    def test_bearish_candle_possible_below(self):
        result = run(stat=.25, analog=.28, p_up=.20, score=-60)
        self.assertEqual(result["status"], "POSSIBLE BELOW")
        self.assertLess(result["p_above"], .5)

    def test_no_clear_lean_near_half(self):
        result = run(stat=.50, analog=.50, p_up=.52)
        self.assertEqual(result["status"], "NO CLEAR LEAN")

    def test_opposing_candle_models_are_cautious(self):
        result = run(stat=.79, analog=.27, p_up=.51, agreement=.2, score=5)
        self.assertEqual(result["status"], "NO CLEAR LEAN")
        self.assertIn("disagree", result["detail"])

    def test_high_reversal_risk_increases_gate(self):
        result = run(stat=.58, analog=.58, p_up=.55, reversal="HIGH")
        self.assertEqual(result["status"], "NO CLEAR LEAN")

    def test_final_minute_no_false_settlement_signal(self):
        result = run(remaining=55)
        self.assertEqual(result["status"], "NO CLEAR LEAN")
        self.assertIsNone(result["p_above"])
        self.assertIn("BRTI", result["detail"])

    def test_stale_input_blocks_possible(self):
        result = run(stale=True)
        self.assertEqual(result["status"], "DATA STALE")
        self.assertIsNone(result["p_above"])

    def test_no_strike_blocks(self):
        result = candle_possible_signal(70000, None, 300, {"p_up": .9},
                                        {"outcome_score": 80}, {"prob": .8}, {"prob": .8})
        self.assertEqual(result["status"], "UNAVAILABLE")

    def test_missing_analog_cannot_masquerade_as_robust_consensus(self):
        result = run(stat=.58, analog=None, p_up=.7)
        self.assertEqual(result["status"], "NO CLEAR LEAN")
        self.assertIsNone(result["components"]["candle_history"])

    def test_prediction_only_depends_on_allowed_inputs(self):
        # No Kalshi bids/asks, whale or fusion probability appear in the API.
        self.assertEqual(run().get("source"), "BTC CANDLES ONLY")
        self.assertNotIn("market_prob", run()["components"])
        self.assertNotIn("flow_prob", run()["components"])


if __name__ == "__main__":
    unittest.main()
