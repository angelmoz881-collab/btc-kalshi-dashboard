"""Point-in-time feature helpers for BTC/Kalshi settlement-probability research."""
from __future__ import annotations
import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "distance_pct", "minutes_remaining", "ret_1m_pct", "ret_5m_pct",
    "ret_15m_pct", "realized_vol_15m_pct", "ema_gap_pct",
    "volume_ratio_15m", "orderbook_imbalance_pct", "yes_price_cents",
]

def candle_features(candles: pd.DataFrame) -> dict:
    """Create features from timestamp-ordered 1-minute OHLCV candles.

    Input columns: timestamp, open, high, low, close, volume.
    Only candles at or before the prediction timestamp may be included.
    """
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(candles.columns)
    if missing:
        raise ValueError(f"Missing candle columns: {sorted(missing)}")
    d = candles.copy().sort_values("timestamp")
    for col in ["open", "high", "low", "close", "volume"]:
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d.dropna(subset=["close", "volume"])
    if len(d) < 16:
        raise ValueError("At least 16 one-minute candles are required.")
    close, volume = d["close"], d["volume"]
    returns = close.pct_change() * 100
    ema5 = close.ewm(span=5, adjust=False).mean().iloc[-1]
    ema15 = close.ewm(span=15, adjust=False).mean().iloc[-1]
    avg_vol = volume.tail(15).mean()
    return {
        "ret_1m_pct": float((close.iloc[-1] / close.iloc[-2] - 1) * 100),
        "ret_5m_pct": float((close.iloc[-1] / close.iloc[-6] - 1) * 100),
        "ret_15m_pct": float((close.iloc[-1] / close.iloc[-16] - 1) * 100),
        "realized_vol_15m_pct": float(returns.tail(15).std(ddof=1) * np.sqrt(15)),
        "ema_gap_pct": float((ema5 / ema15 - 1) * 100) if ema15 else 0.0,
        "volume_ratio_15m": float(volume.iloc[-1] / avg_vol) if avg_vol else 1.0,
        "spot_price": float(close.iloc[-1]),
    }

def validate_training_csv(df: pd.DataFrame) -> pd.DataFrame:
    required = set(FEATURE_COLUMNS) | {"label_yes"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Training CSV missing columns: {sorted(missing)}")
    out = df.copy()
    for c in required:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=list(required))
    out = out[out["label_yes"].isin([0, 1])]
    if len(out) < 100:
        raise ValueError(f"Only {len(out)} valid rows. Gather more labeled observations (at least 100; 300+ recommended).")
    return out
