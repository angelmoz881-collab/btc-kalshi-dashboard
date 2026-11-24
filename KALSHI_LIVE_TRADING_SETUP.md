# Kalshi BTC live execution setup

The BTC SCALP page now has a guarded, manual order panel. It does not run unattended or auto-trade from a prediction. A user must unlock the panel, enable it for the current session, and click an individual order button.

## Required Streamlit Secrets

Add these in the app's Streamlit deployment settings (never commit them to GitHub):

- `KALSHI_TRADE_KEY_ID`: Kalshi API key ID with read and write / trade permissions.
- `KALSHI_TRADE_PRIVATE_KEY`: the matching PEM private key. Keep the original newlines or use escaped `\n`.
- `KALSHI_TRADE_UNLOCK_PASSWORD`: a strong, separate password used to unlock the order controls.
- `KALSHI_TRADE_ENV`: `demo` or `prod`. If omitted, the app defaults to `demo`.

For real position/P&L synchronization on the SCALP page, the existing read-only account sync also needs:

- `KALSHI_READ_KEY_ID`
- `KALSHI_READ_PRIVATE_KEY`
- `SCALP_VIEW_PASSWORD`

The trading key should have `read` and `write::trade` permissions if you want to use it for both order execution and account reads. The existing read-only sync credentials can remain separate.

## Safe first run

1. Create a separate Kalshi Demo account API key and use its private key.
2. Set `KALSHI_TRADE_ENV=demo`.
3. Add the four trade secrets above and deploy the app.
4. Open the BTC SCALP page, unlock trading, and enable manual order buttons.
5. Test only with demo funds and confirm actual fills in the Kalshi Demo account.

To use production, explicitly set `KALSHI_TRADE_ENV=prod`, configure a production key, unlock the panel, and type exactly `I UNDERSTAND LIVE TRADING`. Production orders use real funds.

## Execution limits and behavior

- Only BTC 15-minute tickers beginning `KXBTC15M-` are accepted.
- Entry and exit buttons are shown only when the current market/order book is open and fresh, and an entry watch or synced real position exists.
- Orders are limit-priced, immediate-or-cancel (IOC), and limited to 1–5 whole contracts per click.
- The V2 event-order API quotes the YES book: the code converts YES/NO buys and sells to the correct YES-book bid/ask.
- Unfilled IOC quantity is canceled; the app does not chase prices or automatically retry a POST.
- An HTTP 201 means the exchange accepted the order request, not that the full quantity filled. Check `fill_count`, `remaining_count`, and Kalshi order history.
- Closing a real position requires the existing read-only account sync to reconstruct the live BTC15M position. After a partial exit, refresh sync and verify remaining inventory.
- No automatic trading loop, stop-loss order, take-profit order, or background order execution is enabled. The scalp engine remains an unvalidated research signal; live order actions are manual and user-triggered.

## API reference

Kalshi V2 order creation: https://docs.kalshi.com/api-reference/orders/create-order-v2
Kalshi API key authentication: https://docs.kalshi.com/getting_started/api_keys
