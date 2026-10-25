"""Unit tests: never confuse BTC spot with the official KXBTC15M strike."""
import unittest
from kalshi_btc_strike import kalshi_btc_target, same_contract_target


class StrikeTest(unittest.TestCase):
    def test_official_floor_strike(self):
        p, source = kalshi_btc_target({"floor_strike": 80352.47, "status": "active"})
        self.assertEqual(p, 80352.47)
        self.assertEqual(source, "floor_strike")

    def test_fallback_is_the_same_contract_only(self):
        ticker = "KXBTC15M-26OCT251115-15"
        listing = [{"ticker": ticker, "floor_strike": 80352.47}]
        self.assertEqual(same_contract_target(ticker, {"ticker": ticker, "floor_strike": None}, listing)[0], 80352.47)
        self.assertIsNone(same_contract_target("KXBTC15M-OTHER-30",
                                               {"floor_strike": None}, listing)[0])

    def test_full_detail_preferred_to_listing(self):
        ticker = "KXBTC15M-EXAMPLE-00"
        result = same_contract_target(
            ticker, {"ticker": ticker, "floor_strike": 80320.01},
            [{"ticker": ticker, "floor_strike": 80352.47}],
        )
        self.assertEqual(result, (80320.01, "floor_strike"))

    def test_valid_explicit_target_subtitle(self):
        self.assertEqual(kalshi_btc_target({
            "floor_strike": None,
            "yes_sub_title": "Target price: $80,225.33",
        })[0], 80225.33)

    def test_target_not_generated_from_spot_or_unrelated_numbers(self):
        self.assertIsNone(kalshi_btc_target({
            "close_time": "2026-10-25T17:15:00Z",
            "rules_primary": "Target: $80352 (hypothetical rule text)",
            "coinbase_price": 80352.47,
            "title": "BTC price up in next 15 mins?",
            "floor_strike": None,
        })[0])

    def test_null_invalid_strikes(self):
        for value in ("", None, "unavailable", "NaN", 0, 15, -1, float("inf")):
            self.assertIsNone(kalshi_btc_target({"floor_strike": value})[0])

    def test_custom_strike_only_when_explicit(self):
        self.assertEqual(kalshi_btc_target({
            "custom_strike": {"target_price": "80,500.25"}
        })[0], 80500.25)


if __name__ == "__main__":
    unittest.main()
