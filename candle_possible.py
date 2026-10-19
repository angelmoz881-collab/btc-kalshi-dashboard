"""Candle-only tentative BTC 15m above/below strike estimate.

Inputs MUST be sourced from BTC OHLCV, candle indicators and an exchange
contract's strike/remaining clock. Never pass Kalshi bid/ask/orderbook,
predicted YES odds, whale trades, or the blended expiry prediction.
The output is uncalibrated research, not an observed win probability.
"""
import math


def _finite(value):
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError, OverflowError):
        return None


def candle_possible_signal(current_price, strike, remaining_sec, candle_forecast,
                           candle_intel, statistical, historical, stale=False):
    """Tentative expiration estimate from OHLCV alone.

    statistical: parametric_strike_probability() using Coinbase candles.
    historical: empirical_analog_probability() using only BTC candle closes.
    candle_forecast: candle_only_15m_forecast(), whose score captures OHLCV,
      RSI/MACD/EMA, anatomy, breakouts and volume (no Kalshi flow).
    candle_intel: multi_timeframe_candle_intelligence() (1/5/15m OHLCV).
    Historical match probabilities are uncalibrated and share model risks.
    """
    base = {"status": "UNAVAILABLE", "detail": "Waiting for fresh candle data",
            "p_above": None, "p_below": None, "source": "BTC CANDLES ONLY",
            "calibrated": False, "reasons": [], "components": {}}
    price = _finite(current_price)
    target = _finite(strike)
    seconds = _finite(remaining_sec)
    if price is None or price <= 0 or target is None or target <= 0 or seconds is None:
        base["detail"] = "Waiting for BTC candle price, contract strike and expiration"
        return base
    if seconds <= 0:
        base.update(status="EXPIRED", detail="Waiting for official benchmark settlement")
        return base
    if stale:
        base.update(status="DATA STALE", detail="BTC candle data has not refreshed")
        return base
    if seconds <= 75:
        base.update(status="NO CLEAR LEAN",
                    detail="Final-minute official BRTI averaging cannot be inferred reliably from candles alone")
        return base

    stat = _finite((statistical or {}).get("prob"))
    analog = _finite((historical or {}).get("prob"))
    cup = _finite((candle_forecast or {}).get("p_up"))
    if stat is None or not 0 <= stat <= 1:
        base["detail"] = "Need at least 60 valid BTC candles for volatility/strike estimate"
        return base
    if cup is None or not 0 <= cup <= 1:
        base["detail"] = "Candle pattern / momentum estimate is unavailable"
        return base

    # Calibration-conscious fusion: spot-vs-strike distance and horizon dominate,
    # historical *candle* analogs inform the distribution, and the candle-body /
    # EMA / RSI / MACD direction contributes a bounded short-term drift.
    if analog is not None and 0 <= analog <= 1:
        p = .60 * stat + .40 * analog
    else:
        p = stat
        analog = None
    # p_up predicts 15-minute BTC direction, NOT settlement vs strike. Treat
    # it only as a weak, horizon-scaled drift shift; never equate it with p_above.
    horizon_scale = math.sqrt(min(15.0, seconds / 60.0) / 15.0)
    indicator_shift = .10 * (cup - .50) * horizon_scale  # <= 5 percentage points
    p = min(.995, max(.005, p + indicator_shift))
    agreement = _finite((candle_intel or {}).get("agreement")) or 0.0
    score = _finite((candle_intel or {}).get("outcome_score")) or 0.0
    disagreement = abs(stat - analog) if analog is not None else None
    sample = _finite((historical or {}).get("effective_n")) if historical else None
    reversal = str((candle_forecast or {}).get("reversal_risk", "UNKNOWN")).upper()
    reasons = [str(x) for x in (candle_forecast or {}).get("reasons", []) if x]
    high_disagreement = disagreement is not None and disagreement > .23
    weak_structure = agreement < .35 and abs(score) < 15
    confidence_gate = .62 if high_disagreement else .56
    confidence_gate = max(confidence_gate, .60 if reversal == "HIGH" else .56)
    confidence_gate = max(confidence_gate, .60 if analog is None else .56)
    direction = "ABOVE" if p > .5 else "BELOW"
    margin = max(p, 1 - p)
    if margin < confidence_gate or (weak_structure and margin < .62):
        status = "NO CLEAR LEAN"
        detail = "Candles conflict or the strike-adjusted estimate is near 50/50"
    else:
        status = "POSSIBLE " + direction
        detail = f"Candle-only estimate {margin:.0%} · uncalibrated"
    if high_disagreement:
        detail += " · volatility and candle history disagree"
    if reversal == "HIGH":
        detail += " · high reversal risk"
    if reasons:
        detail += " · " + reasons[0]
    return {
        "status": status, "detail": detail,
        "p_above": p, "p_below": 1-p,
        "source": "BTC CANDLES ONLY", "calibrated": False,
        "reasons": reasons[:5],
        "components": {
            "candle_stat": stat,
            "candle_history": analog,
            "candle_direction_15m": cup,
            "timeframe_agreement": agreement,
            "candle_pattern_score": score,
            "indicator_adjust_pp": indicator_shift * 100,
            "historical_effective_n": sample,
            "model_disagreement": disagreement,
            "reversal_risk": reversal,
            "confidence_gate": confidence_gate,
            "weak_structure": bool(weak_structure),
            "horizon_sec": seconds,
            "spot": price, "strike": target,
        }
    }
