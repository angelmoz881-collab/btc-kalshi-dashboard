# In-app BTC/Kalshi signal alerts

These are **on-screen alerts inside the Streamlit bot**, just like existing Scalp
WATCH and CASH OUT messages. There is **no Telegram or phone setup**.

Your BTC and gold charts, trading signals, profit models, history, and all
existing trading logic are unchanged. Alerts never place orders.

## How to use

Open your BTC dashboard, then open the sidebar **Settings → 🔔 In-app signal
alerts**. **Show popup and status alerts** is enabled by default.

Choose which alerts you want to see:
- Cash-out, profit protection, stop-loss, liquidity and stale-data warnings
- WATCH YES / WATCH NO from your existing scalp entry engine
- Strong observed BTC buying/selling pressure, flow/price divergence and
  possible reversal warnings

When an alert first appears or materially changes, a **popup** appears on
screen. A **compact, always-visible status banner** directly under the BTC
navigation bar shows the highest-priority current warning on all tabs, even
when the popup disappears. **Recent signal alerts** lets you view the last
few alerts for the current contract without searching through the indicators.

The banner favors position/exit warnings over entry and general pressure
signals. Duplicate popup notifications are suppressed while a signal remains
active. Signals must clear and pass a cooldown to re-alert: 45 seconds for
position warnings, 150 seconds for entries, and 180 seconds for market flow
and reversal warnings.

## Limitations

- Alerts only update while the Streamlit dashboard is **open and refreshing**.
  When the app is paused/closed, they cannot provide background notifications.
- The short-term pressure and reversal signals are **research heuristics**,
  not proof of future buyers/sellers or guaranteed profitable trades.
- Confirm quotes and position status before taking any action. The app never
  enters or exits a real trade based on these alerts.
