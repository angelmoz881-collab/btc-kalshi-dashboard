# Connect your BTC dashboard to your Kalshi account (read only)

1. Open the Kalshi **website in Chrome**, not just the phone app:
   https://kalshi.com/account/profile
2. Sign in. On the Account & security page, scroll to **API keys**. If missing on Android, use Chrome's **⋮ → Desktop site** option, reload, and verify account/location when prompted.
3. Choose **Create key** and select **Ed25519** (RSA works too). For first-time connection, grant only **Read all data**; do not grant transfers or trading yet.
4. Save the **Key ID** and private PEM once. Kalshi cannot recover the private key afterward.
5. In your Streamlit Community Cloud app, open **Manage app → Settings → Secrets**. Use exactly these names for **LIVE** credentials, or replace LIVE with DEMO for a separate demo environment.

```toml
KALSHI_API_KEY_ID = "YOUR_KEY_ID"
KALSHI_PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
YOUR_PRIVATE_KEY_CONTENT
-----END PRIVATE KEY-----"""
```

Demo uses `KALSHI_DEMO_API_KEY_ID` and `KALSHI_DEMO_PRIVATE_KEY`. Never commit actual credentials to GitHub, send them in chat, or paste them into public dashboard fields.

6. Open your BTC app, expand **🔑 Kalshi account connection** in the sidebar, select **LIVE** or **DEMO**, and click **Test secure connection**. This fetches only account balance to validate authentication and does not show the balance.
7. This branch **does not send Bitcoin trades**. Connecting successfully is not the same as installing unattended trading. A real early-exit auto-scalper must track actual order fills and sell execution and must use a persistent worker, authenticated and continuously running. Exiting with a stop order is not guaranteed if there are no executable bids.

Troubleshooting:
- **No API keys section:** use the website/desktop layout; finish Kalshi account verification if required; ask Kalshi support if missing after that.
- **Unauthorized:** check that Key ID and private PEM belong to the same environment and pair. Save TOML triple quotes and PEM newlines.
- **Access denied:** review key's read permission and account/location restrictions.
- **No secrets detected:** ensure values are in the deployed app's Streamlit **Secrets**, not just a sample file in GitHub.

Do not toggle `KALSHI_ALLOW_LIVE_TRADING` for this BTC feature; it doesn't activate BTC order execution.
