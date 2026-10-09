# Run the BTC × Kalshi dashboard on Android

This project is a mobile-friendly **research dashboard and paper-trading starter**. It does not place real-money orders. The easiest phone-only approach is Termux + the phone's browser.

## 1. Install Termux

Install Termux from its official F-Droid page or official GitHub releases. Avoid random APK download sites. Open Termux after installation.

## 2. Install system packages

Run these commands in Termux:

```sh
pkg update && pkg upgrade
pkg install python git clang make pkg-config rust
pkg install python-numpy python-pandas
```

If `python-numpy` or `python-pandas` is unavailable in your Termux repository, update Termux and try again. Install Termux from one source only; mixing APK sources can cause package errors.

## 3. Put the project on your phone

Extract `kalshi_btc_adaptive_bot_android.zip` with your Android file manager. Move the extracted `kalshi_btc_bot_merged` folder somewhere easy to find, such as `Download/kalshi_btc_bot_merged`.

In Termux, allow shared-storage access:

```sh
termux-setup-storage
cd ~/storage/shared/Download/kalshi_btc_bot_merged
```

Adjust the path if you extracted the folder somewhere else. If the project is in Android's private app storage, use that actual path instead.

## 4. Install dashboard dependencies

```sh
python -m pip install --upgrade pip
pip install -r requirements-mobile.txt
```

If pip reports that a package cannot build on your device, use the matching Termux package where available (`pkg search pandas`, `pkg search numpy`) and retry. Android devices and Termux repositories vary, so installation is not guaranteed on every phone.

## 5. Start the dashboard

```sh
streamlit run dashboard.py --server.address 127.0.0.1 --server.port 8501
```

Keep Termux open. Open Chrome or another browser on the same phone and visit:

`http://127.0.0.1:8501`

To stop the dashboard, return to Termux and press `Ctrl+C`.

## 6. Using it

- View recent BTC-USD 1-minute candles, momentum, EMA trend, and approximate recent volatility.
- Paste the exact ticker for a Kalshi market to inspect its public market details and visible order book.
- Turn on auto-refresh only if you want periodic page reloads; API limits and phone battery use still apply.
- The displayed momentum score is a heuristic, not a validated probability of contract settlement.

## Important limits

- This runs locally on your phone; it is not a 24/7 cloud service. Android battery optimization may pause Termux. Keep the app in the foreground for reliability.
- Public API endpoints and response fields may change. A missing market or empty order book does not necessarily mean there is no opportunity.
- This dashboard does not submit Kalshi orders, and the model/paper modules require prepared, time-aligned historical labels and market snapshots.
- Never put API secrets into the dashboard or share them in chat. Live order execution is intentionally not implemented.

Official links:
- Termux: https://termux.dev/
- Termux F-Droid: https://f-droid.org/packages/com.termux/
- Kalshi API docs: https://docs.kalshi.com/
