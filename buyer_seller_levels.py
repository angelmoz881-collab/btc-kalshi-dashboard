"""BTC spot breakout/rejection and buyer/seller pressure research.

This is a forward-looking *heuristic* for the next 1-5 minutes, not an
expiry probability and not a validated trading signal. It never reads Kalshi
prices, Kalshi book liquidity, the strike or the fused settlement model.
Coinbase spot trade "side" is the MAKER side; conversion to aggressor must be
done by the caller. Ordinary OHLCV volume alone has no buy/sell sign.
"""
import math
import numpy as np
import pandas as pd


def _empty(reason):
    return {
        "status": "UNAVAILABLE", "bias": "NO CLEAR CONTROL",
        "setup": "DATA UNAVAILABLE", "detail": reason,
        "support": None, "resistance": None, "range_high": None,
        "range_low": None, "level": None, "volume_ratio": None,
        "tape_imbalance": None, "tape_count": 0,
        "evidence_score": 0.0, "evidence": [], "horizon": "next 1–5 min",
    }


def _trades(tape, now):
    """Measure capped aggressive *executed* dollar flow, only from recent ticks.

    API samples are bounded and incomplete. Old/bad and repeated trade IDs are
    ignored; do not interpret these executions as known future orders.
    """
    latest = []
    seen = set()
    for item in tape or []:
        if not isinstance(item, dict):
            continue
        trade_id = str(item.get("id", ""))
        if trade_id and trade_id in seen:
            continue
        side = str(item.get("aggressor", "")).lower()
        if side not in ("buy", "sell"):
            continue
        try:
            value = float(item["notional"])
            age = (now - pd.to_datetime(item["time"], utc=True)).total_seconds()
        except (ValueError, TypeError, KeyError, OverflowError):
            continue
        if not math.isfinite(value) or value <= 0 or not (0 <= age <= 90):
            continue
        if trade_id:
            seen.add(trade_id)
        latest.append((1.0 if side == "buy" else -1.0, value))
    if len(latest) < 12:
        return None, len(latest)
    values = np.asarray([p[1] for p in latest], dtype=float)
    # One block trade should not make a 100-trade sample appear unanimous.
    cap = max(float(np.median(values)) * 8.0, float(np.quantile(values, .90)))
    weighted = np.minimum(values, cap)
    signed = np.asarray([p[0] for p in latest], dtype=float)
    imbalance = float(np.dot(signed, weighted) / max(float(weighted.sum()), 1e-9))
    return imbalance, len(latest)


def _levels(candles, atr):
    """Previous confirmed swing extrema plus current 20-minute range.

    Swing pivots use two subsequent CLOSED candles before confirmation.
    """
    before = candles.iloc[:-1]
    high = before["high"].to_numpy(dtype=float)
    low = before["low"].to_numpy(dtype=float)
    clusters = {"high": [], "low": []}
    for i in range(2, len(before) - 2):
        if high[i] >= max(high[i-2:i]) and high[i] > max(high[i+1:i+3]):
            clusters["high"].append(float(high[i]))
        if low[i] <= min(low[i-2:i]) and low[i] < min(low[i+1:i+3]):
            clusters["low"].append(float(low[i]))
    # An explicit recent range boundary is always available even without pivots.
    window = before.tail(20)
    upper = float(window["high"].max())
    lower = float(window["low"].min())
    price = float(candles["close"].iloc[-1])
    margin = max(atr * .30, price * .00003)
    supports = [v for v in clusters["low"] if v < price + margin]
    resistances = [v for v in clusters["high"] if v > price - margin]
    supports.append(lower)
    resistances.append(upper)
    support = max((v for v in supports if v <= price + margin), default=lower)
    resistance = min((v for v in resistances if v >= price - margin), default=upper)
    return float(support), float(resistance), upper, lower


