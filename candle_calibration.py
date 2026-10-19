"""Independent, walk-forward calibration for candle-only BTC expiry probabilities.

Inputs are frozen pre-settlement BTC candle probabilities and official YES/NO
settlements. This module deliberately never reads Fusion, market odds or flow.
No predicted probabilities are adjusted until forward validation improves.
"""
import math

import numpy as np
import pandas as pd

MIN_MARKETS = 100
MAX_ADJUSTMENT = 0.12
BLEND = 0.65


def _empty(status="COLLECTING 0/100 MARKETS", n=0, rows=0, base=None):
    return {
        "active": False, "status": status, "resolved_markets": int(n),
        "resolved_rows": int(rows), "validation_markets": 0,
        "raw_brier": base, "calibrated_brier": None,
        "raw_ece": None, "calibrated_ece": None, "hit_rate": None,
        "model": None, "reliability": [],
    }


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), .005, .995)
    return np.log(p / (1.0 - p))


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -25, 25)))


def _fit_platt(prob, labels, weights):
    """Regularized two-parameter calibration; prior is the identity mapping."""
    if len(prob) < 12 or len(np.unique(labels)) < 2:
        return None
    x = _logit(prob)
    w = np.asarray(weights, dtype=float)
    w = w / max(float(w.sum()), 1e-9)
    a, b = 0.0, 1.0
    ridge = 0.035
    for _ in range(80):
        predicted = _sigmoid(a + b * x)
        error = w * (predicted - labels)
        curvature = w * predicted * (1.0 - predicted)
        grad = np.array([error.sum() + ridge * .35 * a,
                         (error * x).sum() + ridge * (b - 1.0)])
        hessian = np.array([
            [curvature.sum() + ridge * .35, (curvature * x).sum()],
            [(curvature * x).sum(), (curvature * x * x).sum() + ridge],
        ])
        try:
            step = np.linalg.solve(hessian, grad)
        except np.linalg.LinAlgError:
            return None
        step = np.clip(step, -.35, .35)
        a -= float(step[0])
        b -= float(step[1])
        b = float(np.clip(b, .10, 2.25))
        if float(np.max(np.abs(step))) < 1e-6:
            break
    return {"intercept": a, "slope": b}


def adjusted_probability(raw, model):
    """Use exactly the same conservative adjustment during validation and live."""
    value = float(raw)
    if not np.isfinite(value) or not 0.0 <= value <= 1.0 or not model:
        return value
    raw = float(np.clip(value, .005, .995))
    learned = float(_sigmoid(model["intercept"] + model["slope"] * _logit([raw])[0]))
    mixed = raw * (1.0 - BLEND) + learned * BLEND
    return float(np.clip(mixed, max(.005, raw - MAX_ADJUSTMENT),
                         min(.995, raw + MAX_ADJUSTMENT)))


def _apply_array(values, model):
    raw = np.clip(np.asarray(values, dtype=float), .005, .995)
    learned = _sigmoid(model["intercept"] + model["slope"] * _logit(raw))
    return np.clip((1.0 - BLEND) * raw + BLEND * learned,
                   np.maximum(.005, raw - MAX_ADJUSTMENT),
                   np.minimum(.995, raw + MAX_ADJUSTMENT))


def _brier(pred, labels, weights):
    return float(np.average((np.asarray(pred) - labels) ** 2, weights=weights))


def _ece(pred, labels, weights):
    """Five-bin weighted expected calibration error on independent holdouts."""
    pred = np.asarray(pred, dtype=float)
    total = float(np.sum(weights))
    result = 0.0
    for lo in np.linspace(0, 1, 6)[:-1]:
        mask = (pred >= lo) & (pred < lo + .2 if lo < .8 else pred <= 1)
        if mask.any():
            fraction = float(np.sum(weights[mask])) / total
            result += fraction * abs(float(np.average(pred[mask], weights=weights[mask])) -
                                     float(np.average(labels[mask], weights=weights[mask])))
    return result


