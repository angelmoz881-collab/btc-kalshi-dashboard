"""Deterministic synthetic checks for the independent spot pressure radar."""
import unittest
from datetime import datetime, timezone
from scalp_pressure import merge_spot_tape, spot_pressure_radar

NOW = 1_800_000_000.0


def trade(n, age, side, notional=100.0):
    return {"id": str(n), "aggressor": side, "notional": notional,
            "time": datetime.fromtimestamp(NOW - age, timezone.utc).isoformat()}


class ScalpPressureTests(unittest.TestCase):
    def test_merge_deduplicates_and_excludes_old_future_invalid_trades(self):
        data = [trade(1, 2, "buy"), trade(2, 15, "sell"), trade(3, 101, "sell"),
                trade(4, -3, "buy")]
        result = merge_spot_tape([trade(1, 2, "buy")], data, now=NOW)
        self.assertEqual([r["id"] for r in result], ["2", "1"])

    def test_strong_buy_pressure_without_kalshi_confirmation(self):
        tape = [trade(i, i * .55, "buy") for i in range(35)] + [
            trade(i + 100, i * .55, "sell", 70) for i in range(5)]
        result = spot_pressure_radar(tape, structure={"status": "OK", "evidence_score": .55}, now=NOW)
        self.assertEqual(result["bias"], "BUYERS")
        self.assertEqual(result["status"], "BUYING PRESSURE BUILDING")
        self.assertEqual(result["kalshi_confirmation"], "PENDING")

    def test_conflicting_structure_does_not_call_buyers(self):
        tape = [trade(i, i, "buy") for i in range(19)] + [trade(100 + i, i, "sell") for i in range(2)]
        result = spot_pressure_radar(tape, structure={"status": "OK", "evidence_score": -.7}, now=NOW)
        self.assertEqual(result["status"], "CONFLICT · WAIT")
        self.assertEqual(result["bias"], "UNCLEAR")

    def test_stale_or_sparse_data_never_signals_buyers(self):
        tape = [trade(i, i, "buy") for i in range(6)]
        self.assertEqual(spot_pressure_radar(tape, now=NOW)["status"], "COLLECTING FLOW")
        self.assertEqual(spot_pressure_radar(tape, now=NOW, stale=True)["status"], "DATA STALE")

    def test_prior_acceleration_and_seller_pressure(self):
        recent = [trade(i, i * .7, "sell") for i in range(25)]
        prior = [trade(i + 50, 25 + i, "buy") for i in range(15)]
        result = spot_pressure_radar(recent + prior, now=NOW)
        self.assertEqual(result["bias"], "SELLERS")
        self.assertIsNotNone(result["acceleration"])
        self.assertLess(result["acceleration"], 0)


if __name__ == "__main__":
    unittest.main()
