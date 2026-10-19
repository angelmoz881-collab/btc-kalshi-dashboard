# Automatic BTC15M scalp signals — setup

**Execution mode:** signals and read-only monitoring only. This project has NO Kalshi trading/write endpoint and does not submit orders.

## Immediately available without API keys

1. Open the existing Streamlit app and select **⚡ SCALP**.
2. It watches the nearest active 15-minute BTC market and evaluates short-horizon candle momentum, actual Kalshi bid movement over at least 12 seconds, spread, visible depth, expiry and opposing reversal clues.
3. When enough evidence agrees, see **ENTRY WATCH YES** or **ENTRY WATCH NO**, including an indicative buy price. A watch is **not a statistically validated buy recommendation**.
4. After two confirmed watches at least 2 seconds apart, it starts an **explicitly SIMULATED 1-contract position** at the observed hypothetical buy ask, with estimated fee. It tracks simulated net P&L using bid-side liquidity, entry/exit fees and slippage reserve. The simulation automatically records an exit warning / paper exit at specified take-profit, reversal, trailing-giveback, max-hold or loss conditions. Paper fills are not real exchange fills.
5. It does not place trades, and the simulated position is **never proof that your real account bought a contract**.

## Optional: Automatically detect *real* Kalshi fills without typing amounts

Kalshi API reference: https://docs.kalshi.com/getting_started/api_keys

1. In Kalshi web account settings, open the **API keys** section (the location may appear under Account & security or Profile). Create a **read-only** key, granting only the necessary read access to positions and fills. **Do not grant trade or transfer rights.** New keys may default to broader permissions; check these before saving.
2. Obtain the Key ID and complete PEM private key directly from Kalshi. The private key may only be shown once. **Never put the key into a GitHub repository, issue, chat, or frontend URL.**
3. In your **Streamlit Community Cloud** app settings → **Secrets**, add the following entries using your actual credentials:

```toml
KALSHI_READ_KEY_ID = "your-read-only-key-id"
KALSHI_READ_PRIVATE_KEY = """
-----BEGIN PRIVATE KEY-----
YOUR_KALSHI_PRIVATE_KEY_TEXT
-----END PRIVATE KEY-----
"""
SCALP_VIEW_PASSWORD = "a-strong-unique-password-not-reused-elsewhere"
```

4. Save secrets and restart your Streamlit app. In the dashboard sidebar, enter the `SCALP_VIEW_PASSWORD` to unlock your own LIVE holdings view. Password protection is **required** so a public Streamlit link does not disclose your positions.
5. When you buy/sell a KXBTC15M contract in Kalshi yourself, the dashboard polls the read-only **positions and fills** endpoints (about every 3 seconds in fast mode), detects your current net side and quantity, and attempts to reconstruct the exact remaining purchase cost from completed fill records. It then estimates available early-sale proceeds at the current order book bids. If history is incomplete or complicated by opposite-side fills, **the bot refuses to invent a cost basis** and displays a warning instead.
6. If you hold multiple BTC15M markets, only your most recently modified position is actively monitored. The app tracks the primary subaccount. It is not a complete portfolio manager.

### Important limitations

- A read-only key does NOT enable automatic selling. You must tap sell in Kalshi.
- The app must remain open. Streamlit session state and paper trades reset with a new browser session or redeployment.
- Alerts are based on polled quotes, which can be stale by seconds, and bid depth can disappear. A cash-out alert is not a guarantee that your sell order will fill at that price.
- Estimates use a general taker-fee formula for exits; contract-specific fees and actual executed fees may differ.
- The scalp watch has **not been validated for positive out-of-sample returns after costs**. The tests check code behavior on synthetic inputs, not profitability.
- Do not set `SCALP_VIEW_PASSWORD` to your Kalshi password. Never reuse passwords between services.
