import unittest
from decimal import Decimal
from unittest.mock import patch

import kalshi_live_trading as live


class PortfolioCapTests(unittest.TestCase):
    def test_budget_subtracts_positions_and_resting_buys(self):
        snapshot = {
            "equity_dollars": Decimal("1000"),
            "committed_dollars": Decimal("125"),
        }
        self.assertEqual(live.available_scalp_budget(snapshot), Decimal("75.00"))

    def test_budget_never_exceeds_twenty_percent(self):
        snapshot = {
            "equity_dollars": Decimal("500"),
            "committed_dollars": Decimal("0"),
        }
        self.assertEqual(live.available_scalp_budget(snapshot), Decimal("100.00"))

    def test_exposure_at_or_above_cap_blocks_new_allocation(self):
        snapshot = {
            "equity_dollars": Decimal("1000"),
            "committed_dollars": Decimal("200"),
        }
        self.assertEqual(live.available_scalp_budget(snapshot), Decimal("0"))

    def test_unknown_exposure_fails_closed(self):
        with self.assertRaises(ValueError):
            live.available_scalp_budget({"equity_dollars": Decimal("1000"), "committed_dollars": None})

    def test_cannot_raise_cap_above_twenty_percent(self):
        with self.assertRaises(ValueError):
            live.available_scalp_budget(
                {"equity_dollars": Decimal("1000"), "committed_dollars": Decimal("0")},
                Decimal("0.25"),
            )

    def test_contract_sizing_includes_fee_reserve(self):
        self.assertEqual(live.contracts_for_budget(Decimal("10"), Decimal("50")), 18)
        self.assertEqual(live.contracts_for_budget(Decimal("0.50"), Decimal("50")), 0)


class V2OrderMappingTests(unittest.TestCase):
    def _capture(self, outcome, action, price, reduce_only=False):
        with patch.object(live, "_request", return_value={"fill_count": "1.00"}) as request:
            live.submit_ioc_order(
                "key", "pem", "KXBTC15M-TEST", outcome, action, price, 1,
                reduce_only=reduce_only,
            )
            return request.call_args.kwargs["body"]

    def test_buy_yes_uses_yes_bid(self):
        body = self._capture("yes", "buy", Decimal("61"))
        self.assertEqual(body["side"], "bid")
        self.assertEqual(body["price"], "0.6100")

    def test_buy_no_uses_yes_ask_equivalent(self):
        body = self._capture("no", "buy", Decimal("39"))
        self.assertEqual(body["side"], "ask")
        self.assertEqual(body["price"], "0.6100")

    def test_sell_no_uses_yes_bid_equivalent_and_reduce_only(self):
        body = self._capture("no", "sell", Decimal("39"), reduce_only=True)
        self.assertEqual(body["side"], "bid")
        self.assertEqual(body["price"], "0.6100")
        self.assertTrue(body["reduce_only"])
        self.assertEqual(body["time_in_force"], "immediate_or_cancel")

    def test_orders_restricted_to_btc15m(self):
        with self.assertRaises(ValueError):
            live.submit_ioc_order("key", "pem", "KXBTC-OTHER", "yes", "buy", 50, 1)


if __name__ == "__main__":
    unittest.main()