def analyze_buyer_seller_pressure(frame, tape=None, stale=False, now=None):
    """Closed-candle breakout/rejection research plus recent spot executions.

    A confirming breakout requires the close beyond the PRIOR range with
    relative volume AND a meaningful body. A wick outside and close back
    inside is a rejection. Score direction is distinct from settlement strike.
    """
    if stale:
        return _empty("Candle feed stale; waiting for fresh BTC data.")
    if frame is None or len(frame) < 55:
        return _empty("Need at least 55 one-minute BTC candles.")
    data = frame.copy()
    for column in ("open", "high", "low", "close", "volume"):
        if column not in data:
            return _empty("Missing BTC OHLCV data.")
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.replace([np.inf, -np.inf], np.nan).dropna(subset=["open", "high", "low", "close", "volume"])
    if "time" in data.columns:
        data["time"] = pd.to_datetime(data["time"], utc=True, errors="coerce")
        data = data.dropna(subset=["time"]).sort_values("time").drop_duplicates("time")
    else:
        data = data.reset_index(drop=True)
    current = pd.Timestamp.now(tz="UTC") if now is None else pd.to_datetime(now, utc=True)
    # Coinbase returns the currently forming 1m bar. No breakout is confirmed
    # until its close, and the live partial volume must not enter the baseline.
    if "time" in data.columns and len(data):
        last_time = data["time"].iloc[-1]
        if last_time.floor("min") >= current.floor("min"):
            data = data.iloc[:-1].copy()
        if len(data) and (current - data["time"].iloc[-1]).total_seconds() > 185:
            return _empty("Completed BTC candles older than 3 minutes.")
    if len(data) < 54:
        return _empty("Waiting for enough completed 1m BTC candles.")
    data = data.tail(180).reset_index(drop=True)
    price = float(data["close"].iloc[-1])
    if not math.isfinite(price) or price <= 0 or (data["volume"] < 0).any():
        return _empty("Invalid candle prices or volume.")
    true_range = pd.concat([
        data["high"] - data["low"],
        (data["high"] - data["close"].shift(1)).abs(),
        (data["low"] - data["close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = float(true_range.tail(14).median())
    if not math.isfinite(atr) or atr <= 0:
        return _empty("No usable volatility to resolve nearby levels.")
    last = data.iloc[-1]
    prior = data.iloc[-21:-1]
    upper = float(prior["high"].max())
    lower = float(prior["low"].min())
    buffer = max(atr * .08, price * .000015)
    candle_range = max(float(last["high"] - last["low"]), 1e-8)
    body = abs(float(last["close"] - last["open"])) / candle_range
    close_pos = float((last["close"] - last["low"]) / candle_range)
    baseline = float(data["volume"].iloc[-41:-1].median())
    vr = float(last["volume"] / baseline) if baseline > 0 else None
    support, resistance, _, _ = _levels(data, atr)
    tape_balance, trade_count = _trades(tape, current)

    up_break = price > upper + buffer
    down_break = price < lower - buffer
    up_wick_fail = last["high"] > upper + buffer and price < upper - buffer * .25
    down_wick_fail = last["low"] < lower - buffer and price > lower + buffer * .25
    prior2 = data.iloc[-22:-2]
    prior_upper = float(prior2["high"].max())
    prior_lower = float(prior2["low"].min())
    up_return = (
        data["close"].iloc[-2] > prior_upper + buffer
        and price < prior_upper - buffer * .25
    )
    down_return = (
        data["close"].iloc[-2] < prior_lower - buffer
        and price > prior_lower + buffer * .25
    )
    vol_confirm = vr is not None and vr >= 1.25
    strong_up = up_break and vol_confirm and body >= .45 and close_pos >= .70
    strong_down = down_break and vol_confirm and body >= .45 and close_pos <= .30

    setup = "IN RANGE"
    level = None
    structural = 0.0
    if up_wick_fail or up_return:
        setup, level, structural = "FAILED BREAK ABOVE · SELLER DEFENSE", upper, -.90
    elif down_wick_fail or down_return:
        setup, level, structural = "FAILED BREAK BELOW · BUYER DEFENSE", lower, .90
    elif strong_up:
        setup, level, structural = "VOLUME-CONFIRMED BREAK ABOVE", upper, .90
    elif strong_down:
        setup, level, structural = "VOLUME-CONFIRMED BREAK BELOW", lower, -.90
    elif up_break:
        setup, level, structural = "BREAK ABOVE · NEEDS CONFIRMATION", upper, .24
    elif down_break:
        setup, level, structural = "BREAK BELOW · NEEDS CONFIRMATION", lower, -.24

    # Retest: earlier breakout and a return to its broken boundary that holds
    # on the latest closed bar. Only use bars that were already closed.
    if setup == "IN RANGE":
        for k in (2, 3, 4):
            earlier = data.iloc[:-k]
            if len(earlier) < 22:
                continue
            pivot = data.iloc[-k]
            old_high = float(earlier["high"].tail(20).max())
            old_low = float(earlier["low"].tail(20).min())
            if (pivot["close"] > old_high + buffer and
                    last["low"] <= old_high + buffer and price > old_high + buffer * .25):
                setup, level, structural = "BREAKOUT RETEST HELD · BUYER DEFENSE", old_high, .78
                break
            if (pivot["close"] < old_low - buffer and
                    last["high"] >= old_low - buffer and price < old_low - buffer * .25):
                setup, level, structural = "BREAKDOWN RETEST HELD · SELLER DEFENSE", old_low, -.78
                break

    # Volume-weighted candle flow is an *inference*: volume belongs to both
    # the executed buyer and seller. Only the live tape supports aggressor labels.
    recent = data.tail(5)
    spread = np.maximum((recent["high"] - recent["low"]).to_numpy(float), 1e-8)
    placement = np.clip((2 * recent["close"].to_numpy(float)
                         - recent["high"].to_numpy(float)
                         - recent["low"].to_numpy(float)) / spread, -1, 1)
    recent_vol = recent["volume"].to_numpy(float)
    bar_pressure = float(np.dot(placement, recent_vol) / max(recent_vol.sum(), 1e-8))
    # Momentum cannot unilaterally decide direction.
    trend_strength = float(np.tanh(
        (price - float(data["close"].iloc[-6])) / max(3.0 * atr, 1e-8)
    ))
    pressure_score = (.48 * structural + .26 * bar_pressure
                      + .11 * trend_strength
                      + (.15 * tape_balance if tape_balance is not None else 0.0))
    evidence = [f"Completed 1m close; volume {vr:.2f}× baseline" if vr is not None else
                "1m candle volume baseline unavailable"]
    if tape_balance is None:
        evidence.append("Live trade-side sample too small/stale; aggressor imbalance unavailable")
    else:
        evidence.append(
            f"Coinbase executed aggressor imbalance {tape_balance:+.0%} ({trade_count} trades / latest 90s)"
        )
    evidence.append(f"5-bar candle close-position pressure {bar_pressure:+.0%} (volume proxy only)")
    if setup != "IN RANGE":
        evidence.append(setup)
    # Trap setup can conflict with recent aggressive flow: avoid a confident call.
    conflict = (abs(structural) >= .70 and tape_balance is not None and
                np.sign(structural) != np.sign(tape_balance) and abs(tape_balance) > .30)
    if conflict:
        status, bias = "CONFLICT · WAIT", "NO CLEAR CONTROL"
    elif pressure_score >= .32 and (structural >= .70 or
                                    (bar_pressure > .20 and tape_balance is not None and tape_balance > .16)):
        status, bias = "BUYERS MAY TAKE CONTROL", "BUYERS"
    elif pressure_score <= -.32 and (structural <= -.70 or
                                     (bar_pressure < -.20 and tape_balance is not None and tape_balance < -.16)):
        status, bias = "SELLERS MAY TAKE CONTROL", "SELLERS"
    else:
        status, bias = "WAIT · NO CONFIRMED CONTROL", "NO CLEAR CONTROL"

    if setup == "IN RANGE":
        if price <= resistance and resistance - price < 1.5 * atr:
            setup = "TESTING RESISTANCE · WATCH FOR REJECTION OR BREAK"
            level = resistance
        elif price >= support and price - support < 1.5 * atr:
            setup = "TESTING SUPPORT · WATCH FOR DEFENSE OR BREAK"
            level = support

    detail = (
        "Heuristic for possible next 1–5m pressure; this is not a calibrated "
        "probability of future orders, a Kalshi settlement forecast, or trade advice."
    )
    return {
        "status": status, "bias": bias, "setup": setup, "detail": detail,
        "support": support, "resistance": resistance, "range_high": upper,
        "range_low": lower, "level": level, "volume_ratio": vr,
        "tape_imbalance": tape_balance, "tape_count": trade_count,
        "evidence_score": float(np.clip(pressure_score, -1, 1)),
        "evidence": evidence, "horizon": "next 1–5 min",
    }
