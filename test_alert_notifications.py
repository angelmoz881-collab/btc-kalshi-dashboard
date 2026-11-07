"""Regression tests for optional notifications; no external network calls."""
import unittest


from alert_notifications import build_signal_alerts, pick_new_alert


class NotificationTests(unittest.TestCase):
    def test_exit_has_priority_and_includes_net_estimate(self):
        alerts = build_signal_alerts(
            "KXBTC15M-TEST",
            watch={"status": "WATCH YES", "side": "YES"},
            exit_report={"status": "CASH OUT SOON", "actionable": True,
                         "net_cents": 3.2, "net_total_dollars": .32,
                         "reason": "Sell bid falling"},
            pressure={"status": "BUYING PRESSURE BUILDING", "strength": "STRONG"},
            source="KALSHI LIVE",
        )
        self.assertEqual(alerts[0]["kind"], "exit")
        self.assertIn("LIVE", alerts[0]["message"])
        self.assertIn("+3.2¢", alerts[0]["message"])
        self.assertNotIn("ENTRY WATCH", " ".join(a["title"] for a in alerts))

    def test_stale_data_suppresses_entry_flow_reversal_but_warns_position(self):
        alerts = build_signal_alerts(
            "TEST", watch={"status": "WATCH NO", "side": "NO"},
            exit_report={"status": "DATA STALE", "reason": "Missing fresh sell bid"},
            pressure={"status": "SELLING PRESSURE BUILDING", "strength": "STRONG"},
            reversal={"status": "POSSIBLE REVERSAL UP", "direction": "UP", "score": 80},
            stale=True,
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["title"], "DATA STALE")

    def test_only_actual_entry_watch_alerts(self):
        self.assertEqual(build_signal_alerts("TEST", watch={"status": "WAIT", "side": "YES"}), [])
        alert = build_signal_alerts("TEST", watch={"status": "WATCH YES", "side": "YES"})
        self.assertEqual(alert[0]["title"], "ENTRY WATCH YES")
        self.assertIn("Research alert", alert[0]["message"])

    def test_pressure_and_reversal_alerts_no_guarantees(self):
        alerts = build_signal_alerts(
            "TEST",
            pressure={"status": "FLOW/PRICE DIVERGENCE · WAIT",
                      "reason": "Strong buys while trade price falls"},
            reversal={"status": "POSSIBLE REVERSAL DOWN", "direction": "DOWN", "score": 60},
        )
        self.assertEqual({x["kind"] for x in alerts}, {"pressure", "reversal"})
        self.assertIn("Strong buys", alerts[0]["detail"])
        self.assertIn("Not a guaranteed turn", alerts[1]["detail"])

    def test_one_alert_per_episode_and_rearm_after_disappearance(self):
        events = build_signal_alerts("TEST", watch={"status": "WATCH NO", "side": "NO"})
        first, state = pick_new_alert(events, now=1000)
        self.assertEqual(first["title"], "ENTRY WATCH NO")
        followup, state = pick_new_alert(events, state, now=1050)
        self.assertIsNone(followup)
        _, state = pick_new_alert([], state, now=1060)
        # Not yet beyond 150-second per-signal cool-down, even if reappearing.
        self.assertIsNone(pick_new_alert(events, state, now=1100)[0])
        fresh, _ = pick_new_alert(events, state, now=1200)
        self.assertIsNotNone(fresh)

    def test_global_gap_defers_lower_priority_event_not_lost(self):
        events = build_signal_alerts(
            "TEST",
            watch={"status": "WATCH YES", "side": "YES"},
            pressure={"status": "BUYING PRESSURE BUILDING", "strength": "STRONG"},
        )
        first, state = pick_new_alert(events, now=10)
        self.assertEqual(first["kind"], "entry")
        queued, state = pick_new_alert(events, state, now=15)
        self.assertIsNone(queued)
        second, state = pick_new_alert(events, state, now=23)
        self.assertEqual(second["kind"], "pressure")

    def test_priority_exit_can_bypass_gap(self):
        watch_events = build_signal_alerts(
            "TEST", watch={"status": "WATCH YES", "side": "YES"})
        _, state = pick_new_alert(watch_events, now=100)
        exit_events = build_signal_alerts(
            "TEST", exit_report={"status": "STOP LOSS REVIEW", "reason": "Manual stop"})
        second, _ = pick_new_alert(exit_events, state, now=101)
        self.assertEqual(second["title"], "STOP LOSS REVIEW")

    def test_notifications_never_need_a_phone_connector(self):
        import inspect
        import alert_notifications
        source = inspect.getsource(alert_notifications)
        self.assertNotIn("telegram", source.lower())
        self.assertNotIn("requests.post", source)
        alerts = build_signal_alerts("TEST", pressure={
            "status": "BUYING PRESSURE BUILDING", "strength": "STRONG"
        })
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["title"], "BUYERS PRESSURE BUILDING")


if __name__ == "__main__":
    unittest.main()
