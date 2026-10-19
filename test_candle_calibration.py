"""Regression tests for independent, settlement-validated candle calibration."""
import unittest

import numpy as np
import pandas as pd

from candle_calibration import (
    MIN_MARKETS, adjusted_probability, apply_candle_calibration,
    train_candle_calibrator,
)
from candle_possible import candle_possible_signal


def history_for_testing(markets=160, biased=True, checkpoints=3):
    """Deterministic fake markets; nothing here represents live accuracy."""
    rng = np.random.default_rng(42)
    rows = []
    for i in range(markets):
        # Clipped strong bias deliberately makes the calibrated model measurably
        # better when forward testing. Unbiased dataset exercises NO activation.
        actual = bool(rng.random() < (.54 if biased else .70))
        raw = (.86 if i % 2 else .75) if biased else .70
        for j in range(checkpoints):
            rows.append({
                "ticker": f"KXBTC15M-TEST-{i:05d}",
                "checkpoint": f"{j}-bucket",
                "recorded_utc": (
                    pd.Timestamp("2026-01-01", tz="UTC") +
                    pd.Timedelta(minutes=15 * i + j)
                ).isoformat(),
                "result": "yes" if actual else "no",
                "candle_possible_raw_prob": raw,
                "market_prob": 1.0 if actual else 0.0,  # must be ignored
                "flow_prob": 1.0 if actual else 0.0,  # must be ignored
            })
    return pd.DataFrame(rows)


def sample_signal():
    return candle_possible_signal(
        70000, 69950, 450,
        {"p_up": .70, "reversal_risk": "LOW", "reasons": ["bullish completed candles"]},
        {"agreement": .80, "outcome_score": 50},
        {"prob": .82}, {"prob": .78},
    )


class CandleCalibrationTests(unittest.TestCase):
    def test_empty_and_legacy_history_do_not_activate(self):
        self.assertFalse(train_candle_calibrator(pd.DataFrame())["active"])
        h = history_for_testing()
        self.assertFalse(train_candle_calibrator(h.drop(columns=["candle_possible_raw_prob"]))["active"])

    def test_independent_markets_not_snapshot_count(self):
        h = history_for_testing(markets=25, checkpoints=10)
        result = train_candle_calibrator(h)
        self.assertFalse(result["active"])
        self.assertEqual(result["resolved_markets"], 25)
        self.assertGreater(result["resolved_rows"], MIN_MARKETS)

    def test_biased_probabilities_improve_with_forward_validation(self):
        result = train_candle_calibrator(history_for_testing())
        self.assertGreaterEqual(result["validation_markets"], 35)
        self.assertTrue(result["active"], result["status"])
        self.assertLess(result["calibrated_brier"], result["raw_brier"])
        self.assertLess(result["calibrated_ece"], result["raw_ece"])
        self.assertEqual(len(result["reliability"]), 5)
        self.assertLess(adjusted_probability(.86, result["model"]), .86)

    def test_reliability_does_not_assert_results_when_small(self):
        result = train_candle_calibrator(history_for_testing())
        for bucket in result["reliability"]:
            if bucket["Markets"] < 10:
                self.assertEqual(bucket["Observed hit rate"], "Not enough data")

    def test_market_flow_cannot_influence_fit(self):
        h = history_for_testing()
        a = train_candle_calibrator(h)
        h["market_prob"] = 1 - h["market_prob"]
        h["flow_prob"] = 1 - h["flow_prob"]
        b = train_candle_calibrator(h)
        self.assertAlmostEqual(a["raw_brier"], b["raw_brier"])
        self.assertAlmostEqual(a["calibrated_brier"], b["calibrated_brier"])
        self.assertEqual(a["model"], b["model"])

    def test_no_settlement_or_wrong_series_is_not_training_data(self):
        h = history_for_testing()
        h["result"] = ""
        self.assertEqual(train_candle_calibrator(h)["resolved_markets"], 0)
        h["result"] = "yes"
        h["ticker"] = "NOT-BTC-SERIES"
        self.assertEqual(train_candle_calibrator(h)["resolved_markets"], 0)

    def test_unvalidated_does_not_change_direction_or_probability(self):
        source = sample_signal()
        result = apply_candle_calibration(source, {"active": False, "status": "COLLECTING"})
        self.assertEqual(result["p_above"], source["p_above"])
        self.assertEqual(result["status"], source["status"])
        self.assertEqual(result["raw_p_above"], source["p_above"])
        self.assertFalse(result["calibrated"])

    def test_validated_adjustment_respects_cap_and_candle_gates(self):
        source = sample_signal()
        calibration = train_candle_calibrator(history_for_testing())
        result = apply_candle_calibration(source, calibration)
        self.assertTrue(result["calibrated"])
        self.assertAlmostEqual(result["raw_p_above"], source["p_above"])
        self.assertLessEqual(abs(result["p_above"] - source["p_above"]), .120001)
        self.assertEqual(result["source"], "BTC CANDLES ONLY")
        self.assertNotIn("market_prob", result["components"])

    def test_stale_candle_prediction_remains_unavailable(self):
        source = sample_signal()
        source.update({"status": "DATA STALE", "p_above": None, "p_below": None})
        calibration = train_candle_calibrator(history_for_testing())
        result = apply_candle_calibration(source, calibration)
        self.assertEqual(result["status"], "DATA STALE")
        self.assertIsNone(result["p_above"])


if __name__ == "__main__":
    unittest.main()
