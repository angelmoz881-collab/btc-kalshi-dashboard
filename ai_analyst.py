"""OpenAI-powered BTC analyst. Read-only: never submits or manages orders."""
import json
import os
import time
from datetime import datetime, timedelta, timezone

import requests


SYSTEM_PROMPT = """You are a cautious BTC market analyst embedded in a trading dashboard.
Analyze only the supplied BTC OHLCV candles and derived indicator context. The candles
are 15-minute bars and the requested forecast horizon is exactly 60 minutes (four bars).
Return one JSON object only with these keys:
direction (UP, DOWN, or UNCERTAIN), confidence (0-100; calibrated humility, not a
claim of statistical certainty), probability_up (0-1), current_price, expected_price_60m,
range_low_60m, range_high_60m, entry_zone_low, entry_zone_high, stop_loss_reference,
take_profit_1, take_profit_2, invalidation_level, reasons (array of 2-5 short strings),
risks (array of 1-4 short strings), summary (one concise paragraph).
Use null for levels you cannot reasonably infer. Do not invent live prices or indicators.
If evidence conflicts, candles are stale/insufficient, or no clear edge exists, choose
UNCERTAIN. This is analysis, not financial advice. Never imply a trade was executed.
The probability and confidence must reflect uncertainty. Respect nearby support/resistance
and do not recommend an entry when reward/risk is clearly poor."""


def _extract_response_text(payload):
    if isinstance(payload, dict) and payload.get("output_text"):
        return payload["output_text"]
    parts = []
    for item in (payload.get("output") or []):
        for content in (item.get("content") or []):
            if content.get("type") in ("output_text", "text") and content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts)


def _append_snapshot(snapshot):
    path = os.environ.get("AI_FORECAST_LOG", "data/ai_forecasts.jsonl")
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(snapshot, separators=(",", ":"), allow_nan=False) + "\n")
        return path
    except (OSError, TypeError, ValueError):
        return None


def request_ai_analysis(api_key, model, candles_15m, context):
    """Request and journal a single 15m-input / 60m-horizon analysis."""
    if not api_key:
        return {"status": "not_configured", "error": "Add OPENAI_API_KEY to Streamlit Secrets."}
    if candles_15m is None or len(candles_15m) < 20:
        return {"status": "insufficient_data", "error": "At least 20 15-minute candles are required."}

    rows = []
    for row in candles_15m.tail(36).to_dict("records"):
        item = {}
        for key in ("time", "open", "high", "low", "close", "volume"):
            value = row.get(key)
            if key == "time":
                item[key] = str(value)
            elif value is not None:
                try:
                    item[key] = round(float(value), 6)
                except (TypeError, ValueError):
                    item[key] = None
        rows.append(item)
    try:
        current_price = float(candles_15m.iloc[-1]["close"])
    except (KeyError, TypeError, ValueError):
        return {"status": "insufficient_data", "error": "Latest 15-minute close is unavailable."}

    now = datetime.now(timezone.utc)
    prompt = {
        "requested_input_timeframe": "15m",
        "requested_prediction_horizon_minutes": 60,
        "forecast_created_at_utc": now.isoformat(),
        "target_time_utc": (now + timedelta(minutes=60)).isoformat(),
        "current_btc_price": current_price,
        "technical_context": context,
        "last_36_15m_ohlcv_bars": rows,
    }
    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": "Bearer " + str(api_key), "Content-Type": "application/json"},
            json={
                "model": model or "gpt-6",
                "instructions": SYSTEM_PROMPT,
                "input": json.dumps(prompt, separators=(",", ":"), default=str),
                "text": {"format": {"type": "json_object"}},
                "max_output_tokens": 1000,
            },
            timeout=30,
        )
        if not response.ok:
            safe_message = "OpenAI API request failed (HTTP {}). Check API key, model access and billing.".format(response.status_code)
            return {"status": "error", "error": safe_message}
        body = response.json()
        text = _extract_response_text(body)
        result = json.loads(text)
        direction = str(result.get("direction", "UNCERTAIN")).upper()
        if direction not in ("UP", "DOWN", "UNCERTAIN"):
            direction = "UNCERTAIN"
        confidence = max(0.0, min(100.0, float(result.get("confidence", 0))))
        probability_up = max(0.0, min(1.0, float(result.get("probability_up", 0.5))))
        result.update({
            "direction": direction,
            "confidence": confidence,
            "probability_up": probability_up,
            "status": "ok",
            "created_at_utc": now.isoformat(),
            "target_time_utc": (now + timedelta(minutes=60)).isoformat(),
            "input_timeframe_minutes": 15,
            "horizon_minutes": 60,
            "starting_price": current_price,
            "model": model or "gpt-6",
        })
        log_record = {
            "created_at_utc": result["created_at_utc"],
            "target_time_utc": result["target_time_utc"],
            "input_timeframe_minutes": 15,
            "horizon_minutes": 60,
            "model": result["model"],
            "starting_price": current_price,
            "direction": direction,
            "confidence": confidence,
            "probability_up": probability_up,
            "expected_price_60m": result.get("expected_price_60m"),
            "range_low_60m": result.get("range_low_60m"),
            "range_high_60m": result.get("range_high_60m"),
            "actual_price": None,
            "outcome": None,
        }
        result["log_path"] = _append_snapshot(log_record)
        return result
    except requests.Timeout:
        return {"status": "error", "error": "OpenAI analysis timed out. The bot's existing signals are unchanged."}
    except requests.RequestException:
        return {"status": "error", "error": "Could not reach OpenAI. The bot's existing signals are unchanged."}
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return {"status": "error", "error": "AI returned an unreadable response. No call was issued."}
