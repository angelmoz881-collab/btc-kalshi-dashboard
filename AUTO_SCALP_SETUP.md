# BTC15M scalp — setup and live execution

The BTC scalp has two modes:

- **SIMULATED (default):** watches Kalshi quotes and records hypothetical entries/exits. No real order is sent.
- **LIVE (opt-in):** submits real Kalshi IOC limit orders only after the user arms live execution in the sidebar. Live execution is experimental and can lose money.

## Live mode requirements

Create a dedicated Kalshi API key that has both **read** access and **write::trade** permission. Do not grant transfer permissions. The bot needs read access to balance, positions and resting orders so it can enforce the portfolio allocation ceiling before every entry.

In Streamlit Community Cloud → App → Settings → Secrets, add:

```toml
KALSHI_TRADE_KEY_ID = "your-trading-key-id"
KALSHI_TRADE_PRIVATE_KEY = """
-----BEGIN PRIVATE KEY-----
YOUR_PRIVATE_KEY_TEXT
-----END PRIVATE KEY-----
"""
SCALP_VIEW_PASSWORD = "a-strong-unique-password"
```

You may keep separate read-only credentials as `KALSHI_READ_KEY_ID` and `KALSHI_READ_PRIVATE_KEY`. If both are configured, the dashboard uses the read-only key for displaying holdings and the trading key only for risk checks and order placement.

**Never paste your private key into chat, commit it to GitHub, or put it in client-side code.** Store it only in the server-side Streamlit Secrets panel. If the key has been exposed, revoke it in Kalshi and create a new one.

## How live scalp sizing works

The live scalp has a hard allocation ceiling of **20% of portfolio equity**:

1. Fetches the current Kalshi portfolio value.
2. Reads all unsettled open positions and all resting orders.
3. Counts existing position exposure and resting buy-order exposure against the scalp allocation.
4. Calculates remaining headroom under 20%.
5. Includes a per-contract fee reserve when calculating whole-contract quantity.
6. Blocks the entry if balance, positions, orders, exposure or price data cannot be verified.

Example: with $1,000 portfolio equity, the total allocation ceiling is $200. If existing positions and resting buy orders already use $125, no more than $75 remains for the scalp. The cap is portfolio-wide, not 20% for every new order.

**The 20% ceiling is an allocation limit, not a maximum-loss guarantee.** Contracts can lose most or all of their purchase cost.

## Entry and exit behavior

- Live execution must be explicitly armed in the sidebar; it defaults OFF.
- Entries require two matching fresh scalp watches at least two seconds apart, and only one entry attempt is made per 15-minute contract.
- Entry orders are IOC limit orders using the observed ask-side price and visible depth. Any unfilled remainder is canceled by the exchange.
- Exits use reduce-only IOC orders, so an exit cannot intentionally increase or reverse the holding.
- Order acceptance is not the same as a fill. The dashboard reports the fill count and the user must verify the final Kalshi position/order status.
- If portfolio data is incomplete, an open position has unknown exposure, the book is stale, or risk cannot be calculated, the bot blocks the entry.
- Disable **ARM LIVE BTC SCALP ORDERS** in the sidebar to stop new live entries. Always verify open orders and positions directly in Kalshi.

## Existing read-only account view

The private holdings panel is protected by `SCALP_VIEW_PASSWORD`. Unlock it in the dashboard sidebar to show actual BTC15M positions and reconstruct entry cost from fills. The password is a dashboard view lock; it is not a Kalshi API key and does not grant trading rights.

## Important limitations and risk

- The scalp signal is heuristic and has **not been proven to have positive out-of-sample returns after fees and slippage**.
- IOC orders can be partially filled or not filled at all. A price observed in the order book is not a guaranteed execution price.
- Kalshi API schemas, fee schedules and market price increments can change. Confirm order status, fills and positions directly in Kalshi.
- The dashboard must remain open and updating for its automated logic to run.
- This code has not been validated against a live trading account in this repository environment. Keep live mode OFF until you have reviewed it and tested with a demo account or the smallest amount you are comfortable risking.
