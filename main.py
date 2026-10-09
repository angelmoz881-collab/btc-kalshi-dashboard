"""Public-data smoke test and timestamped snapshot collector. No order endpoints."""
from __future__ import annotations
import argparse, os, time
from datetime import datetime, timezone
from pathlib import Path
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
COINBASE = "https://api.exchange.coinbase.com"
KALSHI = os.getenv("KALSHI_BASE_URL", "https://api.elections.kalshi.com/trade-api/v2").rstrip("/")
SERIES_FILTER = os.getenv("KALSHI_SERIES_FILTER", "KXBTC")
DATA_DIR = Path("data")
HEADERS = {"User-Agent": "BTC-Kalshi-Adaptive-PaperBot/0.1", "Accept": "application/json"}

def fetch_candles():
    # Coinbase rows: [time, low, high, open, close, volume]
    r = requests.get(f"{COINBASE}/products/BTC-USD/candles",
                     params={"granularity": 60}, headers=HEADERS, timeout=15)
    r.raise_for_status()
    rows = r.json()
    df = pd.DataFrame(rows, columns=["timestamp", "low", "high", "open", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)

def fetch_markets():
    # Public endpoint supports pagination; this starter fetches one page and filters locally.
    r = requests.get(f"{KALSHI}/markets",
        params={"limit": 1000, "status": "open"}, headers=HEADERS, timeout=20)
    r.raise_for_status()
    payload = r.json()
    markets = payload.get("markets", [])
    filt = SERIES_FILTER.upper()
    if filt:
        markets = [m for m in markets if filt in str(m.get("ticker", "")).upper()
                   or filt in str(m.get("event_ticker", "")).upper()
                   or filt in str(m.get("series_ticker", "")).upper()]
    return markets, payload.get("cursor")

def append_rows(path: Path, rows: pd.DataFrame):
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows.empty:
        return
    rows.to_csv(path, mode="a", header=not path.exists(), index=False)

def snapshot_once():
    now = datetime.now(timezone.utc).isoformat()
    candles = fetch_candles()
    candles["collected_at"] = now
    append_rows(DATA_DIR / "btc_candles_snapshots.csv", candles)
    markets, cursor = fetch_markets()
    market_rows = []
    for m in markets:
        market_rows.append({
            "collected_at": now,
            "ticker": m.get("ticker"),
            "event_ticker": m.get("event_ticker"),
            "series_ticker": m.get("series_ticker"),
            "title": m.get("title"),
            "subtitle": m.get("subtitle"),
            "status": m.get("status"),
            "open_time": m.get("open_time"),
            "close_time": m.get("close_time"),
            "expiration_time": m.get("expiration_time"),
            "yes_bid": m.get("yes_bid"),
            "yes_ask": m.get("yes_ask"),
            "no_bid": m.get("no_bid"),
            "no_ask": m.get("no_ask"),
            "floor_strike": m.get("floor_strike"),
            "cap_strike": m.get("cap_strike"),
            "strike_type": m.get("strike_type"),
        })
    append_rows(DATA_DIR / "kalshi_market_snapshots.csv", pd.DataFrame(market_rows))
    print(f"[{now}] BTC candles: {len(candles)} rows; matching open markets: {len(market_rows)}; cursor returned: {bool(cursor)}")
    if market_rows:
        print("Sample markets:")
        for m in market_rows[:8]:
            print(f"  {m['ticker']} | {m['title'] or m['subtitle']}")
    else:
        print("No markets matched the configured series filter. Check KALSHI_SERIES_FILTER against current Kalshi tickers.")
    print("Snapshots saved under data/. This process does not place trades.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Collect one snapshot (default).")
    parser.add_argument("--loop", action="store_true", help="Collect snapshots repeatedly.")
    parser.add_argument("--interval", type=int, default=15, help="Loop interval in seconds (default 15).")
    args = parser.parse_args()
    if args.loop:
        while True:
            try:
                snapshot_once()
            except Exception as exc:
                print(f"Snapshot error: {exc}")
            time.sleep(max(5, args.interval))
    else:
        snapshot_once()

if __name__ == "__main__":
    main()
