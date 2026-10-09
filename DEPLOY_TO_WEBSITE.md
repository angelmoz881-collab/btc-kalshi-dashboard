# Publish your BTC × Kalshi dashboard as a website

This project is a Streamlit dashboard; it is designed to be viewed on Android or desktop browsers. It remains a research dashboard and does not place trades.

## Deploy using Streamlit Community Cloud

1. Create a GitHub repository named `btc-kalshi-dashboard` at https://github.com/new. For easiest setup, choose **Public** and initialize with a README, then create the repository.
2. Upload the files in this folder to that repo's root. Keep `dashboard.py` and `requirements.txt` in the root. You can use GitHub's **Add file → Upload files** on a computer, or GitHub's browser site on Android. The folders `app/`, `data/`, `docs/`, and `models/` should stay alongside `dashboard.py`.
3. Visit https://share.streamlit.io/ and sign in with GitHub. Choose **Create app** → **Yup, I have an app**.
4. Select repository `YOUR_USERNAME/btc-kalshi-dashboard`, branch `main`, and entrypoint `dashboard.py`.
5. Optionally set a custom subdomain like `btc-kalshi-scalp-desk` if available, then press **Deploy**.
6. When deployment finishes, copy the provided `https://....streamlit.app` URL. Open it in Chrome on Android.

Official instructions: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app

## Notes

- This dashboard loads public BTC candles from Coinbase and optionally a selected Kalshi market/order book. Network/API availability can change.
- Enter the exact market ticker; this version deliberately avoids guessing which strike/expiry you intended.
- No Kalshi API secrets are required for the public data currently used by the dashboard. Never place secrets in public source files.
- The dashboard signals are heuristic research indicators, not verified probabilities or financial advice. Live trading is not included.