def train_candle_calibrator(history):
    """Expanding forward tests by ticker; never split one market across folds.

    Old Fusion snapshots without a frozen candle prediction cannot be used to
    backfill this learner. All rows must come from predictions stored in advance.
    """
    required = {"ticker", "recorded_utc", "result", "candle_possible_raw_prob"}
    if history is None or not required.issubset(history.columns):
        return _empty()
    data = history.copy()
    data["candle_possible_raw_prob"] = pd.to_numeric(data["candle_possible_raw_prob"], errors="coerce")
    data["_time"] = pd.to_datetime(data["recorded_utc"], utc=True, errors="coerce")
    data = data[
        data["ticker"].astype(str).str.startswith("KXBTC15M")
        & data["result"].astype(str).str.lower().isin(["yes", "no"])
        & data["_time"].notna()
        & data["candle_possible_raw_prob"].between(.005, .995)
    ].copy()
    if data.empty:
        return _empty()
    data = data.drop_duplicates(subset=["ticker", "checkpoint"], keep="first") if "checkpoint" in data else data
    order = (data.groupby("ticker")["_time"].min().sort_values().index.tolist())
    n = len(order)
    group = data["ticker"].astype(str).to_numpy()
    raw = data["candle_possible_raw_prob"].to_numpy(dtype=float)
    y = data["result"].astype(str).str.lower().eq("yes").to_numpy(dtype=float)
    counts = data.groupby("ticker")["ticker"].transform("count").to_numpy(dtype=float)
    w = 1.0 / np.maximum(counts, 1)
    base_brier = _brier(raw, y, w)
    if n < MIN_MARKETS or len(np.unique(y)) < 2:
        return _empty(f"COLLECTING {n}/{MIN_MARKETS} MARKETS", n, len(data), base_brier)

    warmup = max(60, int(n * .60))
    holdout_groups = order[warmup:]
    out_of_fold = np.full(len(data), np.nan)
    for block in np.array_split(np.array(holdout_groups, dtype=object), 4):
        if not len(block):
            continue
        start = order.index(str(block[0]))
        # Purge one immediately preceding contract from each fitting window.
        train_groups = order[:max(0, start - 1)]
        train_mask = np.isin(group, train_groups)
        test_mask = np.isin(group, block)
        model = _fit_platt(raw[train_mask], y[train_mask], w[train_mask])
        if model:
            out_of_fold[test_mask] = _apply_array(raw[test_mask], model)

    valid = np.isfinite(out_of_fold)
    distinct_valid = len(set(group[valid]))
    if distinct_valid < 35 or len(np.unique(y[valid])) < 2:
        output = _empty("WAITING FOR FORWARD VALIDATION", n, len(data), base_brier)
        output["validation_markets"] = distinct_valid
        return output
    raw_brier = _brier(raw[valid], y[valid], w[valid])
    new_brier = _brier(out_of_fold[valid], y[valid], w[valid])
    raw_ece = _ece(raw[valid], y[valid], w[valid])
    new_ece = _ece(out_of_fold[valid], y[valid], w[valid])
    improvement = (raw_brier - new_brier) / max(raw_brier, 1e-9)
    passes = (new_brier < raw_brier - .002
              and improvement > .01 and new_ece <= raw_ece + .02)
    final_model = _fit_platt(raw, y, w) if passes else None
    active = final_model is not None

    # Directional hit rates measure actual historical results, not certainty.
    rows = []
    holdout_prob = np.where(active, out_of_fold[valid], raw[valid])
    favored_conf = np.maximum(holdout_prob, 1.0 - holdout_prob)
    correct = (holdout_prob >= .5) == (y[valid] >= .5)
    valid_tickers = group[valid]
    valid_weights = w[valid]
    for left, right in zip([.5, .6, .7, .8, .9], [.6, .7, .8, .9, 1.00001]):
        mask = (favored_conf >= left) & (favored_conf < right)
        markets = len(set(valid_tickers[mask]))
        rows.append({
            "Confidence range": f"{int(left * 100)}–{min(100, int(right * 100))}%",
            "Markets": markets,
            "Observed hit rate": (f"{np.average(correct[mask], weights=valid_weights[mask]):.1%}"
                                  if markets >= 10 else "Not enough data"),
        })
    return {
        "active": bool(active),
        "status": "VALIDATED CALIBRATION ACTIVE" if active else "VALIDATED · NO PROVEN IMPROVEMENT",
        "resolved_markets": n, "resolved_rows": len(data),
        "validation_markets": distinct_valid,
        "raw_brier": raw_brier, "calibrated_brier": new_brier,
        "raw_ece": raw_ece, "calibrated_ece": new_ece,
        "hit_rate": float(np.average(correct, weights=valid_weights)),
        "model": final_model, "reliability": rows,
    }


def apply_candle_calibration(signal, calibration):
    """Annotate prediction and change its probability only after passed tests."""
    updated = dict(signal or {})
    raw = updated.get("p_above")
    updated["raw_p_above"] = raw
    updated["raw_status"] = updated.get("status", "UNAVAILABLE")
    updated["calibration"] = {
        "active": bool((calibration or {}).get("active")),
        "status": (calibration or {}).get("status", "COLLECTING"),
        "markets": (calibration or {}).get("resolved_markets", 0),
    }
    if raw is None or not updated["calibration"]["active"] or not calibration.get("model"):
        return updated
    if updated.get("status") not in ("POSSIBLE ABOVE", "POSSIBLE BELOW", "NO CLEAR LEAN"):
        return updated
    try:
        new_prob = adjusted_probability(raw, calibration["model"])
    except (ValueError, TypeError, KeyError):
        return updated
    if not np.isfinite(new_prob):
        return updated
    updated["p_above"] = new_prob
    updated["p_below"] = 1.0 - new_prob
    updated["calibrated"] = True
    parts = updated.get("components") or {}
    threshold = float(parts.get("confidence_gate", .62))
    if parts.get("weak_structure"):
        threshold = max(.62, threshold)
    margin = max(new_prob, 1.0 - new_prob)
    if margin < threshold:
        updated["status"] = "NO CLEAR LEAN"
    else:
        updated["status"] = "POSSIBLE " + ("ABOVE" if new_prob > .5 else "BELOW")
    updated["detail"] = (
        f"Candle-only calibrated estimate {margin:.0%} · "
        f"{calibration['validation_markets']} forward-tested markets · "
        "historical calibration, not a guaranteed outcome"
    )
    return updated
