import time
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd
import numpy as np
import streamlit as st
from arena_core import analyze_arena
from scalp_engine import estimated_taker_fee_cents, entry_watch, review_open_position
import json
import html
import os
import base64
from pathlib import Path
import streamlit.components.v1 as components

# Resilient HTTP client for live polling. Short transient 429/5xx/network hiccups
# should not crash the Streamlit fragment or replace the whole app with an error.
_HTTP_RETRY = Retry(
    total=2, connect=2, read=2, status=2, backoff_factor=0.15,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET"]),
    raise_on_status=False,
)
HTTP = requests.Session()
HTTP.mount("https://", HTTPAdapter(max_retries=_HTTP_RETRY, pool_connections=16, pool_maxsize=32))
HTTP.headers.update({"User-Agent": "BTC-Kalshi-Live-Terminal/2.0"})

st.set_page_config(page_title="BTC × Kalshi | Live Terminal", page_icon="₿", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');
:root {color-scheme:dark}
.stApp {background:radial-gradient(ellipse at 90% -10%,rgba(130,23,35,.24),transparent 42%),linear-gradient(180deg,#08090e 0%,#0b0d14 58%,#0b0d14 100%);color:#e9f1fc;font-family:'DM Sans',sans-serif}
.block-container {padding-top:1.5rem;max-width:1420px;padding-left:1.5rem;padding-right:1.5rem;padding-bottom:3rem}
h1,h2,h3 {font-family:'Space Grotesk',sans-serif!important;letter-spacing:-.035em!important}
h3 {color:#dceaff!important}
p, label {color:#c2d0e4}
[data-testid="stMetric"] {background:linear-gradient(145deg,rgba(26,43,66,.95),rgba(15,28,46,.96));padding:18px 19px;border:1px solid #39212a;border-radius:17px;box-shadow:0 9px 25px rgba(0,0,0,.13);min-height:108px}
[data-testid="stMetricLabel"] {color:#94a9c4!important;font-size:.79rem!important;letter-spacing:.02em}
[data-testid="stMetricValue"] {font-family:'Space Grotesk',sans-serif;font-weight:700;letter-spacing:-.04em;font-size:clamp(1.25rem,2vw,1.85rem)!important}
[data-testid="stMetricDelta"] {font-weight:700}
[data-testid="stTabs"] {margin-top:1rem}
[data-testid="stTabs"] [role="tablist"] {gap:8px;border-bottom:1px solid #39212a}
[data-testid="stTabs"] button {font-weight:700;border-radius:10px 10px 0 0;padding:12px 17px;color:#9bb1cf}
[data-testid="stTabs"] button[aria-selected="true"] {color:#ff6c78!important;background:#35161e}
[data-testid="stSidebar"] {background:#100c12;border-right:1px solid #39212a}
[data-testid="stSidebar"] h2 {color:#ecf7ff}
[data-testid="stRadio"] div[role="radiogroup"] {gap:6px;flex-wrap:wrap}
[data-testid="stRadio"] label {border:1px solid #56303a;background:#1a1119;border-radius:9px;padding:4px 10px}
[data-testid="stAlert"] {border-radius:13px}
hr {border-color:#3b222b!important}
.hero {padding:22px 25px;border:1px solid #5d2835;border-radius:21px;background:linear-gradient(112deg,rgba(52,15,24,.95),rgba(20,12,20,.95) 60%,rgba(55,17,28,.8));margin-bottom:18px;box-shadow:0 12px 38px rgba(0,0,0,.13)}
.eyebrow {font-size:.72rem;letter-spacing:.16em;font-weight:800;color:#ff6575;text-transform:uppercase;margin-bottom:7px}
.hero-title {font-family:'Space Grotesk',sans-serif;font-size:clamp(1.5rem,3vw,2.4rem);font-weight:700;letter-spacing:-.05em;color:#f1f7ff;line-height:1.13}
.hero-sub {color:#a6bbd2;font-size:.87rem;margin-top:8px}
.badge {display:inline-block;border:1px solid #a93d4e;border-radius:20px;background:rgba(155,35,52,.18);color:#ff8c96;font-weight:800;font-size:.72rem;padding:6px 11px;margin-top:13px}
.section-heading {font-size:.72rem;font-weight:800;color:#8fa6c1;letter-spacing:.14em;text-transform:uppercase;margin:20px 0 11px}
@media(max-width:650px){.block-container{padding:.55rem .65rem 2rem}.hero{padding:12px 14px;border-radius:13px;margin-bottom:8px}.hero-title{font-size:1.35rem}.hero-sub{font-size:.76rem}.badge{margin-top:7px;font-size:.63rem;padding:4px 8px}[data-testid="stMetric"]{padding:9px 10px;min-height:72px;border-radius:11px}[data-testid="stMetricValue"]{font-size:1.08rem!important}[data-testid="stTabs"] button{padding:8px 7px;font-size:.75rem}.section-heading{margin:10px 0 6px}[data-testid="stVerticalBlock"]{gap:.48rem}div[data-testid="stPlotlyChart"]{margin:0!important}}

.position-panel {background:linear-gradient(125deg,#250d17,#120e16 75%);border:1px solid #783140;border-radius:16px;padding:17px 18px;margin:10px 0 15px;box-shadow:0 9px 32px rgba(0,0,0,.2)}
.position-eyebrow{font-size:.66rem;color:#e7a6b0;font-weight:800;letter-spacing:.12em}
.position-mood{font-size:clamp(1.15rem,4vw,1.75rem);font-weight:900;letter-spacing:.035em;margin:9px 0 15px}
.position-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px}
.position-grid>div{background:#140e16;border:1px solid #43242d;border-radius:9px;padding:10px;min-width:0}
.position-grid small{display:block;font-size:.6rem;color:#aa8894;letter-spacing:.07em;margin-bottom:6px}
.position-grid strong{display:block;font-size:clamp(.88rem,1.6vw,1.15rem);color:#f7e9ed;overflow-wrap:anywhere}
.position-note{font-size:.7rem;color:#ac8996;margin-top:12px}
@media(max-width:650px){.position-panel{padding:12px}.position-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.position-grid>div{padding:8px}.position-grid strong{font-size:.95rem}}
.market-strip{display:grid;grid-template-columns:1.45fr .85fr .85fr;gap:6px;margin:4px 0 6px}
.market-strip>div{background:linear-gradient(145deg,rgba(26,43,66,.96),rgba(15,28,46,.97));border:1px solid #39212a;border-radius:10px;padding:8px 10px;min-width:0}
.market-strip small{display:block;color:#91a8c3;font-size:.62rem;letter-spacing:.04em;white-space:nowrap}
.market-strip strong{display:block;color:#eff6ff;font-family:'Space Grotesk',sans-serif;font-size:1.03rem;line-height:1.1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.market-strip span{display:block;color:#9fb2c8;font-size:.61rem;margin-top:2px;white-space:nowrap}
.compact-status{border:1px solid #4c2932;background:#15111a;border-radius:9px;padding:6px 9px;margin:3px 0 6px;color:#b8c8dc;font-size:.68rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
@media(max-width:650px){
  .block-container{padding:.3rem .42rem .8rem!important}
  .hero{padding:7px 10px!important;border-radius:10px!important;margin-bottom:4px!important}
  .hero .eyebrow,.hero .hero-sub,.hero .badge{display:none!important}
  .hero-title{font-size:1.05rem!important;line-height:1.05!important}
  [data-testid="stVerticalBlock"]{gap:.26rem!important}
  [data-testid="stMetric"]{padding:5px 7px!important;min-height:52px!important;border-radius:9px!important}
  [data-testid="stMetricLabel"]{font-size:.61rem!important}
  [data-testid="stMetricValue"]{font-size:.9rem!important}
  [data-testid="stMetricDelta"]{font-size:.61rem!important}
  [data-testid="stRadio"] label{padding:2px 5px!important;border-radius:7px!important;font-size:.68rem!important}
  [data-testid="stRadio"] div[role="radiogroup"]{gap:3px!important;flex-wrap:wrap!important}
  [data-testid="stSelectbox"] label{font-size:.66rem!important;margin-bottom:0!important}
  [data-testid="stSelectbox"] div[data-baseweb="select"]>div{min-height:36px!important;height:36px!important}
  [data-testid="stExpander"] summary{min-height:34px!important;padding-top:4px!important;padding-bottom:4px!important;font-size:.72rem!important}
  .stCaptionContainer{font-size:.64rem!important}
  .section-heading{margin:5px 0 3px!important;font-size:.61rem!important}
  .market-strip{gap:4px;margin:2px 0 4px}
  .market-strip>div{padding:6px 7px;border-radius:8px}
  .market-strip small{font-size:.52rem}.market-strip strong{font-size:.86rem}.market-strip span{font-size:.52rem}
}
</style>""", unsafe_allow_html=True)
st.markdown("""<div class="hero"><div class="eyebrow">HYPER-STYLE TERMINAL · BTC × KALSHI</div><div class="hero-title">₿ &nbsp; BTC / KALSHI LIVE</div><div class="hero-sub">Live candles · 15-minute contracts · order flow · risk first</div><span class="badge">● LIVE DATA &nbsp;·&nbsp; RESEARCH ONLY</span></div>""", unsafe_allow_html=True)

COINBASE = "https://api.exchange.coinbase.com"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
HEADERS = {"User-Agent": "BTC-Kalshi-Scalp-Desk/1.0", "Accept": "application/json"}


# -----------------------------------------------------------------------------
# Adaptive outcome learning
# -----------------------------------------------------------------------------
# The live model can learn from its OWN earlier snapshots after Kalshi settles the
# corresponding market. This is deliberately a conservative calibration layer:
# it is not allowed to replace the core strike/volatility/BRTI-aware model until
# enough independent resolved markets exist and walk-forward tests show an actual
# Brier-score improvement.
LEARNING_COLUMNS = [
    "recorded_utc", "ticker", "checkpoint", "remaining_sec", "strike",
    "reference_price", "base_prob_above", "adaptive_prob_above",
    "stat_prob", "analog_prob", "market_prob", "flow_prob", "final60_prob",
    "momentum", "pressure", "bid_balance", "spread", "candle_outcome_score",
    "z_distance", "sigma_1m", "venue_count", "dispersion_bps", "disagreement",
    "outcome_call", "result", "settled_utc", "settlement_value",
]
LEARNING_LOCAL_PATH = Path(os.environ.get("KALSHI_LEARNING_PATH", "data/btc_kalshi_learning.csv"))
LEARNING_GITHUB_PATH = os.environ.get("LEARNING_GITHUB_PATH", "data/btc_kalshi_learning.csv")
LEARNING_GITHUB_REPO = os.environ.get("LEARNING_GITHUB_REPO", "angelmoz881-collab/btc-kalshi-dashboard")
LEARNING_GITHUB_BRANCH = os.environ.get("LEARNING_GITHUB_BRANCH", "learning-data")


def _secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def _learning_token():
    return _secret("LEARNING_GITHUB_TOKEN") or os.environ.get("LEARNING_GITHUB_TOKEN")


def _learning_repo():
    return _secret("LEARNING_GITHUB_REPO", LEARNING_GITHUB_REPO) or LEARNING_GITHUB_REPO


def _learning_branch():
    return _secret("LEARNING_GITHUB_BRANCH", LEARNING_GITHUB_BRANCH) or LEARNING_GITHUB_BRANCH


def _learning_path():
    return _secret("LEARNING_GITHUB_PATH", LEARNING_GITHUB_PATH) or LEARNING_GITHUB_PATH


LEARNING_TEXT_COLUMNS = (
    "recorded_utc", "ticker", "checkpoint", "outcome_call", "result", "settled_utc",
)


def _empty_learning_history():
    return pd.DataFrame({
        col: pd.Series(dtype="string" if col in LEARNING_TEXT_COLUMNS else "float64")
        for col in LEARNING_COLUMNS
    })


def _normalize_learning_history(df):
    if df is None or len(df) == 0:
        return _empty_learning_history()
    out = df.copy()
    for col in LEARNING_COLUMNS:
        if col not in out.columns:
            out[col] = np.nan if col not in ("recorded_utc", "ticker", "checkpoint", "outcome_call", "result", "settled_utc") else ""
    out = out[LEARNING_COLUMNS]
    for col in [
        "remaining_sec", "strike", "reference_price", "base_prob_above", "adaptive_prob_above",
        "stat_prob", "analog_prob", "market_prob", "flow_prob", "final60_prob", "momentum",
        "pressure", "bid_balance", "spread", "candle_outcome_score", "z_distance", "sigma_1m",
        "venue_count", "dispersion_bps", "disagreement", "settlement_value",
    ]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    # CSV readers infer all-blank text columns (especially settled_utc) as
    # float64. Restore their types before assigning ISO timestamps or labels.
    # Keep timestamps as ISO strings to match the existing CSV/API format.
    for col in LEARNING_TEXT_COLUMNS:
        out[col] = out[col].fillna("").astype("string")
    out["result"] = out["result"].str.lower()
    out = out.drop_duplicates(subset=["ticker", "checkpoint"], keep="last")
    return out.sort_values(["recorded_utc", "ticker"], na_position="last").reset_index(drop=True)


def possible_expiration_outcome(engine):
    """A tentative view of the same expiry estimate, independent of the regular call."""
    try:
        p = float(engine.get("prob_above"))
        confidence = float(engine.get("confidence", 0))
        remaining = float(engine.get("remaining_sec"))
        target = float(engine.get("target"))
    except (TypeError, ValueError):
        return "UNAVAILABLE", "Waiting for expiry inputs"
    if not all(math.isfinite(x) for x in (p, confidence, remaining, target)) or not 0 <= p <= 1:
        return "UNAVAILABLE", "Waiting for valid expiry inputs"
    if remaining <= 0:
        return "EXPIRED", "Waiting for official settlement"
    if .45 < p < .55:
        return "NO CLEAR LEAN", "Evidence too weak or close to 50/50"
    direction = "ABOVE" if p > .5 else "BELOW"
    probability = p if p > .5 else 1 - p
    return f"POSSIBLE {direction}", f"Uncalibrated estimate {probability:.0%} · evidence {confidence:.0f}/100 · tentative"


def expiration_trade_review(prob, snapshot, remaining_sec, proxy, disagreement, min_edge):
    """One-contract, hold-to-settlement paper EV; never a live/scalp approval.

    Fee allowance is deliberately configurable, not a verified series fee.
    Ask already includes the entry spread; do not subtract spread twice.
    """
    out = {"summary": "NO TRADE · RESEARCH ONLY", "reason": "No separately validated scalp model; expiry probability is uncalibrated", "side": None, "net_edge_pp": None}
    try:
        p = float(prob)
        if not math.isfinite(p) or not 0 <= p <= 1 or not snapshot:
            return out
        if remaining_sec <= 60 or remaining_sec > 900:
            out["reason"] = "Final-minute/expired contract: proxy settlement risk too high"
            return out
        if snapshot.get("market", {}).get("status") not in ("active", "open") or snapshot.get("book_error"):
            out["reason"] = "Market inactive or order book unavailable"
            return out
        if proxy.get("count", 0) < 3 or proxy.get("dispersion_bps") is None or proxy["dispersion_bps"] > 10:
            out["reason"] = "Insufficient agreement across reference venues"
            return out
        if disagreement is None or not math.isfinite(disagreement) or disagreement > .12:
            out["reason"] = "Expiration components disagree"
            return out
        candidates = []
        for side, probability, opposing in (("yes", p, "no"), ("no", 1-p, "yes")):
            ask, bid = float(snapshot[side+"_ask"]), float(snapshot[side+"_bid"])
            if not (0 < bid <= ask < 100) or ask-bid > 3:
                continue
            depth = sum(float(q) for price, q in snapshot.get(opposing, []) if abs(float(price)-(100-ask)) < .001)
            if depth < 10:
                continue
            # Conservative 3-cent entry fee allowance and 2-cent slippage.
            fee = float(os.environ.get("KALSHI_PAPER_FEE_CENTS", "3"))
            if not math.isfinite(fee) or fee < 0:
                return out
            net = probability*100-ask-fee-2
            candidates.append((net, side.upper(), ask, fee))
        if not candidates:
            out["reason"] = "Missing/crossed quotes, wide spread, or insufficient executable depth"
            return out
        net, side, ask, fee = max(candidates)
        out.update(side=side, net_edge_pp=net, ask_cents=ask, fee_cents=fee)
        threshold = max(10.0, float(min_edge))
        out["summary"] = f"NO TRADE · {side} expiry paper EV {net:+.1f}¢/contract"
        if net >= threshold:
            out["summary"] = f"PAPER ONLY · {side} expiry EV {net:+.1f}¢/contract"
            out["reason"] = "Cost-adjusted expiry estimate clears research threshold; calibration and profitability remain unproven. Not a scalp signal."
        else:
            out["reason"] = f"Expiry paper EV below {threshold:.0f}¢ threshold after ask, fee allowance and slippage"
        return out
    except (TypeError, ValueError, KeyError):
        return out


def _github_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "BTC-Kalshi-Adaptive-Learner/1.0",
    }


def _load_learning_from_github():
    token = _learning_token()
    if not token:
        st.session_state["learning_remote_read_status"] = "GitHub token not configured"
        return None
    url = f"https://api.github.com/repos/{_learning_repo()}/contents/{_learning_path()}"
    try:
        r = HTTP.get(url, params={"ref": _learning_branch()}, headers=_github_headers(token), timeout=10)
        if r.status_code == 404:
            st.session_state["learning_remote_read_status"] = "GitHub file not created yet"
            return None
        r.raise_for_status()
        payload = r.json()
        raw = base64.b64decode(payload.get("content", "")).decode("utf-8")
        from io import StringIO
        remote = _normalize_learning_history(pd.read_csv(StringIO(raw)))
        st.session_state["learning_remote_read_status"] = f"GitHub read OK · {len(remote)} snapshots"
        return remote
    except Exception as exc:
        st.session_state["learning_remote_read_status"] = f"GitHub read failed: {type(exc).__name__}: {exc}"
        return None


def load_learning_history():
    """Load/merge local and durable GitHub feedback history.

    With a token configured, GitHub is treated as durable storage while the local
    file remains a fast cache. Merging both prevents a stale Streamlit runtime file
    from hiding newer history that was already persisted to the learning branch.
    """
    local = None
    try:
        if LEARNING_LOCAL_PATH.exists():
            local = _normalize_learning_history(pd.read_csv(LEARNING_LOCAL_PATH))
    except Exception as exc:
        st.session_state["learning_local_read_status"] = f"Local read failed: {type(exc).__name__}: {exc}"
    remote = _load_learning_from_github() if _learning_token() else None
    frames = [x for x in (local, remote) if isinstance(x, pd.DataFrame) and len(x)]
    if frames:
        merged = _normalize_learning_history(pd.concat(frames, ignore_index=True))
        try:
            LEARNING_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
            merged.to_csv(LEARNING_LOCAL_PATH, index=False)
            st.session_state["learning_local_read_status"] = f"Local cache OK · {len(merged)} snapshots"
        except Exception as exc:
            st.session_state["learning_local_read_status"] = f"Local cache write failed: {type(exc).__name__}: {exc}"
        return merged
    return _empty_learning_history()


def _push_learning_to_github(df):
    token = _learning_token()
    if not token:
        return "local only"
    url = f"https://api.github.com/repos/{_learning_repo()}/contents/{_learning_path()}"
    headers = _github_headers(token)
    sha = None
    try:
        g = HTTP.get(url, params={"ref": _learning_branch()}, headers=headers, timeout=10)
        if g.status_code == 200:
            sha = g.json().get("sha")
        elif g.status_code != 404:
            g.raise_for_status()
        payload = {
            "message": "Update BTC Kalshi adaptive learning history",
            "content": base64.b64encode(df.to_csv(index=False).encode("utf-8")).decode("ascii"),
            "branch": _learning_branch(),
        }
        if sha:
            payload["sha"] = sha
        p = requests.put(url, headers=headers, json=payload, timeout=12)
        p.raise_for_status()
        return "GitHub synced"
    except Exception as exc:
        return f"GitHub sync failed: {exc}"


def save_learning_history(df):
    df = _normalize_learning_history(df)
    status = "local only"
    try:
        LEARNING_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = LEARNING_LOCAL_PATH.with_suffix(".tmp")
        df.to_csv(tmp, index=False)
        os.replace(tmp, LEARNING_LOCAL_PATH)
    except Exception as exc:
        status = f"local save failed: {exc}"
    if _learning_token():
        status = _push_learning_to_github(df)
    st.session_state["learning_save_status"] = status
    return status


def _market_result_payload(ticker):
    """Fetch the official settled YES/NO outcome for one recorded market.

    Kalshi's current Market payload exposes settlement_value_dollars/settlement_ts
    but may omit the older ``result`` field. Binary YES contracts settle to $1 or
    $0, so infer YES/NO from that official payout when necessary. As a final
    fallback for KXBTC15M, compare the published expiration value with the strike.
    """
    try:
        r = HTTP.get(f"{KALSHI}/markets/{ticker}", headers=HEADERS, timeout=10)
        if r.status_code == 404:
            st.session_state["learning_result_status"] = f"{ticker}: market not found yet"
            return None
        r.raise_for_status()
        body = r.json()
        m = body.get("market", body)
        result = str(m.get("result") or m.get("market_result") or "").strip().lower()

        # Newer Kalshi Market objects expose the YES payout instead of a result
        # string. A settled binary market pays either $1.00 (YES) or $0.00 (NO).
        payout_raw = m.get("settlement_value_dollars")
        if payout_raw in (None, ""):
            payout_raw = m.get("yes_settlement_value_dollars")
        try:
            payout = float(payout_raw) if payout_raw not in (None, "") else np.nan
        except Exception:
            payout = np.nan
        if result not in ("yes", "no") and np.isfinite(payout):
            if payout >= 0.999:
                result = "yes"
            elif payout <= 0.001:
                result = "no"

        expiration_raw = m.get("expiration_value")
        try:
            expiration_value = float(expiration_raw) if expiration_raw not in (None, "") else np.nan
        except Exception:
            expiration_value = np.nan

        # If Kalshi has published the benchmark expiration value but not a payout,
        # infer the binary result from the contract strike. This fallback is only
        # used for this BTC-above-strike series.
        if result not in ("yes", "no") and str(ticker).startswith("KXBTC15M") and np.isfinite(expiration_value):
            strike_raw = m.get("floor_strike")
            if strike_raw in (None, ""):
                strike_raw = m.get("strike_price")
            try:
                strike = float(strike_raw) if strike_raw not in (None, "") else np.nan
            except Exception:
                strike = np.nan
            if np.isfinite(strike):
                result = "yes" if expiration_value > strike else "no"

        settled = m.get("settlement_ts") or m.get("settled_time") or m.get("settlement_time") or ""
        if result not in ("yes", "no"):
            status = str(m.get("status") or "").lower()
            st.session_state["learning_result_status"] = (
                f"{ticker}: no settled label yet · status={status or 'unknown'} · "
                f"payout={payout_raw if payout_raw not in (None,'') else 'n/a'}"
            )
            return None

        # Prefer the published BTC expiration benchmark for diagnostics; otherwise
        # retain the binary payout as the settlement value.
        value = expiration_value if np.isfinite(expiration_value) else payout
        st.session_state["learning_result_status"] = f"{ticker}: resolved {result.upper()}"
        return {"result": result, "settled_utc": str(settled), "settlement_value": value}
    except Exception as exc:
        st.session_state["learning_result_status"] = f"{ticker}: result check failed: {type(exc).__name__}: {exc}"
        return None


def refresh_learning_outcomes(df, force=False, max_markets=24):
    """Fill labels for old snapshots by checking official Kalshi market results."""
    df = _normalize_learning_history(df)
    now = time.time()
    last_check = float(st.session_state.get("learning_last_result_check", 0.0) or 0.0)
    if not force and now - last_check < 60:
        return df, 0
    st.session_state["learning_last_result_check"] = now
    unresolved = df[~df["result"].isin(["yes", "no"])]
    tickers = [x for x in unresolved["ticker"].dropna().astype(str).unique() if x and x != "none"]
    if not tickers:
        return df, 0
    updated = 0
    for ticker in tickers[:max_markets]:
        info = _market_result_payload(ticker)
        if not info:
            continue
        mask = df["ticker"].eq(ticker) & ~df["result"].isin(["yes", "no"])
        if mask.any():
            df.loc[mask, "result"] = info["result"]
            df.loc[mask, "settled_utc"] = info["settled_utc"]
            df.loc[mask, "settlement_value"] = info["settlement_value"]
            updated += int(mask.sum())
    if updated:
        save_learning_history(df)
    return _normalize_learning_history(df), updated


def _checkpoint_name(remaining_sec):
    s = float(remaining_sec)
    if s > 720: return "15-12m"
    if s > 540: return "12-9m"
    if s > 360: return "9-6m"
    if s > 180: return "6-3m"
    if s > 60: return "3-1m"
    return "final-60s"


def _prob_logit(p):
    p = float(np.clip(p, .005, .995))
    return math.log(p/(1.0-p))


ADAPTIVE_FEATURE_NAMES = [
    "base_logit", "stat_delta", "analog_delta", "market_delta", "flow_delta", "final_delta",
    "remaining_frac", "z_distance", "momentum", "pressure", "bid_balance", "candle_score",
    "spread_quality", "disagreement", "venue_quality", "dispersion_quality",
]


def _adaptive_feature_vector(row):
    def num(name, default=np.nan):
        try:
            v = float(row.get(name, default))
            return v if np.isfinite(v) else default
        except Exception:
            return default
    base = num("base_prob_above", .5)
    base = float(np.clip(base, .005, .995))
    def delta(name):
        v = num(name, np.nan)
        return float(v-base) if np.isfinite(v) else 0.0
    remaining = float(np.clip(num("remaining_sec", 450.0)/900.0, 0.0, 1.0))
    spread = num("spread", np.nan)
    spread_q = 0.4 if not np.isfinite(spread) else float(np.clip(1.0-spread/12.0, 0.0, 1.0))
    disp = num("dispersion_bps", np.nan)
    disp_q = 0.5 if not np.isfinite(disp) else float(np.clip(1.0-disp/30.0, 0.0, 1.0))
    return np.array([
        _prob_logit(base), delta("stat_prob"), delta("analog_prob"), delta("market_prob"),
        delta("flow_prob"), delta("final60_prob"), remaining,
        float(np.clip(num("z_distance", 0.0), -4, 4)),
        float(np.clip(num("momentum", 0.0), -4, 4)),
        float(np.clip(num("pressure", 0.0), -1, 1)),
        float(np.clip(num("bid_balance", 0.0), -1, 1)),
        float(np.clip(num("candle_outcome_score", 0.0)/100.0, -1, 1)),
        spread_q, float(np.clip(num("disagreement", .12), 0, .5)),
        float(np.clip(num("venue_count", 0.0)/4.0, 0, 1)), disp_q,
    ], dtype=float)


def _fit_regularized_logit(X, y, sample_weight=None, l2=3.0, iterations=650, lr=.075):
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    if X.ndim != 2 or len(y) != len(X) or len(y) < 4 or len(np.unique(y)) < 2:
        return None
    mean = np.nanmean(X, axis=0)
    std = np.nanstd(X, axis=0)
    std = np.where((~np.isfinite(std)) | (std < 1e-6), 1.0, std)
    Xn = np.nan_to_num((X-mean)/std, nan=0.0, posinf=0.0, neginf=0.0)
    Xb = np.column_stack([np.ones(len(Xn)), Xn])
    w = np.ones(len(y), dtype=float) if sample_weight is None else np.asarray(sample_weight, dtype=float)
    w = np.where(np.isfinite(w) & (w > 0), w, 1.0)
    w = w / max(np.mean(w), 1e-9)
    beta = np.zeros(Xb.shape[1], dtype=float)
    # Initialize the intercept from class balance; this speeds convergence.
    prevalence = float(np.clip(np.average(y, weights=w), .02, .98))
    beta[0] = _prob_logit(prevalence)
    for i in range(iterations):
        z = np.clip(Xb @ beta, -20, 20)
        p = 1.0/(1.0+np.exp(-z))
        grad = (Xb.T @ (w*(p-y))) / max(np.sum(w), 1.0)
        reg = np.r_[0.0, beta[1:]] * (l2/max(len(y), 1))
        step = lr / math.sqrt(1.0 + i/180.0)
        beta -= step*(grad + reg)
    return {"mean": mean, "std": std, "beta": beta}


def _predict_regularized_logit(model, X):
    if not model:
        return np.full(len(np.atleast_2d(X)), .5)
    X = np.atleast_2d(np.asarray(X, dtype=float))
    Xn = np.nan_to_num((X-model["mean"])/model["std"], nan=0.0, posinf=0.0, neginf=0.0)
    Xb = np.column_stack([np.ones(len(Xn)), Xn])
    z = np.clip(Xb @ model["beta"], -20, 20)
    return 1.0/(1.0+np.exp(-z))


def train_adaptive_learner(history):
    """Chronological expanding-window validation by market ticker.

    Multiple checkpoints from one 15-minute contract share the same label, so all
    snapshots from a ticker are kept in the same validation fold to reduce leakage.
    The learner activates only when it beats the unlearned probability on held-out
    markets and has enough independent settled markets.
    """
    hist = _normalize_learning_history(history)
    resolved = hist[hist["result"].isin(["yes", "no"]) & hist["base_prob_above"].notna()].copy()
    if resolved.empty:
        return {"active": False, "status": "COLLECTING", "resolved_rows": 0, "resolved_markets": 0,
                "base_brier": None, "learned_brier": None, "hit_rate": None, "blend_weight": 0.0, "model": None}
    groups = resolved["ticker"].astype(str).to_numpy()
    unique_groups = (resolved.assign(_time=pd.to_datetime(resolved["recorded_utc"], utc=True, errors="coerce"))
                     .groupby("ticker")["_time"].min().sort_values().index.tolist())
    n_markets = len(unique_groups)
    y = (resolved["result"].eq("yes")).astype(float).to_numpy()
    X = np.vstack([_adaptive_feature_vector(row) for _, row in resolved.iterrows()])
    base = np.clip(pd.to_numeric(resolved["base_prob_above"], errors="coerce").fillna(.5).to_numpy(dtype=float), .005, .995)
    counts = resolved.groupby("ticker")["ticker"].transform("count").to_numpy(dtype=float)
    weights = 1.0/np.maximum(counts, 1.0)
    base_brier = float(np.average((base-y)**2, weights=weights))
    if n_markets < 100 or len(np.unique(y)) < 2:
        return {"active": False, "status": f"COLLECTING {n_markets}/100 MARKETS", "resolved_rows": len(resolved),
                "resolved_markets": n_markets, "base_brier": base_brier, "learned_brier": None,
                "hit_rate": float(np.average((base>=.5)==(y>=.5), weights=weights)), "blend_weight": 0.0, "model": None}

    # Expanding chronological windows: never train on a market after the test.
    oof = np.full(len(resolved), np.nan)
    warmup = max(30, n_markets//3)
    for test_groups in np.array_split(np.array(unique_groups[warmup:]), 4):
        if len(test_groups) == 0:
            continue
        first = unique_groups.index(test_groups[0])
        train = np.isin(groups, unique_groups[:first])
        test = np.isin(groups, test_groups)
        if len(np.unique(y[train])) < 2:
            continue
        model = _fit_regularized_logit(X[train], y[train], weights[train], l2=4.0)
        if model:
            oof[test] = _predict_regularized_logit(model, X[test])
    valid = np.isfinite(oof)
    if valid.sum() < max(12, len(resolved)*.40):
        return {"active": False, "status": "WAITING FOR VALIDATION", "resolved_rows": len(resolved),
                "resolved_markets": n_markets, "base_brier": base_brier, "learned_brier": None,
                "hit_rate": None, "blend_weight": 0.0, "model": None}
    base_brier = float(np.average((base[valid]-y[valid])**2, weights=weights[valid]))
    learned_brier = float(np.average((oof[valid]-y[valid])**2, weights=weights[valid]))
    learned_hit = float(np.average((oof[valid]>=.5)==(y[valid]>=.5), weights=weights[valid]))
    relative_improvement = (base_brier-learned_brier)/max(base_brier, 1e-9)
    active = learned_brier + 0.001 < base_brier and relative_improvement > .01
    # The learned layer grows slowly with independent settled markets and proven OOF gain.
    sample_strength = float(np.clip((n_markets-100)/200.0, 0.0, 1.0))
    performance_strength = float(np.clip(relative_improvement/.12, 0.0, 1.0))
    blend = float(np.clip((.12 + .48*sample_strength)*performance_strength, 0.0, .60)) if active else 0.0
    final_model = _fit_regularized_logit(X, y, weights, l2=4.0) if active else None
    return {
        "active": bool(active), "status": "ACTIVE" if active else "VALIDATED · NO IMPROVEMENT YET",
        "resolved_rows": int(len(resolved)), "resolved_markets": int(n_markets),
        "base_brier": base_brier, "learned_brier": learned_brier,
        "hit_rate": learned_hit, "relative_improvement": float(relative_improvement),
        "blend_weight": blend, "model": final_model,
    }


def get_adaptive_learner(history):
    """Retrain only when the set of resolved labels changes, not every 2-second refresh."""
    hist = _normalize_learning_history(history)
    resolved = hist[hist["result"].isin(["yes", "no"])].copy()
    latest = ""
    if len(resolved) and "settled_utc" in resolved:
        latest = str(resolved["settled_utc"].fillna("").max())
    signature = (
        int(len(resolved)),
        int(resolved["ticker"].nunique()) if len(resolved) else 0,
        int(resolved["result"].eq("yes").sum()) if len(resolved) else 0,
        latest,
    )
    if st.session_state.get("adaptive_model_signature") == signature and "adaptive_model_cache" in st.session_state:
        return st.session_state["adaptive_model_cache"]
    model = train_adaptive_learner(hist)
    st.session_state["adaptive_model_signature"] = signature
    st.session_state["adaptive_model_cache"] = model
    return model


def apply_adaptive_learner(base_prob, feature_row, learner):
    base_prob = float(np.clip(base_prob, .005, .995))
    if not learner or not learner.get("active") or not learner.get("model"):
        return base_prob, {"active": False, "raw_prob": None, "adjustment_pp": 0.0, "blend": 0.0}
    x = _adaptive_feature_vector(feature_row)
    learned = float(_predict_regularized_logit(learner["model"], x.reshape(1,-1))[0])
    remaining = float(np.clip(float(feature_row.get("remaining_sec", 450.0))/900.0, 0.0, 1.0))
    # Near the final 60-second settlement window, direct BRTI-average evidence is
    # more trustworthy than a historical learner, so the adaptive layer fades down.
    late_scale = .35 + .65*remaining
    blend = float(learner.get("blend_weight", 0.0))*late_scale
    candidate = (1.0-blend)*base_prob + blend*learned
    n = float(learner.get("resolved_markets", 0))
    max_adjust = .06 + .10*float(np.clip(n/100.0, 0.0, 1.0))
    final = float(np.clip(candidate, base_prob-max_adjust, base_prob+max_adjust))
    final = float(np.clip(final, .005, .995))
    return final, {"active": True, "raw_prob": learned, "adjustment_pp": (final-base_prob)*100.0, "blend": blend}


def current_learning_feature_row(engine, candle_engine):
    comps = engine.get("components") or {}
    def cp(name):
        try: return float(comps.get(name, {}).get("prob"))
        except Exception: return np.nan
    stat = engine.get("stat") or {}
    proxy = engine.get("brti_proxy") or {}
    final = engine.get("final_minute") or {}
    return {
        "remaining_sec": engine.get("remaining_sec", np.nan),
        "strike": engine.get("target", np.nan),
        "reference_price": engine.get("reference_price", np.nan),
        "base_prob_above": engine.get("base_prob_above", engine.get("prob_above", np.nan)),
        "adaptive_prob_above": engine.get("prob_above", np.nan),
        "stat_prob": cp("statistical"), "analog_prob": cp("historical_analogs"),
        "market_prob": cp("kalshi_market"), "flow_prob": cp("flow_candles"),
        "final60_prob": cp("final_60s_avg") if "final_60s_avg" in comps else final.get("prob", np.nan),
        "momentum": engine.get("momentum", np.nan), "pressure": engine.get("pressure", np.nan),
        "bid_balance": engine.get("bid_balance", np.nan), "spread": engine.get("spread", np.nan),
        "candle_outcome_score": candle_engine.get("outcome_score", np.nan),
        "z_distance": stat.get("z_distance", np.nan), "sigma_1m": stat.get("sigma_1m", np.nan),
        "venue_count": proxy.get("count", np.nan), "dispersion_bps": proxy.get("dispersion_bps", np.nan),
        "disagreement": engine.get("disagreement", np.nan),
    }


def record_learning_snapshot(history, ticker, engine, candle_engine):
    if not ticker or ticker == "none" or engine.get("target") is None or engine.get("base_prob_above") is None:
        return _normalize_learning_history(history), False
    df = _normalize_learning_history(history)
    checkpoint = _checkpoint_name(engine.get("remaining_sec", 900.0))
    exists = ((df["ticker"] == str(ticker)) & (df["checkpoint"] == checkpoint)).any()
    if exists:
        return df, False
    row = current_learning_feature_row(engine, candle_engine)
    row.update({
        "recorded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ticker": str(ticker), "checkpoint": checkpoint,
        "outcome_call": str(engine.get("outcome", "UNCERTAIN")),
        "result": "", "settled_utc": "", "settlement_value": np.nan,
    })
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df = _normalize_learning_history(df).tail(2500).reset_index(drop=True)
    save_learning_history(df)
    return df, True

@st.cache_data(ttl=2, show_spinner=False)
def get_candles(granularity=60):
    """Get distinct UTC one-minute BTC candles; retry a bounded historical window."""
    def normalize(rows):
        df = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"])
        if df.empty:
            return df
        for col in ("time", "low", "high", "open", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["time", "low", "high", "open", "close"])
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        return df.drop_duplicates("time").sort_values("time").reset_index(drop=True)

    # Coinbase Exchange candles supports at most 300 buckets per request.
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = end - pd.Timedelta(minutes=299)
    params = {"granularity": granularity, "start": start.isoformat(), "end": end.isoformat()}
    response = HTTP.get(f"{COINBASE}/products/BTC-USD/candles",
                            params=params, headers=HEADERS, timeout=15)
    response.raise_for_status()
    df = normalize(response.json())
    if len(df) >= 30:
        return df

    # If the primary endpoint provides insufficient history, try Coinbase's
    # alternate public Advanced Trade candles feed before showing an error.
    # Kraken provides public BTC/USD minute OHLC history without credentials.
    kr = HTTP.get("https://api.kraken.com/0/public/OHLC",
                      params={"pair": "XBTUSD", "interval": 1}, timeout=15)
    kr.raise_for_status()
    body = kr.json()
    if body.get("error"):
        raise ValueError(f"Kraken candle API: {body['error']}")
    pairs = [v for k, v in body.get("result", {}).items() if k != "last"]
    if not pairs:
        raise ValueError("Both candle feeds returned insufficient historical data")
    # Kraken rows: [time, open, high, low, close, vwap, volume, count]
    fallback = [[row[0], row[3], row[2], row[1], row[4], row[6]] for row in pairs[0]]
    df = normalize(fallback)
    if len(df) < 30:
        raise ValueError(f"Candle feeds returned only {len(df)} distinct minutes")
    return df.tail(300).reset_index(drop=True)


@st.cache_data(ttl=1, show_spinner=False)
def get_spot_price():
    """Near-real-time BTC spot used to update the current candle between candle snapshots."""
    r = HTTP.get(f"{COINBASE}/products/BTC-USD/ticker", headers=HEADERS, timeout=6)
    r.raise_for_status()
    return float(r.json()["price"])


def _fetch_reference_venue(name):
    """Public spot quotes from BRTI constituent exchanges.

    This is only a proxy for CME CF BRTI. Kalshi settles KXBTC15M against the
    official BRTI, which is licensed benchmark data and is not reproduced here.
    """
    try:
        if name == "Coinbase":
            r = HTTP.get(f"{COINBASE}/products/BTC-USD/ticker", headers=HEADERS, timeout=4)
            r.raise_for_status()
            return name, float(r.json()["price"])
        if name == "Kraken":
            r = HTTP.get("https://api.kraken.com/0/public/Ticker", params={"pair":"XBTUSD"}, timeout=4)
            r.raise_for_status()
            body = r.json()
            if body.get("error"):
                return name, None
            result = body.get("result") or {}
            row = next(iter(result.values()), None)
            return name, float(row["c"][0]) if row else None
        if name == "Bitstamp":
            r = HTTP.get("https://www.bitstamp.net/api/v2/ticker/btcusd/", timeout=4)
            r.raise_for_status()
            return name, float(r.json()["last"])
        if name == "Gemini":
            r = HTTP.get("https://api.gemini.com/v1/pubticker/btcusd", timeout=4)
            r.raise_for_status()
            return name, float(r.json()["last"])
    except Exception:
        return name, None
    return name, None


@st.cache_data(ttl=2, show_spinner=False)
def get_brti_proxy():
    """Robust multi-exchange proxy for the BRTI settlement reference.

    Uses public prices from several current CME CF BRTI constituent exchanges.
    The median reduces single-exchange basis noise. It is *not* the official BRTI.
    """
    venues = ("Coinbase", "Kraken", "Bitstamp", "Gemini")
    prices = {}
    with ThreadPoolExecutor(max_workers=len(venues)) as pool:
        futures = [pool.submit(_fetch_reference_venue, v) for v in venues]
        for fut in as_completed(futures):
            try:
                name, value = fut.result()
                if value is not None and np.isfinite(value) and value > 1000:
                    prices[name] = float(value)
            except Exception:
                pass
    if not prices:
        return {"price": None, "venues": {}, "count": 0, "dispersion_bps": None}
    vals = np.array(list(prices.values()), dtype=float)
    med = float(np.median(vals))
    # Drop a venue only if it is wildly detached (>1%) from the cross-venue median.
    keep = {k:v for k,v in prices.items() if abs(v/med - 1.0) <= 0.01}
    if keep:
        vals = np.array(list(keep.values()), dtype=float)
        med = float(np.median(vals))
        prices = keep
    dispersion_bps = float(np.max(np.abs(vals/med - 1.0))*10000) if len(vals) else None
    return {"price": med, "venues": prices, "count": len(prices), "dispersion_bps": dispersion_bps}


def _normalize_history_rows(rows):
    df = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"])
    if df.empty:
        return df
    for col in ("time", "low", "high", "open", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["time", "low", "high", "open", "close"])
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.drop_duplicates("time").sort_values("time").reset_index(drop=True)


@st.cache_data(ttl=90, show_spinner=False)
def get_outcome_history(hours=24):
    """Fetch enough 1-minute history for empirical forward-return analogs.

    Coinbase caps candle requests at 300 buckets. Chunks are fetched in parallel
    and cached so the 2-3 second live UI does not repeatedly pay the history cost.
    """
    hours = int(np.clip(hours, 6, 48))
    target_minutes = hours * 60
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    intervals = []
    remaining = target_minutes
    cursor_end = end
    while remaining > 0 and len(intervals) < 12:
        size = min(290, remaining)
        start = cursor_end - pd.Timedelta(minutes=size)
        intervals.append((start, cursor_end))
        remaining -= size
        cursor_end = start - pd.Timedelta(minutes=1)

    def fetch_interval(pair):
        start, stop = pair
        params = {"granularity": 60, "start": start.isoformat(), "end": stop.isoformat()}
        try:
            r = HTTP.get(f"{COINBASE}/products/BTC-USD/candles", params=params, headers=HEADERS, timeout=10)
            r.raise_for_status()
            return _normalize_history_rows(r.json())
        except Exception:
            return pd.DataFrame()

    chunks = []
    with ThreadPoolExecutor(max_workers=min(6, len(intervals) or 1)) as pool:
        for part in pool.map(fetch_interval, intervals):
            if part is not None and not part.empty:
                chunks.append(part)
    if not chunks:
        return pd.DataFrame(columns=["time","low","high","open","close","volume"])
    out = pd.concat(chunks, ignore_index=True)
    out = out.drop_duplicates("time").sort_values("time").tail(target_minutes+5).reset_index(drop=True)
    return out


def _normal_cdf(x):
    try:
        return 0.5 * (1.0 + math.erf(float(x) / math.sqrt(2.0)))
    except Exception:
        return 0.5


def _logistic(x):
    x = float(np.clip(x, -12, 12))
    return 1.0 / (1.0 + math.exp(-x))


def _weighted_quantile(values, weights, q):
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    mask = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not mask.any():
        return np.nan
    values, weights = values[mask], weights[mask]
    order = np.argsort(values)
    values, weights = values[order], weights[order]
    c = np.cumsum(weights) / np.sum(weights)
    return float(np.interp(float(q), c, values))


def empirical_analog_probability(history, current_price, strike, remaining_min):
    """Nearest-regime empirical probability of finishing above the strike.

    We compare the current 5m/15m momentum, realized volatility and EMA gap with
    prior minutes, then inspect what BTC did over the same remaining horizon.
    This is intentionally non-parametric and returns its effective sample size.
    """
    if history is None or len(history) < 240 or strike is None or current_price <= 0:
        return None
    df = history.copy().sort_values("time").drop_duplicates("time")
    c = pd.to_numeric(df["close"], errors="coerce")
    if c.notna().sum() < 240:
        return None
    # Patch the latest close toward the current multi-venue proxy while keeping the
    # historical return structure from Coinbase.
    c = c.copy()
    c.iloc[-1] = float(current_price)
    r1 = c.pct_change()
    feat = pd.DataFrame(index=df.index)
    feat["r5"] = c.pct_change(5)
    feat["r15"] = c.pct_change(15)
    feat["vol15"] = r1.rolling(15).std()
    feat["vol45"] = r1.rolling(45).std()
    ema5 = c.ewm(span=5, adjust=False).mean()
    ema15 = c.ewm(span=15, adjust=False).mean()
    feat["ema_gap"] = ema5 / ema15 - 1.0

    horizon = int(np.clip(round(float(remaining_min)), 1, 15))
    future_ret = c.shift(-horizon) / c - 1.0
    candidates = feat.iloc[:-horizon].copy()
    candidates["future_ret"] = future_ret.iloc[:-horizon]
    candidates = candidates.dropna()
    current = feat.iloc[-1]
    if candidates.empty or current.isna().any():
        return None
    feature_cols = ["r5","r15","vol15","vol45","ema_gap"]
    X = candidates[feature_cols].astype(float)
    cur = current[feature_cols].astype(float)
    med = X.median()
    scale = (X.quantile(.75) - X.quantile(.25)).replace(0, np.nan) / 1.349
    scale = scale.fillna(X.std().replace(0, np.nan)).fillna(1e-6).clip(lower=1e-6)
    # Momentum features matter a little more than the slow volatility regime.
    feature_w = pd.Series({"r5":1.35,"r15":1.15,"vol15":.9,"vol45":.7,"ema_gap":1.0})
    z = ((X - cur) / scale) ** 2
    dist = np.sqrt((z * feature_w).sum(axis=1))
    k = int(np.clip(len(candidates) * 0.16, 80, 220))
    nearest = dist.nsmallest(min(k, len(dist))).index
    d = dist.loc[nearest].to_numpy(dtype=float)
    y = candidates.loc[nearest, "future_ret"].to_numpy(dtype=float)
    # Smooth weights stop the single closest match from dominating.
    base = max(float(np.nanmedian(d)), 0.35)
    w = np.exp(-0.5 * (d / base) ** 2)
    required = float(strike/current_price - 1.0)
    hits = (y >= required).astype(float)
    if np.sum(w) <= 0:
        return None
    p = float(np.sum(w * hits) / np.sum(w))
    eff_n = float((np.sum(w) ** 2) / max(np.sum(w*w), 1e-9))
    se = float(math.sqrt(max(p*(1-p), .0001) / max(eff_n, 1.0)))
    return {
        "prob": float(np.clip(p, .01, .99)),
        "effective_n": eff_n,
        "se": se,
        "horizon_min": horizon,
        "required_return": required,
        "q10": _weighted_quantile(y, w, .10),
        "q50": _weighted_quantile(y, w, .50),
        "q90": _weighted_quantile(y, w, .90),
    }



def historical_reversal_probability(history, trend_direction, horizon_min=5):
    """Estimate short-horizon reversal frequency in historically similar BTC states.

    This is not a guaranteed probability. It looks for prior 1-minute states with
    similar momentum, EMA stretch, realized volatility and momentum deceleration,
    then measures how often price moved materially *against* the prevailing trend
    over the next few minutes.
    """
    if history is None or len(history) < 300 or trend_direction not in (-1, 1):
        return None
    df = history.copy().sort_values("time").drop_duplicates("time")
    c = pd.to_numeric(df["close"], errors="coerce")
    if c.notna().sum() < 300:
        return None
    r1 = c.pct_change()
    ema8 = c.ewm(span=8, adjust=False).mean()
    ema21 = c.ewm(span=21, adjust=False).mean()
    f = pd.DataFrame(index=df.index)
    f["r2"] = c.pct_change(2)
    f["r5"] = c.pct_change(5)
    f["r15"] = c.pct_change(15)
    f["vol15"] = r1.rolling(15).std()
    f["ema_gap"] = ema8 / ema21 - 1.0
    # Positive acceleration means the latest 2m is stronger than the preceding 3m.
    prev3 = c.shift(2) / c.shift(5) - 1.0
    f["accel"] = f["r2"] - prev3

    horizon = int(np.clip(round(float(horizon_min)), 2, 10))
    future = c.shift(-horizon) / c - 1.0
    candidates = f.iloc[:-horizon].copy()
    candidates["future_ret"] = future.iloc[:-horizon]
    candidates = candidates.dropna()
    current = f.iloc[-1]
    if candidates.empty or current.isna().any():
        return None

    # Compare only states whose prevailing 5m/15m direction matches the live trend.
    same_dir = (np.sign(candidates["r5"]) == trend_direction) & (np.sign(candidates["r15"]) == trend_direction)
    pool = candidates.loc[same_dir].copy()
    if len(pool) < 80:
        pool = candidates.copy()

    cols = ["r2", "r5", "r15", "vol15", "ema_gap", "accel"]
    X = pool[cols].astype(float)
    cur = current[cols].astype(float)
    scale = (X.quantile(.75) - X.quantile(.25)).replace(0, np.nan) / 1.349
    scale = scale.fillna(X.std().replace(0, np.nan)).fillna(1e-6).clip(lower=1e-6)
    fw = pd.Series({"r2":1.35,"r5":1.35,"r15":1.0,"vol15":.75,"ema_gap":1.15,"accel":1.3})
    dist = np.sqrt((((X-cur)/scale)**2 * fw).sum(axis=1))
    k = int(np.clip(len(pool)*.22, 70, 180))
    near = dist.nsmallest(min(k, len(dist))).index
    d = dist.loc[near].to_numpy(dtype=float)
    y = pool.loc[near, "future_ret"].to_numpy(dtype=float)
    base = max(float(np.nanmedian(d)), .35)
    w = np.exp(-0.5*(d/base)**2)
    if np.sum(w) <= 0:
        return None

    # Require more than a microscopic tick against trend. Threshold scales with
    # recent 1m volatility so high-volatility periods do not generate false reversals.
    sigma = float(max(current["vol15"], 1e-5))
    threshold = float(np.clip(.55*sigma*np.sqrt(horizon), .00025, .0025))
    reversed_move = (y <= -threshold) if trend_direction > 0 else (y >= threshold)
    p = float(np.sum(w*reversed_move.astype(float))/np.sum(w))
    eff_n = float((np.sum(w)**2)/max(np.sum(w*w), 1e-9))
    return {
        "prob": float(np.clip(p, .01, .99)),
        "effective_n": eff_n,
        "horizon_min": horizon,
        "threshold": threshold,
        "median_forward": _weighted_quantile(y, w, .50),
        "q25": _weighted_quantile(y, w, .25),
        "q75": _weighted_quantile(y, w, .75),
    }


def reversal_intelligence(frame, exchange_trades, candle_intel, outcome_history, strike=None):
    """Detect a *possible* short-horizon BTC reversal using independent evidence.

    The detector intentionally distinguishes a warning from confirmation. It combines
    prevailing trend, momentum deceleration, overextension, reversal candles, aggressive
    large-trade pressure and historical analogs. A high score means several independent
    clues agree; it is not a promise that price will reverse.
    """
    neutral = {
        "status":"NO CLEAR REVERSAL", "direction":"NONE", "score":0.0,
        "confidence":"LOW", "historical_prob":None, "historical":None,
        "whale_pressure":None, "large_buy_usd":0.0, "large_sell_usd":0.0,
        "reasons":[], "confirmations":0, "trend":"MIXED",
    }
    if frame is None or len(frame) < 35:
        return neutral
    f = frame.copy().sort_values("time").drop_duplicates("time")
    c = pd.to_numeric(f["close"], errors="coerce").dropna().astype(float)
    if len(c) < 35:
        return neutral

    price = float(c.iloc[-1])
    r1 = price/float(c.iloc[-2]) - 1.0
    r2 = price/float(c.iloc[-3]) - 1.0
    r5 = price/float(c.iloc[-6]) - 1.0
    r15 = price/float(c.iloc[-16]) - 1.0
    prev3 = float(c.iloc[-3]/c.iloc[-6]-1.0)
    ema8 = float(c.ewm(span=8, adjust=False).mean().iloc[-1])
    ema21 = float(c.ewm(span=21, adjust=False).mean().iloc[-1])
    sigma1 = float(c.pct_change().tail(30).std())
    sigma1 = max(sigma1, 1e-5)

    # Require a reasonably coherent prevailing move before calling something a reversal.
    trend_direction = 0
    if r5 > 0 and r15 > 0 and ema8 >= ema21:
        trend_direction = 1
    elif r5 < 0 and r15 < 0 and ema8 <= ema21:
        trend_direction = -1
    elif abs(r5) > max(.00045, .9*sigma1*np.sqrt(5)):
        trend_direction = 1 if r5 > 0 else -1
    if trend_direction == 0:
        return {**neutral, "trend":"MIXED"}

    trend_name = "UPTREND" if trend_direction > 0 else "DOWNTREND"
    reversal_direction = "DOWN" if trend_direction > 0 else "UP"
    score = 0.0
    reasons = []
    confirms = 0

    def add(points, reason, confirmation=True):
        nonlocal score, confirms
        score += float(points)
        reasons.append(reason)
        if confirmation:
            confirms += 1

    # 1) Momentum deceleration / turn. Recent 1-2m moving against the prior trend is
    # more useful than simply seeing an old overbought/oversold reading.
    if trend_direction > 0:
        if r1 < 0: add(9, "latest 1m candle is pushing against the uptrend")
        if r2 < 0 and prev3 > 0: add(15, "2m momentum flipped down after prior buying")
        if r5 > 0 and r2 < -.18*abs(r5): add(8, "recent downside impulse is eroding the 5m rise")
    else:
        if r1 > 0: add(9, "latest 1m candle is pushing against the downtrend")
        if r2 > 0 and prev3 < 0: add(15, "2m momentum flipped up after prior selling")
        if r5 < 0 and r2 > .18*abs(r5): add(8, "recent upside impulse is eroding the 5m drop")

    # 2) Stretch from a slower mean. Extreme stretch alone is only a setup, so it
    # contributes less unless another trigger appears.
    stretch_z = (price/ema21 - 1.0) / max(sigma1*np.sqrt(8), 1e-5)
    if trend_direction > 0 and stretch_z >= .85:
        add(min(12, 6 + 4*(stretch_z-.85)), f"price is stretched {stretch_z:.1f}σ above EMA21", confirmation=False)
    elif trend_direction < 0 and stretch_z <= -.85:
        add(min(12, 6 + 4*(abs(stretch_z)-.85)), f"price is stretched {abs(stretch_z):.1f}σ below EMA21", confirmation=False)

    # 3) Candle engine: only opposing 1m/5m structure is treated as reversal evidence.
    tf = (candle_intel or {}).get("timeframes", {})
    one = float((tf.get(1) or {}).get("score", 0.0))
    five = float((tf.get(5) or {}).get("score", 0.0))
    opposing = -(0.58*one + 0.42*five) * trend_direction
    if opposing >= 14:
        add(float(np.clip(opposing*.34, 5, 16)), f"1m/5m candles are turning {reversal_direction.lower()}")
    # Explicit rejection/reclaim patterns deserve a separate clue.
    pattern_names = [str(p.get("name", "")) for p in (candle_intel or {}).get("patterns", [])]
    bullish_words = ("bullish", "hammer", "failed low", "lower-wick", "reclaim")
    bearish_words = ("bearish", "shooting", "failed high", "upper-wick", "breakdown")
    if reversal_direction == "UP" and any(any(w in n.lower() for w in bullish_words) for n in pattern_names):
        add(8, "bullish rejection/reversal candle pattern detected")
    if reversal_direction == "DOWN" and any(any(w in n.lower() for w in bearish_words) for n in pattern_names):
        add(8, "bearish rejection/reversal candle pattern detected")

    # 4) Aggressive large trades. Weight ≥$100k trades more heavily than the full tape.
    large_buy = large_sell = 0.0
    all_signed = all_total = 0.0
    for side, usd in exchange_trades or []:
        try:
            usd = float(usd)
            s = 1.0 if side == "buy" else -1.0
            all_signed += s*usd; all_total += usd
            if usd >= 100000:
                if side == "buy": large_buy += usd
                else: large_sell += usd
        except Exception:
            pass
    whale_total = large_buy + large_sell
    if whale_total > 0:
        whale_pressure = (large_buy-large_sell)/whale_total
    elif all_total > 0:
        whale_pressure = all_signed/all_total
    else:
        whale_pressure = None
    if whale_pressure is not None:
        against = -trend_direction * whale_pressure
        if against >= .16:
            magnitude = min(16.0, 7.0 + 12.0*against)
            side_word = "buying" if reversal_direction == "UP" else "selling"
            add(magnitude, f"large-trade pressure shows {side_word} against the current trend")
        elif against <= -.22:
            # Whales reinforcing the prevailing trend reduce reversal risk.
            score -= min(12.0, 5.0 + 10.0*abs(against))
            reasons.append("large-trade pressure is still reinforcing the current trend")

    # 5) Historical same-regime analogs use the existing cached 24h history, so this
    # adds no extra network request to the fast live loop.
    hist = historical_reversal_probability(outcome_history, trend_direction, horizon_min=5)
    hist_p = hist.get("prob") if hist else None
    if hist and hist.get("effective_n", 0) >= 25:
        p = float(hist_p)
        if p >= .60:
            add(float(np.clip((p-.50)*42, 5, 17)), f"similar BTC states reversed {p*100:.0f}% of the time over ~5m")
        elif p <= .36:
            score -= float(np.clip((.50-p)*28, 3, 9))
            reasons.append(f"similar BTC states only reversed {p*100:.0f}% of the time")

    # 6) Strike rejection is especially useful for this product because traders often
    # react around the binary threshold, but it never creates a reversal signal alone.
    if strike is not None and np.isfinite(strike):
        dist_sigma = abs(price-float(strike))/max(price*sigma1*np.sqrt(5), 1e-6)
        strike_events = [str((tf.get(m) or {}).get("strike_event", "")) for m in (1,5)]
        if dist_sigma <= .75:
            if reversal_direction == "UP" and any(("reclaim" in x.lower() or "lower-wick" in x.lower()) for x in strike_events):
                add(9, "price rejected below/reclaimed the strike")
            elif reversal_direction == "DOWN" and any(("breakdown" in x.lower() or "upper-wick" in x.lower()) for x in strike_events):
                add(9, "price rejected above/lost the strike")

    score = float(np.clip(score, 0, 100))
    # Require multiple independent confirmations for stronger language.
    if score >= 72 and confirms >= 3:
        status = f"REVERSAL {reversal_direction} · STRONG WATCH"
        confidence = "HIGH"
    elif score >= 56 and confirms >= 2:
        status = f"POSSIBLE REVERSAL {reversal_direction}"
        confidence = "MEDIUM-HIGH"
    elif score >= 40:
        status = f"REVERSAL {reversal_direction} WATCH"
        confidence = "MEDIUM"
    else:
        status = "NO CLEAR REVERSAL"
        confidence = "LOW"

    return {
        "status":status, "direction":reversal_direction if score >= 40 else "NONE",
        "score":score, "confidence":confidence, "historical_prob":hist_p,
        "historical":hist, "whale_pressure":whale_pressure,
        "large_buy_usd":large_buy, "large_sell_usd":large_sell,
        "reasons":reasons[:5], "confirmations":confirms, "trend":trend_name,
        "stretch_z":float(stretch_z), "r1":float(r1), "r5":float(r5), "r15":float(r15),
    }

def parametric_strike_probability(history, current_price, strike, remaining_min):
    """Short-horizon log-return model using robust recent realized volatility."""
    if history is None or len(history) < 60 or strike is None or current_price <= 0:
        return None
    c = pd.to_numeric(history["close"], errors="coerce").dropna().astype(float)
    if len(c) < 60:
        return None
    c = c.copy()
    c.iloc[-1] = float(current_price)
    lr = np.log(c / c.shift(1)).dropna()
    tail30 = lr.tail(30)
    tail120 = lr.tail(min(120, len(lr)))
    sigma = float(max(tail30.std(ddof=1), .65 * tail120.std(ddof=1), 1e-6))
    # Drift is aggressively shrunk because minute-level BTC drift is noisy.
    ewma_mu = float(lr.ewm(span=20, adjust=False).mean().iloc[-1])
    mu = float(np.clip(ewma_mu * .20, -0.20*sigma, 0.20*sigma))
    # Kalshi settles on the average BRTI during the final minute. For periods
    # earlier than that, the average behaves roughly like a price observed near
    # the midpoint of that final minute rather than the exact expiry tick.
    h = max(float(remaining_min) - .50, .20)
    mean = mu * h
    sigma_h = sigma * math.sqrt(h)
    threshold = math.log(float(strike) / float(current_price))
    z = (threshold - mean) / max(sigma_h, 1e-9)
    p = 1.0 - _normal_cdf(z)
    return {
        "prob": float(np.clip(p, .005, .995)),
        "sigma_1m": sigma,
        "sigma_h": sigma_h,
        "z_distance": float(-threshold / max(sigma_h, 1e-9)),
        "expected_move_dollars": float(current_price * sigma_h),
    }


def market_implied_probability(snapshot):
    if not snapshot:
        return None
    bid, ask = snapshot.get("yes_bid"), snapshot.get("yes_ask")
    if bid is not None and ask is not None:
        mid = (float(bid) + float(ask)) / 2.0
    elif ask is not None:
        mid = float(ask)
    elif bid is not None:
        mid = float(bid)
    else:
        nbid, nask = snapshot.get("no_bid"), snapshot.get("no_ask")
        if nbid is not None and nask is not None:
            mid = 100.0 - (float(nbid)+float(nask))/2.0
        elif nask is not None:
            mid = 100.0 - float(nask)
        elif nbid is not None:
            mid = 100.0 - float(nbid)
        else:
            return None
    return float(np.clip(mid/100.0, .01, .99))


def _time_weighted_observed_average(samples, start_ts, end_ts):
    """Approximate the average proxy price over an observed sub-window."""
    pts = sorted((float(t), float(v)) for t,v in samples if np.isfinite(v))
    if not pts or end_ts <= start_ts:
        return None, 0.0
    before = [x for x in pts if x[0] <= start_ts]
    within = [x for x in pts if start_ts < x[0] <= end_ts]
    if before:
        value = before[-1][1]
    elif within:
        value = within[0][1]
    else:
        return None, 0.0
    cursor = float(start_ts)
    total = 0.0
    for ts, val in within:
        if ts > cursor:
            total += value * (ts-cursor)
            cursor = ts
        value = val
    if end_ts > cursor:
        total += value * (end_ts-cursor)
    dur = float(end_ts-start_ts)
    return (total/dur if dur > 0 else None), dur


def final_minute_probability(proxy_price, strike, expiry_ts, samples, sigma_1m):
    """Approximate Kalshi's 60-second settlement average during the final minute."""
    if proxy_price is None or strike is None or expiry_ts is None or sigma_1m is None:
        return None
    now_ts = time.time()
    window_start = float(expiry_ts) - 60.0
    if now_ts < window_start or now_ts >= float(expiry_ts):
        return None
    obs_avg, observed = _time_weighted_observed_average(samples, window_start, now_ts)
    if obs_avg is None:
        obs_avg = float(proxy_price)
        observed = max(0.0, now_ts-window_start)
    remaining = max(0.1, float(expiry_ts)-now_ts)
    # Required mean price over the unseen remainder for the full 60s average to
    # finish at/above the strike.
    required_future_avg = (60.0*float(strike) - observed*float(obs_avg)) / remaining
    # The average of a diffusion over a short interval has lower variance than the
    # terminal price. sqrt(T/3) is the Brownian-average scale.
    t_min = remaining / 60.0
    sigma_avg = float(sigma_1m) * math.sqrt(max(t_min, 1e-5) / 3.0)
    threshold = math.log(max(required_future_avg, 1e-9) / float(proxy_price))
    z = threshold / max(sigma_avg, 1e-9)
    p = 1.0 - _normal_cdf(z)
    return {
        "prob": float(np.clip(p, .001, .999)),
        "observed_sec": float(np.clip(observed, 0, 60)),
        "observed_avg": float(obs_avg),
        "required_future_avg": float(required_future_avg),
        "remaining_sec": float(remaining),
    }

@st.cache_data(ttl=1, show_spinner=False)
def get_market(ticker):
    r = HTTP.get(f"{KALSHI}/markets/{ticker}", headers=HEADERS, timeout=12)
    r.raise_for_status()
    j = r.json()
    return j.get("market", j)

@st.cache_data(ttl=1, show_spinner=False)
def get_orderbook(ticker):
    r = HTTP.get(f"{KALSHI}/markets/{ticker}/orderbook", headers=HEADERS, timeout=12)
    r.raise_for_status()
    j = r.json()
    return j.get("orderbook_fp") or j.get("orderbook") or j


@st.cache_data(ttl=5, show_spinner=False)
def discover_btc_15m_markets():
    """Fetch open KXBTC15M markets and prioritize the nearest future close."""
    found = []
    cursor = None
    now = datetime.now(timezone.utc)
    for _ in range(5):
        params = {"series_ticker": "KXBTC15M", "status": "open", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        response = HTTP.get(f"{KALSHI}/markets", params=params, headers=HEADERS, timeout=12)
        response.raise_for_status()
        payload = response.json()
        found.extend(payload.get("markets", []))
        cursor = payload.get("cursor")
        if not cursor:
            break

    def seconds_to_close(market):
        try:
            dt = datetime.fromisoformat(str(market.get("close_time", "")).replace("Z", "+00:00"))
            return (dt - now).total_seconds()
        except (ValueError, TypeError):
            return -1

    unique = {m["ticker"]: m for m in found if m.get("ticker") and seconds_to_close(m) > 0}
    return sorted(unique.values(), key=seconds_to_close)

def cents(value):
    if value is None:
        return None
    try:
        x = float(value)
        return x * 100 if x <= 1 else x
    except (ValueError, TypeError):
        return None

def quote_cents(market, side, kind):
    """Kalshi quotes: *_dollars strings or legacy integer-cent fields."""
    for key in (f"{side}_{kind}_dollars", f"{side}_{kind}"):
        value = market.get(key)
        if value is None or value == "":
            continue
        try:
            result = float(value) * (100 if key.endswith("_dollars") else 1)
            return result if 0 <= result <= 100 else None
        except (TypeError, ValueError):
            continue
    return None

def levels(book, side):
    """Parse Kalshi fixed-point orderbook_fp, dollar, and legacy bids."""
    if not isinstance(book, dict):
        return []
    # New API: orderbook_fp.yes_dollars / no_dollars, rows [price, count_fp]
    # Some responses nest orderbook_fp inside the top-level orderbook object.
    book = book.get("orderbook_fp") or book
    if book.get(f"{side}_dollars") is not None:
        rows, dollar_prices = book[f"{side}_dollars"], True
    elif book.get(side) is not None:
        rows, dollar_prices = book[side], False
    else:
        return []
    result = []
    for row in rows or []:
        if isinstance(row, dict):
            raw_price = row.get("price_dollars", row.get("price"))
            raw_qty = row.get("count_fp", row.get("quantity", row.get("count", row.get("size", 0))))
            is_dollars = dollar_prices or row.get("price_dollars") is not None
        elif isinstance(row, (list, tuple)) and len(row) >= 2:
            raw_price, raw_qty = row[:2]
            is_dollars = dollar_prices
        else:
            continue
        try:
            price = float(raw_price) * (100 if is_dollars else 1)
            qty = float(raw_qty)
            if 0 <= price <= 100 and qty > 0:
                result.append((price, qty))
        except (ValueError, TypeError):
            continue
    return sorted(result, key=lambda x: x[0], reverse=True)

def kalshi_snapshot(ticker):
    market = get_market(ticker)
    # A quote is useful even if the order-book endpoint is temporarily unavailable.
    book_error = None
    try:
        book = get_orderbook(ticker)
    except requests.RequestException as exc:
        book = {}
        book_error = str(exc)
    yes = levels(book, "yes")
    no = levels(book, "no")
    ybid = quote_cents(market, "yes", "bid")
    nbid = quote_cents(market, "no", "bid")
    if ybid is None and yes: ybid = yes[0][0]
    if nbid is None and no: nbid = no[0][0]
    yask = quote_cents(market, "yes", "ask")
    nask = quote_cents(market, "no", "ask")
    if yask is None and nbid is not None: yask = 100 - nbid
    if nask is None and ybid is not None: nask = 100 - ybid
    return dict(market=market, yes=yes, no=no, yes_bid=ybid, no_bid=nbid,
                yes_ask=yask, no_ask=nask, book_error=book_error)

def show_price(value):
    return f"{value:.1f}¢" if value is not None else "—"

def safe_float(x):
    try: return float(x)
    except (ValueError, TypeError): return np.nan


def extract_strike(snapshot):
    """Return a plausible BTC strike/threshold from a Kalshi market snapshot."""
    if not snapshot or not isinstance(snapshot, dict):
        return None
    market = snapshot.get("market") or {}
    for key in ("floor_strike", "cap_strike", "strike_price"):
        try:
            value = float(market.get(key))
            if np.isfinite(value) and 1000 < value < 1000000:
                return value
        except (TypeError, ValueError):
            pass
    return None


def resample_ohlcv(frame, minutes):
    """Build clean OHLCV bars for candle analysis without adding dependencies."""
    df = frame.copy()
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["time", "open", "high", "low", "close"])
    df = df.sort_values("time").drop_duplicates("time", keep="last")
    if minutes > 1:
        df = (df.set_index("time")
              .resample(f"{minutes}min", label="left", closed="left")
              .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
              .dropna(subset=["open", "high", "low", "close"])
              .reset_index())
    return df.reset_index(drop=True)


def analyze_candle_timeframe(frame, minutes=1, strike=None):
    """Context-aware candle reader.

    Classical candle names are treated as *features*, not standalone forecasts. The
    engine checks trend context, range/ATR, volume, market structure and strike
    interaction. Completed candles carry most of the weight; the still-forming bar is
    down-weighted so a mid-candle shape cannot masquerade as a confirmed pattern.
    """
    df = resample_ohlcv(frame, minutes)
    empty = {"score": 0.0, "closed_score": 0.0, "forming_score": 0.0,
             "bias": "NEUTRAL", "quality": "LOW", "patterns": [],
             "strike_event": "", "volume_ratio": None, "trend": "MIXED"}
    if len(df) < 8:
        return empty

    now = pd.Timestamp.now(tz="UTC")
    end_time = df["time"] + pd.to_timedelta(minutes, unit="min")
    closed = df[end_time <= now].copy()
    forming = df[end_time > now].copy()
    if closed.empty:
        closed = df.iloc[:-1].copy() if len(df) > 1 else df.copy()
    if closed.empty:
        return empty

    # Use rolling, volatility-adaptive definitions instead of fixed dollar sizes.
    o = closed["open"].astype(float)
    h = closed["high"].astype(float)
    l = closed["low"].astype(float)
    c = closed["close"].astype(float)
    v = closed["volume"].fillna(0).astype(float)
    body = c - o
    abody = body.abs()
    rng = (h - l).clip(lower=1e-9)
    upper = (h - pd.concat([o, c], axis=1).max(axis=1)).clip(lower=0)
    lower = (pd.concat([o, c], axis=1).min(axis=1) - l).clip(lower=0)
    prev_close = c.shift(1)
    tr = pd.concat([rng, (h-prev_close).abs(), (l-prev_close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=5).mean()
    body_ref = abody.shift(1).rolling(20, min_periods=5).median()
    range_ref = rng.shift(1).rolling(20, min_periods=5).median()
    vol_ref = v.shift(1).rolling(20, min_periods=5).median()
    ema5 = c.ewm(span=5, adjust=False).mean()
    ema13 = c.ewm(span=13, adjust=False).mean()

    i = len(closed) - 1
    cur = closed.iloc[i]
    eps = max(float(atr.iloc[i]) if pd.notna(atr.iloc[i]) else float(rng.iloc[i]), 1e-9)
    trend_raw = float((ema5.iloc[max(0, i-1)] - ema13.iloc[max(0, i-1)]) / eps)
    trend_unit = float(np.tanh(trend_raw * 1.8))
    trend = "UP" if trend_unit > 0.12 else "DOWN" if trend_unit < -0.12 else "MIXED"

    patterns = []
    score = 0.0
    strike_event = ""

    def add(name, pts, note=""):
        nonlocal score
        score += float(pts)
        patterns.append({"name": name, "score": float(pts), "note": note, "tf": f"{minutes}m"})

    cr = float(rng.iloc[i]); cb = float(abody.iloc[i]); cs = 1 if body.iloc[i] > 0 else -1 if body.iloc[i] < 0 else 0
    cup = float(upper.iloc[i]); clo = float(lower.iloc[i])
    close_pos = float(np.clip((c.iloc[i] - l.iloc[i]) / cr, 0, 1))
    body_ratio = float(np.clip(cb / cr, 0, 1))
    med_body = float(body_ref.iloc[i]) if pd.notna(body_ref.iloc[i]) and body_ref.iloc[i] > 0 else max(cb, cr * .35)
    med_range = float(range_ref.iloc[i]) if pd.notna(range_ref.iloc[i]) and range_ref.iloc[i] > 0 else cr

    # Continuous candle anatomy: body conviction + where the candle actually closed.
    score += cs * body_ratio * 9.0
    score += (close_pos - .5) * 8.0

    # Long body / range expansion = stronger directional information than color alone.
    if cb >= 1.25 * med_body and cr >= 1.10 * med_range:
        add("Range expansion", cs * 8, "large body and range vs recent bars")
    if body_ratio >= .78 and cup <= .12 * cr and clo <= .12 * cr and cs:
        add("Bullish marubozu" if cs > 0 else "Bearish marubozu", cs * 16, "close held near the candle extreme")

    # Doji / high-wave candles are indecision, so reduce directional conviction.
    is_doji = cb <= max(.10 * cr, .18 * med_body)
    if is_doji:
        patterns.append({"name": "Doji / indecision", "score": 0.0, "note": "small real body", "tf": f"{minutes}m"})
        score *= .78
    elif cb <= .35 * med_body and cup >= .28 * cr and clo >= .28 * cr:
        patterns.append({"name": "High-wave / indecision", "score": 0.0, "note": "long two-sided wicks", "tf": f"{minutes}m"})
        score *= .82

    # Pin bars only become meaningful with context. A hammer in an uptrend is not
    # automatically bullish; a shooting-star shape in a downtrend is not automatically bearish.
    hammer_shape = clo >= max(2.0 * max(cb, 1e-9), .48 * cr) and cup <= .20 * cr and close_pos >= .62
    star_shape = cup >= max(2.0 * max(cb, 1e-9), .48 * cr) and clo <= .20 * cr and close_pos <= .38
    if hammer_shape:
        add("Hammer / lower-wick rejection", 22 if trend_unit < -.12 else 8,
            "stronger after a decline" if trend_unit < -.12 else "shape present without ideal downtrend context")
    if star_shape:
        add("Shooting star / upper-wick rejection", -22 if trend_unit > .12 else -8,
            "stronger after an advance" if trend_unit > .12 else "shape present without ideal uptrend context")

    if i >= 1:
        po, pc, ph, pl = map(float, (o.iloc[i-1], c.iloc[i-1], h.iloc[i-1], l.iloc[i-1]))
        co, cc, ch, cl = map(float, (o.iloc[i], c.iloc[i], h.iloc[i], l.iloc[i]))
        prev_body = abs(pc-po)
        # Real-body engulfing with trend-context confirmation.
        bull_engulf = pc < po and cc > co and co <= pc and cc >= po and cb >= .60 * med_body
        bear_engulf = pc > po and cc < co and co >= pc and cc <= po and cb >= .60 * med_body
        if bull_engulf:
            add("Bullish engulfing", 24 if trend_unit < .20 else 14, "second body engulfs prior bearish body")
        if bear_engulf:
            add("Bearish engulfing", -24 if trend_unit > -.20 else -14, "second body engulfs prior bullish body")

        # Harami is useful as an alert but gets a deliberately modest weight.
        first_lo, first_hi = sorted((po, pc)); second_lo, second_hi = sorted((co, cc))
        harami = prev_body >= 1.15 * med_body and cb <= .65 * prev_body and second_lo >= first_lo and second_hi <= first_hi
        if harami:
            harami_dir = 1 if pc < po else -1
            add("Bullish harami" if harami_dir > 0 else "Bearish harami", harami_dir * 9,
                "contained second body; treated as a weak reversal feature")

        inside = ch <= ph and cl >= pl
        outside = ch > ph and cl < pl
        if inside:
            patterns.append({"name": "Inside bar compression", "score": 0.0, "note": "range contracted inside prior bar", "tf": f"{minutes}m"})
        if outside and cs:
            add("Bullish outside bar" if cs > 0 else "Bearish outside bar", cs * 11,
                "range engulfed prior bar and closed directionally")

    # 3-bar reversal/continuation structures.
    if i >= 2:
        a, b, d = closed.iloc[i-2], closed.iloc[i-1], closed.iloc[i]
        a_body = abs(float(a.close-a.open)); b_body = abs(float(b.close-b.open)); d_body = abs(float(d.close-d.open))
        a_lo, a_hi = sorted((float(a.open), float(a.close)))
        b_lo, b_hi = sorted((float(b.open), float(b.close)))
        bull_3inside = (a.close < a.open and b_lo >= a_lo and b_hi <= a_hi and
                        d.close > d.open and d.close > a.open)
        bear_3inside = (a.close > a.open and b_lo >= a_lo and b_hi <= a_hi and
                        d.close < d.open and d.close < a.open)
        if bull_3inside: add("Three inside up", 22, "harami-style reversal confirmed by third candle")
        if bear_3inside: add("Three inside down", -22, "harami-style reversal confirmed by third candle")

        greens = [x.close > x.open for x in (a, b, d)]
        reds = [x.close < x.open for x in (a, b, d)]
        if all(greens) and a.close < b.close < d.close and min(a_body,b_body,d_body) >= .45*med_body:
            add("Three advancing bullish candles", 15, "persistent closes higher")
        if all(reds) and a.close > b.close > d.close and min(a_body,b_body,d_body) >= .45*med_body:
            add("Three declining bearish candles", -15, "persistent closes lower")

    # Confirmed Hikkake: an inside bar, false breakout, then a close back through the
    # trap bar within three bars. This is especially useful for short-horizon scalping.
    if len(closed) >= 5:
        start = max(1, len(closed)-6)
        for j in range(start, len(closed)-1):
            mother = closed.iloc[j-1]; inside_bar = closed.iloc[j]
            if not (inside_bar.high <= mother.high and inside_bar.low >= mother.low):
                continue
            k = j + 1
            trap = closed.iloc[k]
            bull_setup = trap.high < inside_bar.high and trap.low < inside_bar.low
            bear_setup = trap.high > inside_bar.high and trap.low > inside_bar.low
            later = closed.iloc[k+1:min(len(closed), k+4)]
            if bull_setup and len(later) and (later["close"] > trap.high).any():
                add("Confirmed bullish Hikkake", 24, "false downside breakout was reclaimed")
                break
            if bear_setup and len(later) and (later["close"] < trap.low).any():
                add("Confirmed bearish Hikkake", -24, "false upside breakout failed")
                break

    # Market structure: higher-high/higher-low or lower-high/lower-low sequence.
    if i >= 4:
        hh = h.iloc[i-2] > h.iloc[i-3] > h.iloc[i-4]
        hl = l.iloc[i-2] > l.iloc[i-3] > l.iloc[i-4]
        lh = h.iloc[i-2] < h.iloc[i-3] < h.iloc[i-4]
        ll = l.iloc[i-2] < l.iloc[i-3] < l.iloc[i-4]
        if hh and hl: add("Higher-high / higher-low structure", 10, "short-term structure rising")
        if lh and ll: add("Lower-high / lower-low structure", -10, "short-term structure falling")

    # Breakout / rejection of recent local structure.
    if i >= 10:
        prior_high = float(h.iloc[i-10:i].max()); prior_low = float(l.iloc[i-10:i].min())
        if c.iloc[i] > prior_high and close_pos >= .68:
            add("Local high breakout", 16, "closed above the prior 10-bar high")
        elif h.iloc[i] > prior_high and c.iloc[i] < prior_high:
            add("Failed high breakout", -11, "wicked above resistance but closed back below")
        if c.iloc[i] < prior_low and close_pos <= .32:
            add("Local low breakdown", -16, "closed below the prior 10-bar low")
        elif l.iloc[i] < prior_low and c.iloc[i] > prior_low:
            add("Failed low breakdown", 11, "wicked below support but closed back above")

    # Strike interaction is directly relevant to a 15-minute binary outcome market.
    if strike is not None and np.isfinite(strike):
        co, cc, ch, cl = map(float, (o.iloc[i], c.iloc[i], h.iloc[i], l.iloc[i]))
        if cl <= strike <= ch:
            if co < strike < cc:
                strike_event = "Bullish strike reclaim"
                add(strike_event, 24, "opened below strike and closed above it")
            elif co > strike > cc:
                strike_event = "Bearish strike breakdown"
                add(strike_event, -24, "opened above strike and closed below it")
            elif co >= strike and cc >= strike and cl < strike:
                strike_event = "Lower-wick strike rejection"
                add(strike_event, 15, "traded below strike but recovered above it")
            elif co <= strike and cc <= strike and ch > strike:
                strike_event = "Upper-wick strike rejection"
                add(strike_event, -15, "traded above strike but fell back below it")
            else:
                strike_event = "Strike touched"
                patterns.append({"name": strike_event, "score": 0.0, "note": "price traded through the strike", "tf": f"{minutes}m"})
        if i >= 2:
            recent = c.iloc[i-2:i+1]
            if (recent > strike).all() and c.iloc[i-3] <= strike if i >= 3 else False:
                add("Strike acceptance above", 10, "three closes held above strike")
            if (recent < strike).all() and c.iloc[i-3] >= strike if i >= 3 else False:
                add("Strike acceptance below", -10, "three closes held below strike")

    # Volume is confirmation, not direction. Current synthetic live bars can have zero
    # volume, so only completed candles with a valid historical comparison affect weight.
    volume_ratio = None
    if pd.notna(vol_ref.iloc[i]) and vol_ref.iloc[i] > 0 and v.iloc[i] > 0:
        volume_ratio = float(v.iloc[i] / vol_ref.iloc[i])
        if volume_ratio >= 1.6:
            score *= 1.14
            patterns.append({"name": "Volume confirmation", "score": 0.0, "note": f"{volume_ratio:.1f}× median volume", "tf": f"{minutes}m"})
        elif volume_ratio < .55:
            score *= .88

    closed_score = float(np.clip(score, -100, 100))

    # Forming candle: only anatomy + strike interaction; no classical pattern claims.
    forming_score = 0.0
    if not forming.empty:
        f = forming.iloc[-1]
        fr = max(float(f.high-f.low), 1e-9)
        fb = float(f.close-f.open)
        fbr = min(abs(fb)/fr, 1.0)
        fpos = float(np.clip((f.close-f.low)/fr, 0, 1))
        forming_score = (1 if fb > 0 else -1 if fb < 0 else 0) * fbr * 16 + (fpos-.5)*8
        if strike is not None and np.isfinite(strike) and f.low <= strike <= f.high:
            if f.open < strike < f.close: forming_score += 10
            elif f.open > strike > f.close: forming_score -= 10
        forming_score = float(np.clip(forming_score, -40, 40))

    # Different use cases weight the still-forming candle differently downstream.
    combined = float(np.clip(.78*closed_score + .22*forming_score, -100, 100))
    bias = "BULLISH" if combined >= 12 else "BEARISH" if combined <= -12 else "NEUTRAL"
    directional_patterns = [p for p in patterns if abs(p.get("score", 0)) >= 8]
    quality = "HIGH" if abs(combined) >= 38 and len(directional_patterns) >= 2 else "MEDIUM" if abs(combined) >= 20 else "LOW"
    return {"score": combined, "closed_score": closed_score, "forming_score": forming_score,
            "bias": bias, "quality": quality, "patterns": patterns[-10:],
            "strike_event": strike_event, "volume_ratio": volume_ratio, "trend": trend}


def multi_timeframe_candle_intelligence(frame, strike=None):
    """Blend 1m/5m/15m candle context for scalp and expiry decisions."""
    results = {m: analyze_candle_timeframe(frame, m, strike) for m in (1, 5, 15)}
    scalp_weights = {1: .50, 5: .35, 15: .15}
    outcome_weights = {1: .25, 5: .35, 15: .40}
    scalp_score = sum(results[m]["score"] * scalp_weights[m] for m in results)
    outcome_score = sum(results[m]["score"] * outcome_weights[m] for m in results)
    signs = [np.sign(results[m]["score"]) for m in results if abs(results[m]["score"]) >= 12]
    agreement = float(abs(sum(signs)) / len(signs)) if signs else 0.0
    bias = "BULLISH" if scalp_score >= 12 else "BEARISH" if scalp_score <= -12 else "NEUTRAL"
    quality = "HIGH" if abs(scalp_score) >= 35 and agreement >= .66 else "MEDIUM" if abs(scalp_score) >= 18 else "LOW"
    pats = []
    for m in (1,5,15):
        pats.extend(results[m]["patterns"])
    pats = sorted(pats, key=lambda p: abs(p.get("score", 0)), reverse=True)
    return {"bias": bias, "quality": quality,
            "scalp_score": float(np.clip(scalp_score, -100, 100)),
            "outcome_score": float(np.clip(outcome_score, -100, 100)),
            "agreement": agreement, "timeframes": results, "patterns": pats[:8]}


def _rsi(series, period=14):
    c = pd.to_numeric(series, errors="coerce").astype(float)
    d = c.diff()
    gain = d.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50.0)


def _candle_forecast_analogs(history, horizon=15):
    """Find similar historical candle/momentum regimes and inspect the next 15m return.

    This model intentionally uses BTC OHLCV only. No Kalshi price, order book, whale
    trades, blockchain flow or settlement target is allowed into these features.
    """
    if history is None or len(history) < 300:
        return None
    df = history.copy().sort_values("time").drop_duplicates("time", keep="last")
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    if len(df) < 300:
        return None

    c = df["close"].astype(float)
    o = df["open"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    v = df["volume"].fillna(0).astype(float)
    r1 = c.pct_change()
    rng = (h-l).clip(lower=1e-9)
    body = (c-o) / rng
    upper = (h-pd.concat([o,c],axis=1).max(axis=1))/rng
    lower = (pd.concat([o,c],axis=1).min(axis=1)-l)/rng
    ema5 = c.ewm(span=5, adjust=False).mean()
    ema15 = c.ewm(span=15, adjust=False).mean()
    ema30 = c.ewm(span=30, adjust=False).mean()
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    signal = macd.ewm(span=9, adjust=False).mean()
    rsi = _rsi(c)
    vol_med = v.rolling(30, min_periods=10).median().replace(0, np.nan)

    feat = pd.DataFrame(index=df.index)
    feat["r3"] = c.pct_change(3)
    feat["r5"] = c.pct_change(5)
    feat["r15"] = c.pct_change(15)
    feat["vol15"] = r1.rolling(15).std()
    feat["vol45"] = r1.rolling(45).std()
    feat["ema_gap"] = ema5/ema15 - 1
    feat["ema_slope"] = ema15.pct_change(3)
    feat["macd_gap"] = (macd-signal) / c
    feat["rsi"] = (rsi-50)/50
    feat["body"] = body.rolling(3).mean()
    feat["upper"] = upper.rolling(3).mean()
    feat["lower"] = lower.rolling(3).mean()
    feat["vol_ratio"] = (v/vol_med).clip(0, 5)/5
    feat["trend30"] = ema15/ema30 - 1

    horizon = int(np.clip(horizon, 5, 30))
    future_ret = c.shift(-horizon)/c - 1
    pool = feat.iloc[:-horizon].copy()
    pool["future_ret"] = future_ret.iloc[:-horizon]
    pool = pool.dropna()
    current = feat.iloc[-1]
    if pool.empty or current.isna().any():
        return None

    cols = ["r3","r5","r15","vol15","vol45","ema_gap","ema_slope","macd_gap","rsi",
            "body","upper","lower","vol_ratio","trend30"]
    X = pool[cols].astype(float)
    cur = current[cols].astype(float)
    scale = ((X.quantile(.75)-X.quantile(.25))/1.349).replace(0,np.nan)
    scale = scale.fillna(X.std().replace(0,np.nan)).fillna(1e-6).clip(lower=1e-6)
    fw = pd.Series({"r3":1.35,"r5":1.45,"r15":1.25,"vol15":.75,"vol45":.55,
                    "ema_gap":1.15,"ema_slope":1.0,"macd_gap":1.05,"rsi":.75,
                    "body":.75,"upper":.45,"lower":.45,"vol_ratio":.45,"trend30":.8})
    dist = np.sqrt((((X-cur)/scale)**2 * fw).sum(axis=1))
    k = int(np.clip(len(dist)*.12, 80, 260))
    idx = dist.nsmallest(min(k,len(dist))).index
    d = dist.loc[idx].to_numpy(float)
    y = pool.loc[idx,"future_ret"].to_numpy(float)
    bandwidth = max(float(np.nanmedian(d)), .35)
    w = np.exp(-.5*(d/bandwidth)**2)
    if not np.isfinite(w).any() or w.sum() <= 0:
        return None
    p_up = float(np.sum(w*(y>0))/np.sum(w))
    eff_n = float((w.sum()**2)/max(np.sum(w*w),1e-9))
    return {
        "p_up": float(np.clip(p_up,.02,.98)),
        "effective_n": eff_n,
        "q10": _weighted_quantile(y,w,.10),
        "q25": _weighted_quantile(y,w,.25),
        "q50": _weighted_quantile(y,w,.50),
        "q75": _weighted_quantile(y,w,.75),
        "q90": _weighted_quantile(y,w,.90),
        "mean": float(np.average(y,weights=w)),
    }


def candle_only_15m_forecast(frame, history=None, candle_intel=None):
    """15-minute BTC direction/range forecast using only candles, volume and price indicators.

    Whale trades, Kalshi order flow/prices and blockchain data are deliberately excluded.
    The output is probabilistic; confidence measures evidence agreement, not certainty.
    """
    df = resample_ohlcv(frame, 1)
    if len(df) < 45:
        return {"direction":"UNCERTAIN","p_up":.5,"p_down":.5,"confidence":0.0,
                "confidence_label":"LOW","reason":"Not enough candle history","horizon_min":15}
    c = df["close"].astype(float)
    o = df["open"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    v = df["volume"].fillna(0).astype(float)
    price = float(c.iloc[-1])
    r1 = c.pct_change()
    tr = pd.concat([(h-l),(h-c.shift(1)).abs(),(l-c.shift(1)).abs()],axis=1).max(axis=1)
    atr = float(tr.tail(14).mean())
    atr_pct = atr/price if price else 0.0
    ema5 = c.ewm(span=5,adjust=False).mean()
    ema15 = c.ewm(span=15,adjust=False).mean()
    ema30 = c.ewm(span=30,adjust=False).mean()
    macd = c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean()
    macd_sig = macd.ewm(span=9,adjust=False).mean()
    rsi = _rsi(c)

    # Feature score: each piece is bounded so no single indicator can dominate.
    score = 0.0
    reasons = []
    r5 = float(c.iloc[-1]/c.iloc[-6]-1) if len(c)>=6 else 0.0
    r15 = float(c.iloc[-1]/c.iloc[-16]-1) if len(c)>=16 else 0.0
    mom_scale = max(float(r1.tail(30).std())*math.sqrt(15), .0006)
    momentum_unit = float(np.tanh((.60*r5+.40*r15)/mom_scale))
    score += 1.05*momentum_unit
    if abs(momentum_unit)>.18:
        reasons.append("short-term momentum rising" if momentum_unit>0 else "short-term momentum falling")

    ema_gap = float((ema5.iloc[-1]-ema15.iloc[-1])/max(atr,1e-9))
    ema_slope = float((ema15.iloc[-1]-ema15.iloc[-4])/max(atr,1e-9))
    trend_unit = float(np.tanh(.9*ema_gap+.8*ema_slope))
    score += 1.0*trend_unit
    if abs(trend_unit)>.18:
        reasons.append("EMA structure bullish" if trend_unit>0 else "EMA structure bearish")

    macd_gap = float((macd.iloc[-1]-macd_sig.iloc[-1])/max(atr,1e-9))
    macd_slope = float(((macd-macd_sig).iloc[-1]-(macd-macd_sig).iloc[-4])/max(atr,1e-9))
    macd_unit = float(np.tanh(1.1*macd_gap+.75*macd_slope))
    score += .70*macd_unit

    rsi_now = float(rsi.iloc[-1])
    rsi_slope = float(rsi.iloc[-1]-rsi.iloc[-4])
    rsi_unit = float(np.tanh((rsi_now-50)/18 + rsi_slope/16))
    score += .60*rsi_unit
    if rsi_now >= 72 and momentum_unit>0:
        score -= .20
        reasons.append("RSI stretched; upside exhaustion risk")
    elif rsi_now <= 28 and momentum_unit<0:
        score += .20
        reasons.append("RSI stretched; downside exhaustion risk")

    # Structure from recent local ranges.
    recent = df.tail(20)
    first = recent.iloc[:10]
    second = recent.iloc[10:]
    hh = float(second["high"].max()-first["high"].max())/max(atr,1e-9)
    hl = float(second["low"].min()-first["low"].min())/max(atr,1e-9)
    structure_unit = float(np.tanh(.55*hh+.55*hl))
    score += .75*structure_unit
    if structure_unit>.2: reasons.append("higher-high / higher-low structure")
    elif structure_unit<-.2: reasons.append("lower-high / lower-low structure")

    # Volume confirmation, not a direction source on its own.
    vol_med = float(v.tail(30).median()) if float(v.tail(30).median())>0 else 0.0
    vol_ratio = float(v.tail(3).mean()/vol_med) if vol_med else 1.0
    if vol_ratio>1.15:
        score *= min(1.14,1.0+.07*(vol_ratio-1.0))
        reasons.append("recent volume confirms the move")
    elif vol_ratio<.60:
        score *= .90
        reasons.append("recent volume is weak")

    candle_score = float((candle_intel or {}).get("outcome_score",0.0))/100.0
    tf_agree = float((candle_intel or {}).get("agreement",0.0))
    score += 1.15*candle_score

    # Convert bounded evidence to a probability, then blend with historical analogs.
    heuristic_p = _logistic(1.15*score)
    analog_source = history if history is not None and len(history)>=300 else df
    analog = _candle_forecast_analogs(analog_source,15)
    if analog:
        analog_w = float(np.clip(.28 + .20*(analog["effective_n"]/150), .28, .48))
        p_up = (1-analog_w)*heuristic_p + analog_w*analog["p_up"]
    else:
        analog_w = 0.0
        p_up = heuristic_p
    p_up = float(np.clip(p_up,.05,.95))

    # Expected 15m return distribution. Prefer empirical analog quantiles; fall back to realized vol.
    sigma15 = max(float(r1.tail(45).std())*math.sqrt(15), atr_pct*math.sqrt(15/14), .0005)
    if analog and all(np.isfinite(analog[k]) for k in ("q10","q50","q90")):
        q10,q50,q90 = float(analog["q10"]),float(analog["q50"]),float(analog["q90"])
        expected_ret = float(.60*analog["q50"]+.40*((p_up-.5)*2*sigma15*.70))
    else:
        expected_ret = float((p_up-.5)*2*sigma15*.70)
        q10,q50,q90 = expected_ret-1.28*sigma15,expected_ret,expected_ret+1.28*sigma15
    range_low = price*(1+q10)
    range_high = price*(1+q90)
    expected_price = price*(1+expected_ret)

    # Invalidation = nearby opposing swing plus ATR buffer.
    swing_low = float(l.tail(12).min())
    swing_high = float(h.tail(12).max())
    invalidation = max(swing_low, price-1.35*atr) if p_up>=.5 else min(swing_high, price+1.35*atr)

    # Reversal risk from exhaustion + wick rejection + indicator disagreement.
    last5 = df.tail(5)
    rng = (last5["high"]-last5["low"]).clip(lower=1e-9)
    upper = (last5["high"]-pd.concat([last5["open"],last5["close"]],axis=1).max(axis=1))/rng
    lower = (pd.concat([last5["open"],last5["close"]],axis=1).min(axis=1)-last5["low"])/rng
    opp_wick = float(upper.tail(3).mean()) if p_up>=.5 else float(lower.tail(3).mean())
    component_signs = [np.sign(x) for x in (momentum_unit,trend_unit,macd_unit,rsi_unit,structure_unit,candle_score) if abs(x)>.12]
    agreement = abs(sum(component_signs))/len(component_signs) if component_signs else 0.0
    reversal_score = 35*(1-agreement) + 35*np.clip((opp_wick-.25)/.45,0,1)
    if (p_up>=.5 and rsi_now>72) or (p_up<.5 and rsi_now<28): reversal_score += 20
    reversal_score = float(np.clip(reversal_score,0,100))
    reversal_risk = "HIGH" if reversal_score>=65 else "MODERATE" if reversal_score>=38 else "LOW"

    separation = abs(p_up-.5)*2
    sample_quality = float(np.clip((analog.get("effective_n",0) if analog else 0)/130,0,1))
    confidence = 100*(.46*separation+.24*agreement+.18*tf_agree+.12*sample_quality)
    confidence = float(np.clip(confidence,0,92))
    if reversal_risk=="HIGH": confidence=min(confidence,64.0)
    confidence_label = "HIGH" if confidence>=70 else "MEDIUM" if confidence>=50 else "LOW"
    if confidence>=58 and p_up>=.61: direction="UP"
    elif confidence>=58 and p_up<=.39: direction="DOWN"
    else: direction="UNCERTAIN"

    return {
        "direction":direction,"p_up":p_up,"p_down":1-p_up,"confidence":confidence,
        "confidence_label":confidence_label,"horizon_min":15,"price":price,
        "expected_price":float(expected_price),"expected_return":float(expected_ret),
        "range_low":float(min(range_low,range_high)),"range_high":float(max(range_low,range_high)),
        "invalidation":float(invalidation),"reversal_risk":reversal_risk,
        "reversal_score":reversal_score,"rsi":rsi_now,"atr":atr,"volume_ratio":vol_ratio,
        "heuristic_p_up":float(heuristic_p),"analog":analog,"analog_weight":analog_w,
        "agreement":float(agreement),"reasons":reasons[:5],
        "note":"Candles/volume only — excludes whales, Kalshi order flow and blockchain activity.",
    }


def hourly_price_forecast(frame, history=None, hours=6):
    """Forecast BTC price at each upcoming hourly horizon from candle/history analogs.

    This is deliberately price-action only. Kalshi quotes, whale-flow and blockchain
    activity are excluded because they are tied to much shorter-lived market states.
    The output is a center estimate plus a wide empirical range, not an exact-price call.
    """
    hours = int(np.clip(hours, 1, 6))
    live = resample_ohlcv(frame, 1)
    hist = resample_ohlcv(history, 1) if isinstance(history, pd.DataFrame) and len(history) else pd.DataFrame()
    if len(hist):
        df = pd.concat([hist, live], ignore_index=True)
        df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
        df = df.dropna(subset=["time", "open", "high", "low", "close"])
        df = df.sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)
    else:
        df = live.copy()
    if len(df) < 720:
        return {"price": float(live["close"].iloc[-1]) if len(live) else None,
                "rows": [], "reason": "Not enough one-minute history for hourly analogs"}

    c = pd.to_numeric(df["close"], errors="coerce").astype(float)
    h = pd.to_numeric(df["high"], errors="coerce").astype(float)
    l = pd.to_numeric(df["low"], errors="coerce").astype(float)
    v = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0).astype(float)
    price = float(live["close"].iloc[-1]) if len(live) else float(c.iloc[-1])
    # Keep the history's final close synchronized with the current live spot.
    c = c.copy()
    c.iloc[-1] = price
    r1 = c.pct_change()
    ema15 = c.ewm(span=15, adjust=False).mean()
    ema60 = c.ewm(span=60, adjust=False).mean()
    ema180 = c.ewm(span=180, adjust=False).mean()
    rsi = _rsi(c)
    tr = pd.concat([(h-l), (h-c.shift(1)).abs(), (l-c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(30, min_periods=15).mean()
    vol_med = v.rolling(120, min_periods=30).median().replace(0, np.nan)

    feat = pd.DataFrame(index=df.index)
    feat["r5"] = c.pct_change(5)
    feat["r15"] = c.pct_change(15)
    feat["r60"] = c.pct_change(60)
    feat["r180"] = c.pct_change(180)
    feat["ema15_gap"] = c/ema15 - 1
    feat["ema60_gap"] = c/ema60 - 1
    feat["ema180_gap"] = c/ema180 - 1
    feat["ema60_slope"] = ema60.pct_change(15)
    feat["vol30"] = r1.rolling(30).std()
    feat["vol120"] = r1.rolling(120).std()
    feat["rsi"] = (rsi-50)/50
    feat["atr_pct"] = atr/c
    feat["vol_ratio"] = (v/vol_med).clip(0, 5)/5

    cols = ["r5","r15","r60","r180","ema15_gap","ema60_gap","ema180_gap",
            "ema60_slope","vol30","vol120","rsi","atr_pct","vol_ratio"]
    cur = feat.iloc[-1][cols].astype(float)
    if cur.isna().any():
        return {"price": price, "rows": [], "reason": "Hourly feature set is still warming up"}

    feature_weights = pd.Series({
        "r5": .65, "r15": 1.00, "r60": 1.45, "r180": 1.10,
        "ema15_gap": .80, "ema60_gap": 1.15, "ema180_gap": .85,
        "ema60_slope": .95, "vol30": .70, "vol120": .75, "rsi": .55,
        "atr_pct": .70, "vol_ratio": .35,
    })
    recent_sigma_1m = max(float(r1.tail(180).std()), 1e-5)
    r15_now = float(c.iloc[-1]/c.iloc[-16]-1) if len(c) >= 16 else 0.0
    r60_now = float(c.iloc[-1]/c.iloc[-61]-1) if len(c) >= 61 else 0.0
    r180_now = float(c.iloc[-1]/c.iloc[-181]-1) if len(c) >= 181 else r60_now
    one_hour_trend = .58*r60_now + .27*(r180_now/3.0) + .15*(r15_now*4.0)

    rows = []
    now_utc = pd.Timestamp.now(tz="UTC")
    for hour in range(1, hours+1):
        horizon = hour*60
        future_ret = c.shift(-horizon)/c - 1
        pool = feat[cols].copy()
        pool["future_ret"] = future_ret
        pool = pool.dropna()
        # Thin neighboring one-minute observations so a single old regime does not
        # masquerade as hundreds of independent examples.
        pool = pool.iloc[::3].copy()
        if len(pool) < 80:
            continue

        X = pool[cols].astype(float)
        scale = ((X.quantile(.75)-X.quantile(.25))/1.349).replace(0, np.nan)
        scale = scale.fillna(X.std().replace(0, np.nan)).fillna(1e-6).clip(lower=1e-6)
        dist = np.sqrt((((X-cur)/scale)**2 * feature_weights).sum(axis=1))
        k = int(np.clip(len(dist)*.22, 55, 180))
        idx = dist.nsmallest(min(k, len(dist))).index
        d = dist.loc[idx].to_numpy(float)
        y = pool.loc[idx, "future_ret"].to_numpy(float)
        bandwidth = max(float(np.nanmedian(d)), .40)
        w = np.exp(-.5*(d/bandwidth)**2)
        if not np.isfinite(w).any() or float(np.sum(w)) <= 0:
            continue

        p_analog = float(np.sum(w*(y > 0))/np.sum(w))
        eff_n = float((w.sum()**2)/max(np.sum(w*w), 1e-9))
        q10 = float(_weighted_quantile(y, w, .10))
        q50 = float(_weighted_quantile(y, w, .50))
        q90 = float(_weighted_quantile(y, w, .90))
        sigma_h = max(recent_sigma_1m*math.sqrt(horizon), .0009*math.sqrt(hour))

        # Momentum is intentionally damped with sqrt(time); linear extrapolation of a
        # 15- or 60-minute move becomes unrealistic very quickly in BTC.
        trend_projection = float(np.clip(one_hour_trend*math.sqrt(hour), -1.35*sigma_h, 1.35*sigma_h))
        expected_ret = float(.74*q50 + .26*trend_projection)
        heuristic_p = _logistic(1.15*trend_projection/max(sigma_h, 1e-6))
        p_up = float(np.clip(.76*p_analog + .24*heuristic_p, .05, .95))

        normal_low = expected_ret - 1.28*sigma_h
        normal_high = expected_ret + 1.28*sigma_h
        low_ret = float(.72*q10 + .28*normal_low)
        high_ret = float(.72*q90 + .28*normal_high)
        if low_ret > high_ret:
            low_ret, high_ret = high_ret, low_ret
        # Never allow the displayed center estimate to sit outside its own range.
        low_ret = min(low_ret, expected_ret)
        high_ret = max(high_ret, expected_ret)

        spread = max(high_ret-low_ret, 1e-6)
        sample_quality = float(np.clip(eff_n/85.0, 0, 1))
        directional_strength = float(abs(p_up-.5)*2)
        range_quality = float(np.clip((3.2*sigma_h)/spread, 0, 1))
        horizon_decay = float(max(.62, 1.0-.065*(hour-1)))
        confidence = 100*(.58*directional_strength + .20*sample_quality + .22*range_quality)*horizon_decay
        confidence = float(np.clip(confidence, 15, 74))

        if p_up >= .58 and expected_ret > 0:
            direction = "UP"
        elif p_up <= .42 and expected_ret < 0:
            direction = "DOWN"
        else:
            direction = "UNCERTAIN"

        rows.append({
            "hour": hour,
            "target_utc": now_utc + pd.Timedelta(hours=hour),
            "direction": direction,
            "p_up": p_up,
            "confidence": confidence,
            "expected_price": float(price*(1+expected_ret)),
            "range_low": float(price*(1+low_ret)),
            "range_high": float(price*(1+high_ret)),
            "expected_return": expected_ret,
            "effective_n": eff_n,
        })

    return {
        "price": price,
        "rows": rows,
        "history_minutes": int(len(df)),
        "note": "Candle/history forecast only — excludes Kalshi, whale-flow and blockchain data.",
    }

with st.sidebar:
    st.header("Settings")
    st.caption("Automatically searches Kalshi for open BTC 15-minute markets; refreshes discovery about every 5 seconds.")
    try:
        discovered_markets = discover_btc_15m_markets()
    except Exception as e:
        discovered_markets = []
        st.warning(f"Automatic market discovery failed: {e}")
    market_options = {
        f"{m.get('title') or m.get('subtitle') or m['ticker']} · {m['ticker']}": m["ticker"]
        for m in discovered_markets if m.get("ticker")
    }
    if market_options:
        selected_label = st.selectbox("Detected open BTC 15-minute market", list(market_options.keys()), index=0)
        market_ticker = market_options[selected_label]
        st.success(f"Selected ticker: {market_ticker}")
        st.caption("The nearest-closing active contract is selected by default on every refresh. You can select another open contract if needed.")
    else:
        st.info("No matching open BTC 15-minute markets were found automatically. You can enter a ticker manually below.")
        market_ticker = ""
    manual_ticker = st.text_input(
        "Or enter ticker manually",
        placeholder="KX...-...",
        help="Optional fallback if automatic discovery does not find the market."
    ).strip().upper()
    if manual_ticker:
        market_ticker = manual_ticker
    refresh_mode = st.selectbox(
        "Live update speed",
        ["Fast · 3s", "Ultra · 2s", "Balanced · 5s", "Paused"],
        index=0,
        help="Fast mode refreshes the live dashboard without reloading the whole page. Ultra is more responsive but makes more API requests.",
    )
    live_run_every = {"Fast · 3s": 3, "Ultra · 2s": 2, "Balanced · 5s": 5, "Paused": None}[refresh_mode]
    st.caption("BTC, Kalshi quotes/order book, whale trades and signals use the selected live interval. Countdown still updates every second.")
    st.markdown("---")
    st.markdown("**Signal controls**")
    min_edge = st.slider("Minimum model edge (percentage points)", 1, 20, 5)
    outcome_conf_gate = st.slider(
        "Minimum confidence for ABOVE/BELOW call", 45, 85, 60,
        help="Higher values make the bot say UNCERTAIN more often, but only commit when more evidence agrees.",
    )
    st.markdown("**Manual scalp exit protection**")
    scalp_profit_target = st.slider("Net profit target (¢ per contract)", 2, 20, 5, key="scalp_profit_target")
    scalp_trailing_lock = st.slider("Profit giveback warning (¢)", 1, 10, 2, key="scalp_trailing_lock")
    scalp_max_loss = st.slider("Loss warning (¢ per contract)", 3, 30, 8, key="scalp_max_loss")
    scalp_max_hold = st.slider("Maximum time in trade (seconds)", 30, 600, 180, step=15, key="scalp_max_hold")
    scalp_slippage = st.slider("Extra exit slippage reserve (¢ per contract)", 0.0, 5.0, 1.0, step=.5, key="scalp_slippage")
    st.caption("Exit fees are estimates until verified. This is manual research only, not auto-sell.")
    st.caption("Signals are research estimates, not guaranteed predictions. Confirm market rules, expiry and fees.")

# Streamlit fragments update only the live dashboard region instead of reloading the
# whole page. This keeps navigation stable and makes frequent refreshes usable on mobile.
_fragment = getattr(st, "fragment", getattr(st, "experimental_fragment", None))
if _fragment is None:
    def _fragment(*, run_every=None):
        def decorate(fn):
            return fn
        return decorate

def _render_live_dashboard_inner():
    active_ticker = market_ticker
    # Keep the tracked contract selected; otherwise auto-rotation could display
    # a different contract's quotes while a position is still open.
    pinned_position = st.session_state.get("scalp_position")
    if isinstance(pinned_position, dict) and pinned_position.get("ticker"):
        active_ticker = pinned_position["ticker"]
    elif not manual_ticker:
        try:
            _live_markets = discover_btc_15m_markets()
            _open_tickers = {m.get("ticker") for m in _live_markets if m.get("ticker")}
            if active_ticker not in _open_tickers and _live_markets:
                active_ticker = _live_markets[0]["ticker"]
        except Exception:
            pass
    # Load previous prediction snapshots, automatically attach any newly settled
    # Kalshi results, then train the adaptive calibration layer. The model only
    # activates after chronological held-out validation proves it improves Brier score.
    learning_history = load_learning_history()
    learning_history, _learning_updates = refresh_learning_outcomes(learning_history, force=False)
    learning_model = get_adaptive_learner(learning_history)

    candle_feed_stale = False
    try:
        candles = get_candles(60)
        if len(candles) < 10:
            raise ValueError(f"Only {len(candles)} candles returned")
        st.session_state["_last_good_candles"] = candles.copy()
        st.session_state["_last_good_candles_ts"] = time.time()
    except Exception as e:
        fallback = st.session_state.get("_last_good_candles")
        if isinstance(fallback, pd.DataFrame) and len(fallback) >= 10:
            candles = fallback.copy()
            candle_feed_stale = True
        else:
            st.warning("BTC feed is temporarily reconnecting. The dashboard will retry automatically.")
            st.caption(f"Feed detail: {type(e).__name__}: {e}")
            return

    # Pull the ticker separately so the displayed price/current candle can move every
    # live refresh instead of waiting on the candle endpoint alone.
    spot_feed_stale = False
    try:
        _spot = get_spot_price()
        _now_minute = pd.Timestamp.now(tz="UTC").floor("min")
        _last_time = pd.Timestamp(candles.iloc[-1]["time"]).floor("min")
        candles = candles.copy()
        if _last_time == _now_minute:
            _i = candles.index[-1]
            candles.loc[_i, "close"] = _spot
            candles.loc[_i, "high"] = max(float(candles.loc[_i, "high"]), _spot)
            candles.loc[_i, "low"] = min(float(candles.loc[_i, "low"]), _spot)
        elif 0 < (_now_minute - _last_time).total_seconds() <= 120:
            _prev_close = float(candles.iloc[-1]["close"])
            _new = pd.DataFrame([{
                "time": _now_minute, "low": min(_prev_close, _spot),
                "high": max(_prev_close, _spot), "open": _prev_close,
                "close": _spot, "volume": 0.0,
            }])
            candles = pd.concat([candles, _new], ignore_index=True).tail(300).reset_index(drop=True)
    except (requests.RequestException, KeyError, ValueError, TypeError):
        spot_feed_stale = True

    last = candles.iloc[-1]
    prev = candles.iloc[-2]
    price = float(last["close"])
    ret1 = (price / float(candles.iloc[-2]["close"]) - 1) * 100
    ret5 = (price / float(candles.iloc[-6]["close"]) - 1) * 100 if len(candles) >= 6 else np.nan
    ret15 = (price / float(candles.iloc[-16]["close"]) - 1) * 100 if len(candles) >= 16 else np.nan
    returns = candles["close"].pct_change().dropna()
    vol15 = float(returns.tail(15).std() * np.sqrt(15) * 100) if len(returns) >= 15 else np.nan
    ema_fast = candles["close"].ewm(span=5, adjust=False).mean().iloc[-1]
    ema_slow = candles["close"].ewm(span=15, adjust=False).mean().iloc[-1]
    trend = "BULLISH" if ema_fast > ema_slow else "BEARISH" if ema_fast < ema_slow else "MIXED"

    st.markdown(f"""<div class="market-strip">
      <div><small>BTC / USD</small><strong>${price:,.2f}</strong><span>{ret1:+.2f}% · 1m</span></div>
      <div><small>5M MOVE</small><strong>{f'{ret5:+.2f}%' if pd.notna(ret5) else '—'}</strong><span>short-term</span></div>
      <div><small>TREND</small><strong>{trend.title()}</strong><span>EMA 5 / 15</span></div>
    </div>""", unsafe_allow_html=True)
    if candle_feed_stale:
        age = max(0, int(time.time() - float(st.session_state.get("_last_good_candles_ts", time.time()))))
        st.caption(f"⚠️ BTC candle feed reconnecting — showing last good data ({age}s old).")

    kalshi_data = None
    kalshi_error = None
    kalshi_stale = False
    if active_ticker:
        cache_key = f"_last_good_kalshi::{active_ticker}"
        cache_ts_key = f"_last_good_kalshi_ts::{active_ticker}"
        try:
            kalshi_data = kalshi_snapshot(active_ticker)
            st.session_state[cache_key] = kalshi_data
            st.session_state[cache_ts_key] = time.time()
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            fallback = st.session_state.get(cache_key)
            if isinstance(fallback, dict) and fallback:
                kalshi_data = fallback
                kalshi_stale = True
                kalshi_error = f"Live Kalshi feed reconnecting: {exc}"
            else:
                kalshi_error = str(exc)


    # Timestamp actual Kalshi bids, never reusing cached fallback quotes as new ticks.
    quote_history = []
    if active_ticker:
        histories = st.session_state.setdefault("scalp_quote_history", {})
        quote_history = histories.get(active_ticker, [])
        ts = time.time()
        quote_history = [row for row in quote_history if 0 <= ts - row.get("t", -1e9) <= 120][-120:]
        if kalshi_data and not kalshi_stale and not kalshi_data.get("book_error"):
            point = {"t": ts, "yes_bid": kalshi_data.get("yes_bid"), "no_bid": kalshi_data.get("no_bid")}
            if not quote_history or ts - quote_history[-1]["t"] >= .75:
                quote_history.append(point)
        histories[active_ticker] = quote_history

    # Dual-purpose research signals: deliberately conservative, not calibrated probabilities.
    @st.cache_data(ttl=2, show_spinner=False)
    def recent_exchange_trades():
        r = HTTP.get(f"{COINBASE}/products/BTC-USD/trades", headers=HEADERS, timeout=9)
        r.raise_for_status()
        trades = r.json()
        if not isinstance(trades, list):
            raise ValueError("Unexpected exchange trade format")
        result = []
        for t in trades:
            try:
                size = float(t["size"])
                px = float(t["price"])
                side = str(t.get("side", "")).lower()
                if size > 0 and px > 0 and side in ("buy", "sell"):
                    # Coinbase Exchange trade 'side' is the maker side; the aggressor is opposite.
                    result.append(("buy" if side == "sell" else "sell", size * px))
            except (KeyError, ValueError, TypeError):
                pass
        return result

    @st.cache_data(ttl=15, show_spinner=False)
    def blockchain_activity():
        # Unconfirmed transactions are NOT attributed to whales or exchanges.
        r = HTTP.get("https://mempool.space/api/mempool", timeout=9)
        r.raise_for_status()
        data = r.json()
        return int(data.get("count", 0)), int(data.get("vsize", 0))

    def research_signals(frame, snapshot, exchange_trades, candle_intel, outcome_history, brti_proxy, proxy_samples, adaptive_learner):
        closes = frame["close"].astype(float)
        if len(closes) < 40:
            return {"outcome": "UNCERTAIN", "scalp": "WAIT", "reason": "Insufficient BTC history", "momentum": 0.0,
                    "pressure": None, "bid_balance": None, "spread": None, "target": None,
                    "outcome_score": 0.0, "scalp_score": 0.0, "prob_above": None,
                    "prob_below": None, "confidence": 0.0, "confidence_label": "LOW",
                    "components": {}, "reference_price": float(closes.iloc[-1])}

        coinbase_p = float(closes.iloc[-1])
        proxy_p = brti_proxy.get("price") if isinstance(brti_proxy, dict) else None
        reference_price = float(proxy_p) if proxy_p is not None and np.isfinite(proxy_p) else coinbase_p
        r5 = coinbase_p / float(closes.iloc[-6]) - 1
        r15 = coinbase_p / float(closes.iloc[-16]) - 1
        vol = float(closes.pct_change().tail(60).std())
        momentum = (r5 + 0.5 * r15) / max(vol * np.sqrt(15), 0.00001)

        pressure = None
        if exchange_trades:
            total = sum(v for _, v in exchange_trades)
            pressure = sum((1 if side == "buy" else -1) * v for side, v in exchange_trades) / total if total else None

        balance, spread = None, None
        target = extract_strike(snapshot)
        remaining_min = 15.0
        remaining_sec = 0.0
        expiry_ts = None
        if snapshot:
            yes_depth = sum(q for _, q in snapshot["yes"][:5])
            no_depth = sum(q for _, q in snapshot["no"][:5])
            if yes_depth + no_depth > 0:
                balance = (yes_depth - no_depth) / (yes_depth + no_depth)
            if snapshot["yes_ask"] is not None and snapshot["yes_bid"] is not None:
                spread = snapshot["yes_ask"] - snapshot["yes_bid"]
            expiry = snapshot.get("market", {}).get("close_time") or snapshot.get("market", {}).get("expiration_time")
            if expiry:
                try:
                    expiry_dt = pd.to_datetime(expiry, utc=True)
                    expiry_ts = float(expiry_dt.timestamp())
                    remaining_sec = float(np.clip((expiry_dt - pd.Timestamp.now(tz="UTC")).total_seconds(), 0.0, 900.0))
                    remaining_min = remaining_sec / 60.0
                except Exception:
                    pass

        # Build independent estimates. The engine intentionally refuses to create a
        # strong call when the strike is missing, models disagree, or data quality is poor.
        stat = parametric_strike_probability(outcome_history if outcome_history is not None and len(outcome_history) >= 60 else frame,
                                              reference_price, target, remaining_min)
        analog = empirical_analog_probability(outcome_history, reference_price, target, remaining_min)
        market_p = market_implied_probability(snapshot)

        # Flow probability is only a small confirmation component. It cannot overpower
        # strike distance or the market-implied/statistical estimates.
        flow_signal = 0.55 * np.tanh(momentum / 1.5)
        flow_signal += 0.65 * (candle_intel.get("outcome_score", 0.0) / 100.0)
        if pressure is not None:
            flow_signal += 0.45 * pressure
        if balance is not None:
            flow_signal += 0.35 * balance
        flow_p = _logistic(1.65 * flow_signal)

        final_min = None
        if stat and expiry_ts and target is not None and proxy_samples:
            final_min = final_minute_probability(reference_price, target, expiry_ts, proxy_samples, stat.get("sigma_1m"))

        components = {}
        def add_component(name, prob, weight):
            if prob is not None and np.isfinite(prob):
                components[name] = {"prob": float(np.clip(prob, .001, .999)), "weight": float(max(weight, 0.0))}

        # Dynamic weights: distance/statistics and market consensus dominate late in
        # the contract; historical analogs matter more earlier. The special final-minute
        # average model gets the largest weight once Kalshi's 60-second settlement
        # window has started.
        urgency = float(np.clip(1.0 - remaining_min/15.0, 0.0, 1.0))
        w_stat = .25 + .13*urgency
        w_analog = .34 - .16*urgency
        w_market = .28 + .08*urgency
        w_flow = .13 - .05*urgency
        if final_min is not None:
            w_stat, w_analog, w_market, w_flow = .23, .08, .25, .04
            add_component("final_60s_avg", final_min.get("prob"), .40)
        add_component("statistical", stat.get("prob") if stat else None, w_stat)
        add_component("historical_analogs", analog.get("prob") if analog else None, w_analog)
        add_component("kalshi_market", market_p, w_market)
        add_component("flow_candles", flow_p, w_flow)

        if target is None or not components:
            prob_above = None
            confidence = 0.0
            confidence_label = "LOW"
            outcome = "UNCERTAIN"
            outcome_score = 0.0
            disagreement = None
            base_prob_above = None
            learning_adjustment = {"active": False, "raw_prob": None, "adjustment_pp": 0.0, "blend": 0.0}
        else:
            total_w = sum(v["weight"] for v in components.values())
            if total_w <= 0:
                total_w = 1.0
            for v in components.values():
                v["norm_weight"] = v["weight"] / total_w
            prob_above = sum(v["prob"]*v["norm_weight"] for v in components.values())
            probs = np.array([v["prob"] for v in components.values()], dtype=float)
            ws = np.array([v["norm_weight"] for v in components.values()], dtype=float)
            disagreement = float(math.sqrt(np.sum(ws * (probs-prob_above)**2))) if len(probs) > 1 else 0.0
            base_prob_above = float(np.clip(prob_above, .005, .995))
            # Feed only information that existed at this moment into the learner.
            # The outcome label is added later, after Kalshi settles the contract.
            _learn_features = {
                "remaining_sec": remaining_sec, "base_prob_above": base_prob_above,
                "stat_prob": stat.get("prob") if stat else np.nan,
                "analog_prob": analog.get("prob") if analog else np.nan,
                "market_prob": market_p, "flow_prob": flow_p,
                "final60_prob": final_min.get("prob") if final_min else np.nan,
                "momentum": momentum, "pressure": pressure, "bid_balance": balance, "spread": spread,
                "candle_outcome_score": candle_intel.get("outcome_score", 0.0),
                "z_distance": stat.get("z_distance", np.nan) if stat else np.nan,
                "sigma_1m": stat.get("sigma_1m", np.nan) if stat else np.nan,
                "venue_count": brti_proxy.get("count", 0) if isinstance(brti_proxy, dict) else 0,
                "dispersion_bps": brti_proxy.get("dispersion_bps", np.nan) if isinstance(brti_proxy, dict) else np.nan,
                "disagreement": disagreement,
            }
            prob_above, learning_adjustment = apply_adaptive_learner(base_prob_above, _learn_features, adaptive_learner)

            separation = float(abs(prob_above-.5)*2.0)
            agreement = float(np.clip(1.0 - disagreement/.22, 0.0, 1.0))
            z_strength = float(np.clip(abs(stat.get("z_distance", 0.0))/2.0, 0.0, 1.0)) if stat else 0.0
            analog_quality = float(np.clip((analog.get("effective_n", 0.0) if analog else 0.0)/120.0, 0.0, 1.0))
            venue_quality = float(np.clip((brti_proxy.get("count", 0) if isinstance(brti_proxy, dict) else 0)/4.0, 0.0, 1.0))
            spread_quality = 1.0 if spread is not None and spread <= 3 else .65 if spread is not None and spread <= 7 else .35
            quality = .35*venue_quality + .30*analog_quality + .20*spread_quality + .15*(1.0 if stat else 0.0)
            if final_min is not None:
                coverage = float(np.clip(final_min.get("observed_sec", 0.0)/60.0, 0.0, 1.0))
                quality = max(quality, .55 + .35*coverage)
            confidence = float(np.clip(100*(.40*separation + .27*agreement + .18*z_strength + .15*quality), 0, 100))

            # Hard caps prevent false certainty when the reference proxy is thin or
            # when the competing models strongly disagree.
            venue_count = brti_proxy.get("count", 0) if isinstance(brti_proxy, dict) else 0
            dispersion_bps = brti_proxy.get("dispersion_bps") if isinstance(brti_proxy, dict) else None
            if venue_count < 2:
                confidence = min(confidence, 55.0)
            if dispersion_bps is not None and dispersion_bps > 15:
                confidence = min(confidence, 62.0)
            if disagreement is not None and disagreement > .18:
                confidence = min(confidence, 58.0)
            if analog and analog.get("se", 0) > .07:
                confidence = min(confidence, 65.0)

            confidence_label = "VERY HIGH" if confidence >= 82 else "HIGH" if confidence >= 68 else "MEDIUM" if confidence >= 52 else "LOW"
            # Conservative call gate: better to show UNCERTAIN than manufacture certainty.
            strong_gate = confidence >= max(float(outcome_conf_gate)+10.0, 68.0) and (prob_above >= .78 or prob_above <= .22)
            normal_gate = confidence >= float(outcome_conf_gate) and (prob_above >= .66 or prob_above <= .34)
            if strong_gate:
                outcome = "ABOVE · STRONG" if prob_above > .5 else "BELOW · STRONG"
            elif normal_gate:
                outcome = "ABOVE" if prob_above > .5 else "BELOW"
            else:
                outcome = "UNCERTAIN"
            outcome_score = float(np.clip((prob_above-.5)*200.0, -100, 100))

        # Scalp model reacts faster and now includes model-vs-market edge.
        scalp_score = 28 * np.tanh(momentum / 1.25)
        scalp_score += 30 * (candle_intel.get("scalp_score", 0.0) / 100.0)
        if pressure is not None: scalp_score += 18 * pressure
        if balance is not None: scalp_score += 12 * balance
        model_edge = None
        if prob_above is not None and market_p is not None:
            model_edge = (prob_above-market_p)*100.0
            scalp_score += float(np.clip(model_edge*1.25, -20, 20))
        scalp_score = float(np.clip(scalp_score, -100, 100))

        # A separate cash-out monitor uses observed Kalshi bids and liquidity,
        # not expiry EV, after the reversal detector has run.
        scalp = "WAIT"
        trade_review = expiration_trade_review(prob_above, snapshot, remaining_sec,
                                               brti_proxy, disagreement, min_edge)
        if expiry_ts is None:
            trade_review = {"summary": "NO TRADE · expiry unavailable", "reason": "Cannot validate contract expiration"}
        reason = trade_review["reason"]

        return {
            "outcome": outcome, "scalp": scalp, "reason": reason, "momentum": momentum,
            "pressure": pressure, "bid_balance": balance, "spread": spread, "target": target,
            "outcome_score": outcome_score, "scalp_score": scalp_score,
            "prob_above": prob_above, "prob_below": (1.0-prob_above) if prob_above is not None else None,
            "confidence": confidence, "confidence_label": confidence_label,
            "components": components, "disagreement": disagreement,
            "reference_price": reference_price, "coinbase_price": coinbase_p,
            "remaining_min": remaining_min, "remaining_sec": remaining_sec,
            "analog": analog, "stat": stat, "market_prob": market_p,
            "flow_prob": flow_p, "final_minute": final_min, "model_edge": model_edge,
            "brti_proxy": brti_proxy, "base_prob_above": base_prob_above,
            "learning_adjustment": learning_adjustment, "learning_model": adaptive_learner,
            "trade_review": trade_review,
        }

    try:
        whale_trades = recent_exchange_trades()
        whale_error = None
    except (requests.RequestException, ValueError) as exc:
        whale_trades, whale_error = [], str(exc)
    try:
        chain_count, chain_vsize = blockchain_activity()
        chain_error = None
    except (requests.RequestException, ValueError, TypeError) as exc:
        chain_count, chain_vsize, chain_error = None, None, str(exc)
    # Outcome Fusion v2 uses a multi-exchange proxy aligned with Kalshi's actual
    # CME CF BRTI settlement source, plus a deeper cached history for empirical analogs.
    try:
        brti_proxy = get_brti_proxy()
    except Exception:
        brti_proxy = {"price": None, "venues": {}, "count": 0, "dispersion_bps": None}
    try:
        outcome_history = get_outcome_history(24)
    except Exception:
        outcome_history = pd.DataFrame()

    proxy_samples = []
    proxy_value = brti_proxy.get("price") if isinstance(brti_proxy, dict) else None
    if proxy_value is not None and np.isfinite(proxy_value):
        sample_key = f"brti_proxy_samples::{active_ticker or 'none'}"
        prior = list(st.session_state.get(sample_key, []))
        now_sample = time.time()
        prior.append((now_sample, float(proxy_value)))
        # Keep enough history for Kalshi's 60-second settlement averaging window.
        prior = [(t,v) for t,v in prior if now_sample-float(t) <= 90]
        st.session_state[sample_key] = prior[-80:]
        proxy_samples = prior

    target_hint = extract_strike(kalshi_data)
    candle_engine = multi_timeframe_candle_intelligence(candles, target_hint)
    candle_forecast = candle_only_15m_forecast(candles, outcome_history, candle_engine)
    hourly_forecast = hourly_price_forecast(candles, outcome_history, hours=6)
    engine = research_signals(candles, kalshi_data, whale_trades, candle_engine,
                              outcome_history, brti_proxy, proxy_samples, learning_model)
    engine["candle_only_15m"] = candle_forecast
    engine["hourly_price_forecast"] = hourly_forecast
    reversal = reversal_intelligence(candles, whale_trades, candle_engine, outcome_history, target_hint)
    engine["reversal"] = reversal
    # Evaluate independent experts against past settled markets, without placing orders.
    arena = analyze_arena(
        learning_history, engine, kalshi_data,
        min_edge_cents=max(10.0, float(min_edge)),
        candle_stale=(candle_feed_stale or spot_feed_stale), market_stale=kalshi_stale,
        volatility_15m_pct=vol15,
    )
    engine["arena"] = arena
    # A strong reversal warning acts as a scalp safety brake: do not keep telling the
    # user to chase a direction that multiple independent reversal clues oppose.
    if reversal.get("score", 0) >= 60:
        if reversal.get("direction") == "UP" and engine.get("scalp") == "WATCH NO":
            engine["scalp"] = "WAIT"
            engine["reason"] = "Possible upside reversal conflicts with the downside scalp signal"
        elif reversal.get("direction") == "DOWN" and engine.get("scalp") == "WATCH YES":
            engine["scalp"] = "WAIT"
            engine["reason"] = "Possible downside reversal conflicts with the upside scalp signal"

    # Automatically journal one snapshot in each time bucket (max six per market).
    # Once the market settles, refresh_learning_outcomes supplies the official YES/NO
    # label and the next model fit can learn from the mistake or correct call.
    learning_history, _learning_added = record_learning_snapshot(learning_history, active_ticker, engine, candle_engine)

    # Compact mobile navigation. Hourly price forecasting is isolated from the
    # 15-minute Kalshi flow so longer-horizon estimates do not blur the scalp view.
    selected_page = st.radio(
        "Dashboard section",
        ["📈 CHART", "⚡ SCALP", "🏆 ARENA", "🕐 HOURLY", "📊 FLOW", "📖 GUIDE"],
        horizontal=True,
        label_visibility="collapsed",
        key="dashboard_section_compact",
    )


    if selected_page == "📈 CHART":
        val = (engine.get("arena") or {}).get("validation") or {}
        if val.get("active"):
            st.caption("🏆 Arena blend passed historical validation · paper research only")
        else:
            st.caption(f"🏆 Arena training: {int(val.get('n', 0))}/120 comparable settled BTC markets")
        if active_ticker:
            market_status = kalshi_data['market'].get('status', 'unknown') if kalshi_data else 'quotes unavailable'
            st.markdown(f'<div class="compact-status">🎯 {html.escape(str(active_ticker))} · {html.escape(str(market_status))}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="compact-status">⚠️ No active Kalshi BTC 15m contract selected</div>', unsafe_allow_html=True)
        if kalshi_stale:
            age = max(0, int(time.time() - float(st.session_state.get(f"_last_good_kalshi_ts::{active_ticker}", time.time()))))
            st.caption(f"⚠️ Kalshi feed reconnecting — showing last good quotes ({age}s old).")

        # Independent candle-only 15-minute forecast. It deliberately excludes whales,
        # Kalshi prices/order flow and blockchain activity so the user can compare pure
        # price-action evidence with the broader expiration model.
        cf = engine.get("candle_only_15m", {})
        cf_dir = cf.get("direction", "UNCERTAIN")
        cf_up = float(cf.get("p_up", .5))*100
        cf_conf = float(cf.get("confidence", 0.0))
        cf_expected = cf.get("expected_price")
        cf_low, cf_high = cf.get("range_low"), cf.get("range_high")
        cf_inv = cf.get("invalidation")
        st.markdown("**15-minute candle-only forecast · no whale data**")
        f1,f2,f3,f4 = st.columns(4)
        f1.metric("Direction", cf_dir)
        f2.metric("UP / DOWN", f"{cf_up:.0f}% / {100-cf_up:.0f}%")
        f3.metric("Confidence", f"{cf_conf:.0f}%")
        f4.metric("Reversal risk", cf.get("reversal_risk", "—"))
        if cf_expected is not None and cf_low is not None and cf_high is not None:
            st.caption(f"Expected ~${cf_expected:,.0f} · likely 15m range ${cf_low:,.0f}–${cf_high:,.0f}" +
                       (f" · invalidation ${cf_inv:,.0f}" if cf_inv is not None else ""))
        reasons = [str(x) for x in cf.get("reasons", []) if x]
        if reasons:
            st.caption("Candle read: " + " · ".join(reasons[:4]))
        st.caption("This is a probabilistic BTC price-action forecast, not a guaranteed future price or trade instruction. It uses candles, volume, momentum, volatility and historical analogs only.")

        timeframe = st.radio("Candle size", ["1m", "5m", "15m", "30m", "1h"], index=0, horizontal=True, label_visibility="collapsed", key="candle_size_compact")
        with st.expander("⚙️ Chart options", expanded=False):
            window = st.selectbox("Show history", ["15m", "30m", "1h", "3h", "6h"], index=2)
            show_ema = st.toggle("Show EMA 5 / 15", value=True)
            chart_style = st.radio("Chart type", ["Candles", "Line"], horizontal=True)
        minutes = {"15m": 15, "30m": 30, "1h": 60, "3h": 180, "6h": 360}[window]
        candle_minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60}[timeframe]
        # Coinbase timestamps are already UTC datetime values. Preserve those
        # timestamps, remove duplicate buckets, then resample OHLC properly.
        source = candles.copy()
        source["time"] = pd.to_datetime(source["time"], utc=True, errors="coerce")
        for col in ("open", "high", "low", "close", "volume"):
            source[col] = pd.to_numeric(source[col], errors="coerce")
        source = source.dropna(subset=["time", "open", "high", "low", "close"])
        source = source.sort_values("time").drop_duplicates("time", keep="last")
        if candle_minutes > 1:
            source = (source.set_index("time")
                      .resample(f"{candle_minutes}min", label="left", closed="left")
                      .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
                      .dropna(subset=["open", "high", "low", "close"])
                      .reset_index())
        # Keep history available for panning; the initial view is set in JS.
        view = source.tail(300).copy()

        # Convert timestamps to real UNIX *seconds* in a way that does not depend on
        # pandas' internal datetime resolution (ns/us/ms/s). Newer pandas builds can
        # preserve a non-nanosecond dtype, so dividing astype("int64") by 1e9 can
        # collapse many candles onto the same timestamp and make the chart appear empty.
        def _unix_seconds(value):
            ts = pd.Timestamp(value)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            else:
                ts = ts.tz_convert("UTC")
            return int(ts.timestamp())

        view["epoch"] = view["time"].map(_unix_seconds).astype("int64")
        view = view.sort_values("epoch").drop_duplicates("epoch", keep="last")
        bars = [{"time": int(r.epoch), "open": float(r.open), "high": float(r.high),
                 "low": float(r.low), "close": float(r.close)} for r in view.itertuples()]
        if not bars:
            st.error("No valid BTC candles were received. Try reloading the dashboard.")
            st.stop()
        if len(bars) < 10:
            st.warning(f"Only {len(bars)} distinct {timeframe} candles received; displaying available data.")
        line = [{"time": b["time"], "value": b["close"]} for b in bars]
        ema5 = [{"time": int(t), "value": float(v)} for t, v in zip(view["epoch"], view["close"].ewm(span=5, adjust=False).mean())]
        ema15 = [{"time": int(t), "value": float(v)} for t, v in zip(view["epoch"], view["close"].ewm(span=15, adjust=False).mean())]
        visible_count = max(2, min(len(bars), max(1, minutes // candle_minutes)))
        # Lightweight Charts handles native two-finger scaling and one-finger panning.
        # Pass unique, strictly ascending UNIX timestamps (seconds, not milliseconds).
        clean_bars = sorted({b["time"]: b for b in bars}.values(), key=lambda b: b["time"])
        if len(clean_bars) < 2:
            st.error("At least two distinct candles are required to draw the chart.")
            st.stop()
        closes = pd.Series([b["close"] for b in clean_bars], dtype="float64")
        overlays = []
        for span, color in ((5, "#fbbf24"), (15, "#a78bfa")):
            avg = closes.ewm(span=span, adjust=False).mean()
            overlays.append({"color": color, "points": [
                {"time": b["time"], "value": float(v)} for b, v in zip(clean_bars, avg)
            ]})
        strike_value = engine.get("target")
        try:
            strike_value = float(strike_value) if strike_value is not None else None
            if strike_value is not None and not np.isfinite(strike_value):
                strike_value = None
        except (TypeError, ValueError):
            strike_value = None

        chart_data = json.dumps({
            "bars": clean_bars,
            "line": [{"time": b["time"], "value": b["close"]} for b in clean_bars],
            "overlays": overlays if show_ema else [],
            "style": chart_style,
            "timeframe": timeframe,
            "visible": visible_count,
            "strike": strike_value,
            "reference": float(engine.get("reference_price")) if engine.get("reference_price") is not None else None,
        }, allow_nan=False)
        chart_html = r"""<!doctype html><html><head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />
        <style>
        html,body{margin:0;background:#0b0b11;color:#d9e3f1;font-family:system-ui;overflow:hidden}
        #frame{position:relative;width:100%;height:300px;overflow:hidden}
        #chart{width:100%;height:300px;touch-action:none;overscroll-behavior:contain}
        #status{position:absolute;top:9px;left:12px;pointer-events:none;background:#120e16d9;
          border:1px solid #56303a;border-radius:8px;padding:6px 9px;font-size:12px;z-index:2}
        #reset-view{position:absolute;top:9px;right:70px;z-index:3;background:#211925;color:#d9e3f1;border:1px solid #56303a;border-radius:6px;padding:5px 8px;cursor:pointer}
        #error{color:#ff9eaa;padding:15px;display:none}
        </style></head><body>
        <div id="frame"><button id="reset-view" type="button">Reset view</button><div id="status">COINBASE BTC/USD · __TIMEFRAME__</div><div id="chart"></div><div id="error"></div></div>
        <script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js"></script>
        <script>
        const data=__PAYLOAD__;
        const root=document.getElementById('chart');
        const error=document.getElementById('error');
        try {
          if(!window.LightweightCharts) throw new Error('Chart library unavailable.');
          const LC=window.LightweightCharts;
          const chart=LC.createChart(root,{
            width:root.clientWidth,height:300,
            layout:{background:{type:'solid',color:'#0b0b11'},textColor:'#b9c9df'},
            grid:{vertLines:{color:'#251c27'},horzLines:{color:'#251c27'}},
            rightPriceScale:{borderColor:'#51303b',scaleMargins:{top:.08,bottom:.12}},
            timeScale:{timeVisible:true,secondsVisible:false,borderColor:'#51303b',
              barSpacing:8,minBarSpacing:2,rightOffset:3,lockVisibleTimeRangeOnResize:true},
            crosshair:{mode:LC.CrosshairMode.Magnet},
            handleScroll:{mouseWheel:false,pressedMouseMove:true,horzTouchDrag:false,vertTouchDrag:false},
            handleScale:{axisPressedMouseMove:false,mouseWheel:false,pinch:true},
            kineticScroll:{touch:true,mouse:false}
          });
          const main=data.style==='Candles'
            ?chart.addCandlestickSeries({upColor:'#34d399',downColor:'#fb7185',borderVisible:false,
              wickUpColor:'#34d399',wickDownColor:'#fb7185'})
            :chart.addLineSeries({color:'#60a5fa',lineWidth:2});
          main.setData(data.style==='Candles'?data.bars:data.line);

          // Kalshi strike line. It stays fixed while the BTC candles pan/zoom so a
          // crossing is immediately visible on the chart.
          if (Number.isFinite(data.strike)) {
            main.createPriceLine({
              price:data.strike,
              color:'#ff3b5c',
              lineWidth:2,
              lineStyle:LC.LineStyle.Dashed,
              axisLabelVisible:true,
              title:'STRIKE'
            });
          }
          if (Number.isFinite(data.reference)) {
            main.createPriceLine({
              price:data.reference,
              color:'#60a5fa',
              lineWidth:1,
              lineStyle:LC.LineStyle.Dotted,
              axisLabelVisible:true,
              title:'BRTI PROXY'
            });
          }

          data.overlays.forEach(o=>{
            const series=chart.addLineSeries({color:o.color,lineWidth:1,
              lastValueVisible:false,priceLineVisible:false});series.setData(o.points);
          });
          const viewKey='btc-kalshi-view-'+data.timeframe;
          // Read before chart layout/resize events can overwrite the previous view.
          let savedView=null;
          try { savedView=JSON.parse(localStorage.getItem(viewKey)||'null'); } catch(_) {}
          let viewReady=false;
          const validView=v=>v && Number.isFinite(v.span) && v.span>0 && Number.isFinite(v.rightOffset);
          function defaultView(){
            const n=data.bars.length;
            const visible=Math.min(n,Math.max(3,data.visible));
            chart.timeScale().setVisibleLogicalRange({from:n-visible-1,to:n+2});
          }
          function saveView(r){
            if(!viewReady || !r || !Number.isFinite(r.from) || !Number.isFinite(r.to) || r.to<=r.from) return;
            const anchorIndex=Math.max(0,Math.min(data.bars.length-1,Math.floor(r.to)));
            try {
              localStorage.setItem(viewKey,JSON.stringify({
                span:r.to-r.from,rightOffset:(data.bars.length-1)-r.to,
                anchorTime:data.bars[anchorIndex].time,anchorOffset:r.to-anchorIndex,
                followLatest:r.to>=data.bars.length-1
              }));
            } catch(_) {}
          }
          function setInitialView(){
            if(validView(savedView)){
              let to=(data.bars.length-1)-savedView.rightOffset;
              // Keep historical candles in place when the rolling data window moves.
              if(savedView.followLatest===false && Number.isFinite(savedView.anchorTime) && Number.isFinite(savedView.anchorOffset)){
                const index=data.bars.findIndex(b=>b.time===savedView.anchorTime);
                if(index>=0) to=index+savedView.anchorOffset;
              }
              chart.timeScale().setVisibleLogicalRange({from:to-savedView.span,to});
            } else {
              defaultView();
            }
            // Subscribe only after restoration: initial layout must never save defaults.
            requestAnimationFrame(()=>{
              viewReady=true;
              chart.timeScale().subscribeVisibleLogicalRangeChange(saveView);
            });
          }
          requestAnimationFrame(()=>requestAnimationFrame(setInitialView));
          document.getElementById('reset-view').addEventListener('click',()=>{
            if(!viewReady) return;
            defaultView();
            saveView(chart.timeScale().getVisibleLogicalRange());
          });
          window.addEventListener('pagehide',()=>saveView(chart.timeScale().getVisibleLogicalRange()));
          new ResizeObserver(()=>{
            if(root.clientWidth>0) chart.applyOptions({width:root.clientWidth});
          }).observe(root);

          // Mobile controls: custom one-finger horizontal panning + native two-finger pinch.
          // Android browsers inside Streamlit iframes can swallow Lightweight Charts' built-in
          // one-finger drag, so we pan the logical time range ourselves.
          let panStartX=null;
          let panStartRange=null;
          let panMoved=false;
          root.addEventListener('touchstart', e => {
            if (e.touches.length===1) {
              panStartX=e.touches[0].clientX;
              const r=chart.timeScale().getVisibleLogicalRange();
              panStartRange=r ? {from:r.from,to:r.to} : null;
              panMoved=false;
            } else {
              panStartX=null;
              panStartRange=null;
            }
          }, {passive:true});

          root.addEventListener('touchmove', e => {
            if (e.touches.length!==1 || panStartX===null || !panStartRange) return;
            e.preventDefault();
            const dx=e.touches[0].clientX-panStartX;
            if (Math.abs(dx)>3) panMoved=true;
            const barsVisible=Math.max(1, panStartRange.to-panStartRange.from);
            const pxPerBar=Math.max(2, root.clientWidth/barsVisible);
            const shift=-dx/pxPerBar;
            chart.timeScale().setVisibleLogicalRange({
              from:panStartRange.from+shift,
              to:panStartRange.to+shift
            });
          }, {passive:false});

          root.addEventListener('touchend', e => {
            if (e.touches.length===0) {
              panStartX=null;
              panStartRange=null;
            }
          }, {passive:true});
          root.addEventListener('touchcancel', () => {
            panStartX=null;
            panStartRange=null;
          }, {passive:true});

          root.addEventListener('contextmenu',e=>e.preventDefault());
        } catch(e){error.style.display='block';error.textContent='Chart error: '+e.message;}
        </script></body></html>"""
        chart_html = chart_html.replace("__PAYLOAD__", chart_data).replace("__TIMEFRAME__", timeframe)
        components.html(chart_html, height=308, scrolling=False)
        refresh_label = refresh_mode.replace(" · ", " ")
        if strike_value is not None:
            side_text = "ABOVE" if price >= strike_value else "BELOW"
            ref_now = float(engine.get("reference_price") or price)
            ref_side = "ABOVE" if ref_now >= strike_value else "BELOW"
            st.caption(f"🔴 Strike ${strike_value:,.2f} · Coinbase {side_text} ${abs(price-strike_value):,.2f} · BRTI proxy {ref_side} ${abs(ref_now-strike_value):,.2f} · ⚡ {refresh_label} · 👆 Drag · 🤏 Pinch")
        else:
            st.caption(f"⚡ {refresh_label} · 👆 Drag · 🤏 Pinch zoom · Tap candle · Strike unavailable for this contract")
        # Compact all essential live information into one terminal-style panel.
        expiry_raw = None
        if kalshi_data:
            market_info = kalshi_data["market"]
            expiry_raw = market_info.get("close_time") or market_info.get("expiration_time")
            target_raw = market_info.get("floor_strike") or market_info.get("cap_strike") or market_info.get("strike_price")
            try:
                target_value = float(target_raw)
                distance = price - target_value
                target_text = f"${target_value:,.0f}"
                distance_text = f"${distance:+,.0f}"
            except (ValueError, TypeError):
                target_text, distance_text = "—", "—"
        else:
            target_text, distance_text = "—", "—"

        # Outcome-first terminal: prioritize the settlement estimate and model confidence.
        timer_expiry = None
        if expiry_raw:
            try:
                timer_expiry = pd.to_datetime(expiry_raw, utc=True).isoformat()
            except (ValueError, TypeError, OverflowError):
                pass
        yes_buy = show_price(kalshi_data["yes_ask"]) if kalshi_data else "—"
        no_buy = show_price(kalshi_data["no_ask"]) if kalshi_data else "—"
        yes_sell = show_price(kalshi_data["yes_bid"]) if kalshi_data else "—"
        no_sell = show_price(kalshi_data["no_bid"]) if kalshi_data else "—"

        ref_price = float(engine.get("reference_price") or price)
        if target_text != "—":
            try:
                ref_distance = ref_price - float(target_value)
                distance_text = f"${ref_distance:+,.0f}"
            except Exception:
                pass
        prob_above = engine.get("prob_above")
        prob_below = engine.get("prob_below")
        prob_above_text = f"{prob_above*100:.0f}%" if prob_above is not None else "—"
        prob_below_text = f"{prob_below*100:.0f}%" if prob_below is not None else "—"
        conf_text = f"{engine.get('confidence',0):.0f}/100"
        _learn = engine.get("learning_adjustment") or {}
        _lm = engine.get("learning_model") or {}
        if _learn.get("active"):
            conf_sub = f"{str(engine.get('confidence_label','LOW')).lower()} · learn {_learn.get('adjustment_pp',0):+.1f}pp"
        else:
            conf_sub = f"{str(engine.get('confidence_label','LOW')).lower()} · {_lm.get('resolved_markets',0)} learned"
        venues = int((engine.get("brti_proxy") or {}).get("count", 0))
        proxy_sub = f"{venues} venue proxy · not official BRTI" if venues else "Coinbase fallback · not BRTI"
        edge = engine.get("model_edge")
        edge_text = engine.get("trade_review", {}).get("summary", "NO TRADE · missing inputs")
        final_min = engine.get("final_minute")
        if final_min:
            settle_note = f"final-60s proxy {final_min.get('observed_sec',0):.0f}s observed"
        else:
            settle_note = "Kalshi settles on 60s BRTI average"

        outcome_text = str(engine.get("outcome", "UNCERTAIN"))
        possible_outcome, possible_detail = possible_expiration_outcome(engine)
        if outcome_text.startswith("ABOVE"):
            mood, mood_color = "OUTCOME MODEL FAVORS ABOVE", "#36d7a4"
        elif outcome_text.startswith("BELOW"):
            mood, mood_color = "OUTCOME MODEL FAVORS BELOW", "#ff6c78"
        else:
            mood, mood_color = "NO HIGH-CONFIDENCE OUTCOME CALL", "#ffcf77"

        rev = engine.get("reversal") or {}
        rev_status = str(rev.get("status", "NO CLEAR REVERSAL"))
        rev_score = float(rev.get("score", 0.0) or 0.0)
        rev_hist = rev.get("historical_prob")
        rev_hist_text = f"hist {rev_hist*100:.0f}%" if rev_hist is not None else "hist n/a"
        rev_whale = rev.get("whale_pressure")
        if rev_whale is None:
            rev_whale_text = "whales n/a"
        elif rev_whale > .08:
            rev_whale_text = "whales buying"
        elif rev_whale < -.08:
            rev_whale_text = "whales selling"
        else:
            rev_whale_text = "whales balanced"
        rev_sub = f"{rev_score:.0f}/100 · {rev_hist_text} · {rev_whale_text}"
        rev_color = "#36d7a4" if rev.get("direction") == "UP" else "#ff6c78" if rev.get("direction") == "DOWN" else "#ffcf77"

        intel = {
            "expiry": timer_expiry, "btc": f"${ref_price:,.0f}", "yes": yes_buy, "no": no_buy,
            "yesSell": yes_sell, "noSell": no_sell, "outcome": outcome_text,
            "scalp": engine["scalp"], "target": target_text, "distance": distance_text,
            "above": prob_above_text, "below": prob_below_text, "confidence": conf_text,
            "confSub": conf_sub, "proxySub": proxy_sub, "edge": edge_text,
            "settleNote": settle_note, "mood": mood, "moodColor": mood_color,
            "reversal": rev_status, "reversalSub": rev_sub, "reversalColor": rev_color,
            "possibleOutcome": possible_outcome, "possibleDetail": possible_detail,
        }
        intel_json = json.dumps(intel)
        intel_html = r"""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
        <style>
        *{box-sizing:border-box}html,body{margin:0;background:transparent;color:#edf5ff;font-family:system-ui,sans-serif}
        .panel{border:1px solid #71303d;border-radius:11px;background:linear-gradient(125deg,#210e17,#10111a 72%);padding:8px}
        .head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px}
        .mood{font-size:10px;font-weight:900;letter-spacing:.08em}.sub{font-size:9px;color:#967985;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .grid4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:5px}.grid4b{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:5px;margin-top:5px}
        .tile{background:#111722;border:1px solid #302631;border-radius:8px;padding:6px;min-width:0}.tile small{display:block;color:#8197b2;font-size:8px;font-weight:800;letter-spacing:.06em;white-space:nowrap}
        .tile strong{display:block;margin-top:2px;font-size:13px;line-height:1.1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.tile em{display:block;margin-top:2px;color:#8fa0b3;font-size:8px;font-style:normal;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .rev{margin-top:5px;display:flex;align-items:center;justify-content:space-between;gap:8px;border:1px solid #3b3138;background:#0f141d;border-radius:8px;padding:5px 7px}.rev b{font-size:9px;letter-spacing:.04em}.rev span{color:#94a5b8;font-size:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .foot{margin-top:5px;color:#8e7a84;font-size:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        @media(max-width:430px){.panel{padding:6px}.grid4,.grid4b{gap:3px}.tile{padding:5px 4px}.tile strong{font-size:11px}.tile small,.tile em,.foot{font-size:7px}.mood{font-size:9px}}
        </style></head><body><div class="panel">
          <div class="head"><div class="mood" id="mood"></div><div class="sub">OUTCOME FUSION · BRTI-AWARE PROXY</div></div>
          <div class="grid4">
            <div class="tile"><small>TIME LEFT</small><strong id="count">--:--</strong><em id="settleNote"></em></div>
            <div class="tile"><small>BRTI PROXY</small><strong id="btc"></strong><em id="proxySub"></em></div>
            <div class="tile"><small>YES BUY</small><strong id="yes"></strong><em id="yesSell"></em></div>
            <div class="tile"><small>NO BUY</small><strong id="no"></strong><em id="noSell"></em></div>
          </div>
          <div class="grid4b">
            <div class="tile"><small>EXPIRATION OUTCOME</small><strong id="outcome"></strong><em id="edge"></em></div>
            <div class="tile"><small>EST. ABOVE</small><strong id="above"></strong><em id="below"></em></div>
            <div class="tile"><small>EVIDENCE SCORE</small><strong id="confidence"></strong><em id="confSub"></em></div>
            <div class="tile"><small>SCALP</small><strong id="scalp"></strong><em>manual exits · experimental</em></div>
          </div>
          <div class="rev"><b id="possibleOutcome" style="color:#ffcf77"></b><span id="possibleDetail"></span></div>
          <div class="rev" id="revBox"><b id="reversal"></b><span id="reversalSub"></span></div>
          <div class="foot" id="distance"></div>
        </div><script>
        const d=__INTEL__;
        document.getElementById('possibleOutcome').textContent=d.possibleOutcome||'UNAVAILABLE';document.getElementById('possibleDetail').textContent=d.possibleDetail||'';
        for(const id of ['btc','yes','no','outcome','above','confidence','scalp']) document.getElementById(id).textContent=d[id]||'—';
        document.getElementById('yesSell').textContent='sell '+(d.yesSell||'—');document.getElementById('noSell').textContent='sell '+(d.noSell||'—');
        document.getElementById('below').textContent='below '+(d.below||'—');document.getElementById('confSub').textContent=d.confSub||'—';document.getElementById('proxySub').textContent=d.proxySub||'—';document.getElementById('edge').textContent=d.edge||'—';document.getElementById('settleNote').textContent=d.settleNote||'—';
        const rv=document.getElementById('reversal');rv.textContent=d.reversal||'NO CLEAR REVERSAL';rv.style.color=d.reversalColor||'#ffcf77';document.getElementById('reversalSub').textContent=d.reversalSub||'—';document.getElementById('revBox').style.borderColor=d.reversalColor||'#3b3138';
        document.getElementById('distance').textContent='Proxy vs target: '+(d.distance||'—')+' · official BRTI is the settlement source; this is an estimate, not a guarantee';
        const m=document.getElementById('mood');m.textContent=d.mood||'NO HIGH-CONFIDENCE OUTCOME CALL';m.style.color=d.moodColor||'#ffcf77';
        const c=document.getElementById('count');function tick(){if(!d.expiry){c.textContent='--:--';return}const ms=Date.parse(d.expiry)-Date.now();if(!Number.isFinite(ms)||ms<=0){c.textContent='EXPIRED';return}const sec=Math.ceil(ms/1000),h=Math.floor(sec/3600),mm=Math.floor((sec%3600)/60),ss=sec%60;c.textContent=(h?String(h).padStart(2,'0')+':':'')+String(mm).padStart(2,'0')+':'+String(ss).padStart(2,'0')}tick();setInterval(tick,1000);
        </script></body></html>""".replace("__INTEL__", intel_json)
        components.html(intel_html, height=216, scrolling=False)
        direction_score = np.clip((ret5 if pd.notna(ret5) else 0) * 18 + (ret15 if pd.notna(ret15) else 0) * 5, -100, 100)
        if abs(direction_score) < 8:
            context = "NO CLEAR EDGE — wait for confirmation"
        elif direction_score > 0:
            context = "UPSIDE MOMENTUM — only consider a long after checking Kalshi price and spread"
        else:
            context = "DOWNSIDE MOMENTUM — only consider a short/downside thesis after checking Kalshi price and spread"

        # Keep secondary information and tools behind one disclosure so the default
        # mobile view stays close to a single terminal screen.
        with st.expander("＋ More data / tools", expanded=False):
            st.markdown("**Market details**")
            if kalshi_data:
                st.caption(f"Ticker: {active_ticker} · Status: {kalshi_data['market'].get('status', 'unknown')} · Expiry UTC: {kalshi_data['market'].get('close_time', 'unknown')}")
                st.caption(f"YES buy {yes_buy} / sell {yes_sell} · NO buy {no_buy} / sell {no_sell} · Target {target_text} · Distance {distance_text}")
            elif kalshi_error:
                st.warning(f"Kalshi quotes unavailable: {kalshi_error}")
            else:
                st.info("No active Kalshi contract selected.")

            st.markdown("**Reversal radar**")
            rev = engine.get("reversal") or {}
            st.caption(f"{rev.get('status','NO CLEAR REVERSAL')} · score {rev.get('score',0):.0f}/100 · current trend {rev.get('trend','MIXED')}")
            if rev.get("historical_prob") is not None:
                hist = rev.get("historical") or {}
                st.caption(f"Similar historical states reversed {rev['historical_prob']*100:.1f}% over ~{hist.get('horizon_min',5)}m · effective sample ≈ {hist.get('effective_n',0):.0f}")
            if rev.get("whale_pressure") is not None:
                st.caption(f"Large-trade pressure {rev['whale_pressure']:+.2f} · ≥$100k buys ${rev.get('large_buy_usd',0)/1e6:.2f}M · sells ${rev.get('large_sell_usd',0)/1e6:.2f}M")
            for why in rev.get("reasons", [])[:4]:
                st.caption(f"• {why}")
            st.caption("A reversal watch is a warning that the current short-term move may be failing; it is not a guaranteed turn.")

            st.markdown("**Outcome Fusion v2**")
            if engine.get("prob_above") is not None:
                st.caption(
                    f"Estimated ABOVE {engine['prob_above']*100:.1f}% · BELOW {engine['prob_below']*100:.1f}% · "
                    f"model confidence {engine['confidence']:.0f}/100 ({engine['confidence_label']}) · call: {engine['outcome']}"
                )
                proxy_info = engine.get("brti_proxy") or {}
                venue_text = ", ".join(f"{k} ${v:,.0f}" for k,v in (proxy_info.get("venues") or {}).items()) or "Coinbase fallback"
                dispersion = proxy_info.get("dispersion_bps")
                disp_text = f" · cross-venue dispersion {dispersion:.1f} bps" if dispersion is not None else ""
                st.caption(f"BRTI-aware proxy ${engine['reference_price']:,.2f} from {venue_text}{disp_text}. This is not the official BRTI.")
                comp_names = {
                    "statistical":"realized-vol model",
                    "historical_analogs":"24h historical analogs",
                    "kalshi_market":"Kalshi market",
                    "flow_candles":"flow + candles",
                    "final_60s_avg":"final-60s average model",
                }
                comp_text = []
                for name, row in (engine.get("components") or {}).items():
                    comp_text.append(f"{comp_names.get(name,name)} {row['prob']*100:.0f}%")
                if comp_text:
                    st.caption("Components: " + " · ".join(comp_text))
                stat_info = engine.get("stat") or {}
                analog_info = engine.get("analog") or {}
                if stat_info:
                    st.caption(f"1σ expected move to settlement window ≈ ${stat_info.get('expected_move_dollars',0):,.0f} · strike distance z {stat_info.get('z_distance',0):+.2f}")
                if analog_info:
                    st.caption(f"Historical analog effective sample ≈ {analog_info.get('effective_n',0):.0f} · horizon {analog_info.get('horizon_min',0)}m · analog SE ≈ {analog_info.get('se',0)*100:.1f}pp")
                if engine.get("final_minute"):
                    fm = engine["final_minute"]
                    st.caption(f"Final 60s window: {fm.get('observed_sec',0):.0f}s observed · proxy average ${fm.get('observed_avg',0):,.2f} · required remaining average ${fm.get('required_future_avg',0):,.2f}")
            else:
                st.caption("No settlement probability is available because the strike or required live inputs are missing.")
            st.caption("Kalshi KXBTC15M settles from the simple average of 60 official BRTI values during the last minute. The dashboard uses a multi-exchange proxy and deliberately shows UNCERTAIN when evidence is not strong enough.")

            st.markdown("**Candle intelligence**")
            tf_text = " · ".join([f"{m}m {candle_engine['timeframes'][m]['score']:+.0f}" for m in (1,5,15)])
            st.caption(f"{candle_engine['bias']} · scalp score {candle_engine['scalp_score']:+.0f}/100 · expiry score {candle_engine['outcome_score']:+.0f}/100 · agreement {candle_engine['agreement']:.0%} · {tf_text}")
            if candle_engine["patterns"]:
                pattern_text = " · ".join([f"{p['tf']} {p['name']} ({p['score']:+.0f})" for p in candle_engine["patterns"][:6]])
                st.caption(f"Confirmed/observed: {pattern_text}")
            st.caption("Completed candles carry most of the weight. The still-forming candle is down-weighted because its shape can change before close.")

            st.markdown("**Momentum**")
            st.caption(f"{context} · Score {direction_score:+.1f}/100 · 15m realized volatility {vol15:.3f}%" if pd.notna(vol15) else f"{context} · Score {direction_score:+.1f}/100")

            st.markdown("**Whale + flow evidence**")
            if whale_error:
                st.caption(f"Exchange trades unavailable: {whale_error}")
            else:
                large = [(side, usd) for side, usd in whale_trades if usd >= 100000]
                pressure_text = f"{engine['pressure']:+.1%}" if engine['pressure'] is not None else "Unavailable"
                st.caption(f"Coinbase trades sampled: {len(whale_trades)} · ≥$100k: {len(large)} · Aggressive pressure: {pressure_text}")
            if chain_error:
                st.caption(f"Blockchain activity unavailable: {chain_error}")
            else:
                st.caption(f"Bitcoin mempool: {chain_count:,} unconfirmed · {chain_vsize / 1e6:.2f} MB vsize")
            bid_text = f"{engine['bid_balance']:+.1%}" if engine['bid_balance'] is not None else "Unavailable"
            spread_text = f"{engine['spread']:.1f}¢" if engine['spread'] is not None else "Unavailable"
            st.caption(f"Kalshi top-five bid balance: {bid_text} · YES spread: {spread_text}")

            st.markdown("**Adaptive learning**")
            lm = engine.get("learning_model") or {}
            la = engine.get("learning_adjustment") or {}
            rb = lm.get("base_brier")
            rl = lm.get("learned_brier")
            brier_text = "collecting labels" if rb is None else (
                f"Brier {rb:.3f}" if rl is None else f"held-out Brier {rb:.3f} → {rl:.3f}"
            )
            learn_status = lm.get("status", "COLLECTING")
            st.caption(
                f"{learn_status} · {lm.get('resolved_markets',0)} resolved markets / {lm.get('resolved_rows',0)} snapshots · "
                f"{brier_text} · current adjustment {la.get('adjustment_pp',0):+.1f}pp"
            )
            if lm.get("hit_rate") is not None:
                st.caption(f"Held-out direction hit rate: {lm['hit_rate']*100:.1f}% · blend weight {lm.get('blend_weight',0)*100:.0f}% when active.")
            st.caption(
                "The learner only changes the live probability after at least 100 independent settled markets AND chronological held-out Brier score improves. "
                "That prevents a few lucky trades from making the bot overconfident."
            )
            if st.button("Check old markets for new settlements", key="refresh_learning_results"):
                learning_history, newly = refresh_learning_outcomes(learning_history, force=True, max_markets=40)
                st.success(f"Updated {newly} learning snapshots." if newly else "No new settled labels found yet.")
            import_file = st.file_uploader("Import previous learning CSV", type=["csv"], key="learning_csv_import")
            if import_file is not None and st.button("Merge imported history", key="merge_learning_csv"):
                try:
                    imported = _normalize_learning_history(pd.read_csv(import_file))
                    merged = pd.concat([learning_history, imported], ignore_index=True)
                    merged = _normalize_learning_history(merged).tail(2500)
                    save_learning_history(merged)
                    st.success(f"Merged {len(imported)} rows. The learner will re-evaluate them on the next refresh.")
                except Exception as exc:
                    st.error(f"Could not import learning history: {exc}")
            if len(learning_history):
                st.download_button(
                    "Export learning history (CSV)", learning_history.to_csv(index=False),
                    file_name="btc_kalshi_learning.csv", mime="text/csv", key="export_learning_history"
                )
                preview_cols = [c for c in ["recorded_utc","ticker","checkpoint","base_prob_above","adaptive_prob_above","outcome_call","result"] if c in learning_history.columns]
                st.dataframe(learning_history[preview_cols].tail(20), hide_index=True, use_container_width=True, height=180)
            persistence = st.session_state.get("learning_save_status", "local only")
            unresolved_count = int((~learning_history["result"].isin(["yes", "no"])).sum()) if len(learning_history) else 0
            if _learning_token():
                st.caption(f"Persistence: {persistence}. GitHub-backed history is enabled via LEARNING_GITHUB_TOKEN.")
                st.caption(
                    f"Storage check: {st.session_state.get('learning_remote_read_status','waiting')} · "
                    f"unresolved snapshots: {unresolved_count} · "
                    f"resolver: {st.session_state.get('learning_result_status','waiting for first settlement check')}"
                )
            else:
                st.caption("Persistence: local runtime + CSV export. Streamlit may reset local files on a redeploy; add a LEARNING_GITHUB_TOKEN secret for automatic GitHub-backed history.")

            st.markdown("**Paper signal tracker**")
            if "paper_signals" not in st.session_state:
                st.session_state.paper_signals = []
            if st.button("Record current signals", type="secondary"):
                st.session_state.paper_signals.append({"recorded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "ticker": active_ticker or "none", "coinbase_btc": round(price, 2),
                    "brti_proxy": round(engine.get("reference_price", price), 2), "outcome_call": engine["outcome"],
                    "prob_above_pct": round(engine.get("prob_above", np.nan)*100, 1) if engine.get("prob_above") is not None else np.nan,
                    "model_confidence": round(engine.get("confidence", 0), 1), "scalp_watch": engine["scalp"],
                    "model_edge_pp": round(engine.get("model_edge", np.nan), 1) if engine.get("model_edge") is not None else np.nan,
                    "candle_bias": candle_engine["bias"], "candle_scalp_score": round(candle_engine["scalp_score"], 1),
                    "candle_expiry_score": round(candle_engine["outcome_score"], 1), "settled_result": "NOT VERIFIED"})
                st.session_state.paper_signals = st.session_state.paper_signals[-200:]
            if st.session_state.paper_signals:
                st.dataframe(pd.DataFrame(st.session_state.paper_signals), hide_index=True, use_container_width=True, height=180)
                st.download_button("Export paper signals (CSV)", pd.DataFrame(st.session_state.paper_signals).to_csv(index=False),
                                   file_name="btc_kalshi_paper_signals.csv", mime="text/csv")
            st.caption("Manual paper signals remain session-only. The adaptive journal above is separate: it records fixed checkpoints automatically and verifies settled YES/NO outcomes through Kalshi.")



    if selected_page == "🏆 ARENA":
        arena = engine.get("arena") or {}
        review = arena.get("paper") or {}
        validation = arena.get("validation") or {}
        st.markdown("### 🏆 Battle of the Bots · Model Arena")
        st.caption("Score models against officially settled BTC contracts. Lower Brier score means better historical probability estimates, not higher trading profits.")
        a1, a2, a3 = st.columns(3)
        base, independent, blended = arena.get("baseline_p"), arena.get("independent_p"), arena.get("blend_p")
        a1.metric("Current YES", f"{base:.1%}" if base is not None else "—")
        a2.metric("Independent YES", f"{independent:.1%}" if independent is not None else "—")
        a3.metric("Validated blend", f"{blended:.1%}" if validation.get("active") and blended is not None else "LOCKED")
        n = int(validation.get("n", 0))
        st.progress(min(1.0, n / 120.0), text=f"Settled markets for validation · {n}/120")
        st.caption(validation.get("status", "Collecting independent results"))
        st.caption("Independent model: strike/volatility 65%, similar historical setups 25%, flow/candles 10%. Kalshi's market price is excluded to prevent circular edge estimates.")
        if validation.get("recent_base_brier") is not None:
            v1, v2 = st.columns(2)
            v1.metric("Old model Brier · 120 markets", f"{validation['recent_base_brier']:.4f}")
            v2.metric("Arena blend Brier · 120 markets", f"{validation['recent_blend_brier']:.4f}")
        st.markdown("**Model leaderboard · official settlements**")
        board = arena.get("scoreboard") or []
        if board:
            visible = [{k: row[k] for k in ("Model", "Markets", "Brier ↓", "Hit rate", "95% hit CI", "Status")} for row in board]
            st.dataframe(pd.DataFrame(visible), hide_index=True, use_container_width=True, height=min(340, 45 * (len(visible)+1)))
            st.caption("Only one historical checkpoint is counted per market. Under 100 results are provisional. These are prediction scores, not backtested order fills.")
        else:
            st.info("No independently verified model outcomes yet. Keep collecting and reconciling Kalshi settlements.")
        st.markdown("**Conservative paper-entry research · one contract**")
        if review.get("status") == "PAPER CANDIDATE":
            st.success(f"PAPER ONLY · {review.get('side')} · hypothetical net EV {review.get('net_ev_cents'):+.1f}¢")
        else:
            st.warning("NO TRADE · Research watch")
        st.caption(review.get("reason", "Waiting for live market inputs"))
        if review.get("entry_cents") is not None:
            st.caption(f"Estimated 1-contract entry {review['entry_cents']:.1f}¢ · 3¢ assumed fee + 2¢ slippage allowance, not a verified Kalshi fee.")
        st.caption("Blocked for stale prices, wide spread, thin orderbook, <60s until expiry, volatile regimes, weak multi-exchange agreement or insufficient validated settlements.")
        with st.expander("How each model competes"):
            st.markdown("""
            - **Volatility / strike:** Prices settlement against the Kalshi strike using observed BTC volatility.
            - **Historical analogs:** Compares similar previously observed BTC setups.
            - **Flow / candles:** Looks at recent directional BTC behavior and aggressive trade flow.
            - **Kalshi consensus:** Uses observed market quotes as a benchmark, not a free edge.
            - **Existing fusion / learner:** Your prior combined and adaptive predictions.
            - **Arena blend:** A fixed 70% existing + 30% independent forecast. Unlocks only after at least 120 distinct settled contracts and improvement in BOTH chronological halves.
            """)
        st.caption("Paper research only · no live trading orders · the official BRTI settlement index can differ from public price proxies.")


    if selected_page == "🕐 HOURLY":
        hf = engine.get("hourly_price_forecast") or {}
        rows = hf.get("rows") or []
        st.markdown("### 🕐 BTC hourly price forecast")
        st.caption("Possible BTC price at each upcoming hour from recent candles, momentum, volatility and similar historical setups. This view does not use Kalshi or whale-flow signals.")
        if not rows:
            st.warning(hf.get("reason", "Hourly forecast is warming up. More BTC history is needed."))
        else:
            first = rows[0]
            h1, h2, h3, h4 = st.columns(4)
            h1.metric("BTC now", f"${float(hf.get('price', price)):,.0f}")
            h2.metric("+1h estimate", f"${first['expected_price']:,.0f}")
            h3.metric("+1h likely range", f"${first['range_low']:,.0f}–${first['range_high']:,.0f}")
            h4.metric("+1h confidence", f"{first['confidence']:.0f}%")

            forecast_chart = pd.DataFrame({
                "Hour": [f"+{r['hour']}h" for r in rows],
                "Center estimate": [r["expected_price"] for r in rows],
                "Likely low": [r["range_low"] for r in rows],
                "Likely high": [r["range_high"] for r in rows],
            }).set_index("Hour")
            st.markdown("**Forecast path and uncertainty band**")
            st.line_chart(forecast_chart, height=300, use_container_width=True)

            display_rows = []
            for r in rows:
                target = pd.Timestamp(r["target_utc"])
                display_rows.append({
                    "Horizon": f"+{r['hour']} hour" if r["hour"] == 1 else f"+{r['hour']} hours",
                    "Target (CT)": target.tz_convert("America/Chicago").strftime("%I:%M %p"),
                    "Possible price": f"${r['expected_price']:,.0f}",
                    "Likely range": f"${r['range_low']:,.0f} – ${r['range_high']:,.0f}",
                    "Bias": r["direction"],
                    "Chance higher": f"{r['p_up']*100:.0f}%",
                    "Confidence": f"{r['confidence']:.0f}%",
                })
            st.dataframe(pd.DataFrame(display_rows), hide_index=True, use_container_width=True)
            st.caption("The center estimate is not a guaranteed target. 'Likely range' is the more important number, and it intentionally widens farther into the future. Confidence measures agreement/analog quality, not the probability that the exact price will occur.")
            with st.expander("How the hourly forecast is calculated", expanded=False):
                st.markdown("""
- Compares the current BTC setup with similar one-minute historical setups using 5m, 15m, 1h and 3h returns, EMA structure, RSI, volatility, ATR and volume.
- Measures the actual forward return after 1, 2, 3, 4, 5 and 6 hours for the closest historical analogs.
- Blends the analog median with damped current momentum; it does **not** project the latest move linearly.
- Uses empirical 10th–90th percentile outcomes plus realized volatility to create the displayed likely range.
- Confidence is capped and decays with horizon because farther hourly forecasts are inherently less certain.
                """)


    if selected_page == "📊 FLOW":
        if not active_ticker:
            st.warning("No open BTC 15-minute market selected. Check the sidebar.")
        elif kalshi_error:
            st.error(f"Kalshi market request failed: {kalshi_error}")
        elif kalshi_data:
            k = kalshi_data
            market = k["market"]
            st.subheader(str(market.get("title") or market.get("subtitle") or active_ticker))
            st.caption(f"Ticker: {active_ticker}")
            a, b = st.columns(2)
            a.metric("Market status", str(market.get("status", "unknown")))
            b.metric("Close / expiry (UTC)", str(market.get("close_time", market.get("expiration_time", "unknown"))))
            st.caption(f"Strike: {market.get('floor_strike', market.get('cap_strike', market.get('strike_price', 'not provided')))}")
            st.markdown("### Live YES / NO quotes")
            possible_outcome, possible_detail = possible_expiration_outcome(engine)
            st.caption(f"Lower-confidence expiry view: {possible_outcome} · {possible_detail}")
            yes_col, no_col = st.columns(2)
            with yes_col:
                st.metric("🟢 Buy YES", show_price(k["yes_ask"]))
                st.caption(f"Sell YES: {show_price(k['yes_bid'])}")
            with no_col:
                st.metric("🔴 Buy NO", show_price(k["no_ask"]))
                st.caption(f"Sell NO: {show_price(k['no_bid'])}")
            yes, no = k["yes"], k["no"]
            yes_depth = sum(q for _, q in yes)
            no_depth = sum(q for _, q in no)
            total = yes_depth + no_depth
            imbalance = ((yes_depth - no_depth) / total * 100) if total else np.nan
            x, y, z = st.columns(3)
            x.metric("YES visible depth", f"{yes_depth:,.0f}" if yes else "—")
            y.metric("NO visible depth", f"{no_depth:,.0f}" if no else "—")
            z.metric("Depth imbalance", f"{imbalance:+.1f}%" if pd.notna(imbalance) else "Unavailable")
            if k["book_error"]:
                st.warning(f"Order book unavailable: {k['book_error']}")
            elif not yes and not no:
                st.info("No visible bids were returned. This does not mean YES or NO costs 0¢.")
            st.markdown("#### Visible order-book bids")
            left, right = st.columns(2)
            with left:
                st.markdown("**YES bids**")
                st.dataframe(pd.DataFrame(yes, columns=["Price (¢)", "Contracts"]).head(15), use_container_width=True, hide_index=True)
            with right:
                st.markdown("**NO bids**")
                st.dataframe(pd.DataFrame(no, columns=["Price (¢)", "Contracts"]).head(15), use_container_width=True, hide_index=True)
            st.subheader("Decision checklist")
            review = engine.get("trade_review", {})
            st.info(review.get("summary", "NO TRADE"))
            st.caption(review.get("reason", "Missing inputs"))
            st.caption("Expiry estimates are uncalibrated. The separate SCALP tab monitors live bid depth and manual net exits. Entry watches and exit alerts have not been backtested or validated.")
            st.caption("Order-book depth is not a forecast. Quotes can change and may not be executable at the displayed size. The official settlement source is CME CF BRTI, not Coinbase.")

    if selected_page == "📖 GUIDE":
        st.markdown("""
    **How to use this dashboard**
    - **CHART:** Coinbase BTC candles plus the Kalshi strike, a blue BRTI-proxy line, countdown, estimated ABOVE/BELOW probability, model confidence, scalping watch and live quotes.
    - **ARENA:** Competing model Brier scores, settlement validation, and independent paper-only EV.\n    - **FLOW:** Kalshi order book, bid depth, YES/NO spread, and whether the expiry model clears the confidence/edge gates.
    - **GUIDE:** Explains how the outcome model is built and where uncertainty remains.

    **What Outcome Fusion v2 adds**
    - Kalshi's BTC 15-minute contracts settle from the **simple average of 60 official CME CF BRTI values during the final minute**, not from a Coinbase close.
    - The dashboard therefore builds a **BRTI-aware proxy** from public prices on several BRTI constituent exchanges (Coinbase, Kraken, Bitstamp and Gemini) and uses the median to reduce single-exchange basis noise. It is still only a proxy, not the licensed official BRTI.
    - A cached **24-hour 1-minute history** is used to find prior BTC regimes with similar 5m/15m momentum, volatility and EMA structure. The bot checks what happened over the same remaining horizon and produces an empirical historical-analog probability.
    - A separate **realized-volatility probability model** estimates how difficult it is for BTC to finish on the other side of the strike given the remaining time and current volatility.
    - **Kalshi's live YES price** is treated as another independent market-implied estimate instead of being ignored.
    - Candle intelligence, aggressive Coinbase trade flow and Kalshi depth are used as a **small confirmation layer**, not allowed to overpower the strike-distance/statistical models.
    - During the **last 60 seconds**, the bot records the live multi-exchange proxy and estimates the average already observed. It then calculates the average price still required over the remaining seconds for the final 60-second settlement average to finish above the strike.
    - The model reports **EST. ABOVE**, **EST. BELOW**, and **MODEL CONFIDENCE**. If the components disagree or data quality is weak, it deliberately shows **UNCERTAIN** instead of forcing ABOVE or BELOW.
    - **POSSIBLE ABOVE / BELOW** is a separate tentative expiration view using the same model: it needs at least 55% estimated directional probability; its evidence score stays visible. Near 50/50 or with weaker evidence it says **NO CLEAR LEAN**. It does not change the regular expiration call, scalp signals, or learning labels. Model confidence is an evidence score, not a success probability.

    **How candle reading is used**
    - Long bodies and closes near an extreme imply stronger one-sided control; long two-sided wicks imply conflict/indecision.
    - Reversal shapes only receive full weight when the preceding trend supports the pattern.
    - Breakouts get more weight when range and volume expand; failed breaks and wick rejection point the other way.
    - Direct interaction with the Kalshi strike is tracked separately: reclaim, breakdown, wick rejection and multiple closes holding above/below.
    - The still-forming candle is down-weighted because it can reverse before close.

    **What MODEL CONFIDENCE means**
    - It combines probability separation from 50/50, agreement between the statistical model, historical analogs, Kalshi market and flow/candle model, strike distance measured in volatility units, cross-exchange reference quality, spread and analog sample size.
    - It is an **evidence-strength score**, not a guaranteed chance that the prediction is correct. Raising the sidebar confidence gate makes the bot produce fewer directional calls.

    **Important limitations**
    - The official BRTI is licensed benchmark data. The dashboard's multi-exchange reference is an approximation and can differ by several dollars, which matters when BTC is extremely close to the strike.
    - The displayed ABOVE/BELOW percentages are model estimates and have **not yet been calibrated against a large archive of actual KXBTC15M settlements**.
    - Hidden liquidity, exchange outages, sudden news and second-by-second volatility can still flip a 15-minute result.
    - The bot does not place orders and cannot guarantee a settlement outcome.

    **Adaptive learning from previous contracts**
    - The bot now journals fixed checkpoints during each 15-minute contract and automatically attaches Kalshi's official YES/NO result after settlement.
    - A strongly regularized logistic calibration layer learns from the base probability, statistical model, historical analogs, Kalshi price, candle/flow context, strike-distance z-score, spread and cross-exchange quality.
    - All snapshots from the same market stay in the same held-out validation fold. The learner stays inactive until it has at least **100 independent resolved markets** and its held-out **Brier score** actually beats the unlearned model.
    - Even when active, the learner is blended conservatively, its maximum probability adjustment is capped, and it fades down during the final 60-second settlement window.
    - This can correct repeated biases, but it cannot guarantee future accuracy and can stop helping if market behavior changes.

    **Validation target:** keep collecting settled contracts and watch held-out Brier score, calibration, direction hit rate, and fee/slippage-adjusted paper results. The learner only receives weight when out-of-sample probability accuracy improves.
    """)
    st.caption(f"Last dashboard update: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} • Data may be delayed.")


@_fragment(run_every=live_run_every)
def render_live_dashboard():
    try:
        _render_live_dashboard_inner()
        st.session_state["_last_live_render_ok"] = time.time()
        st.session_state.pop("_last_live_render_error", None)
    except Exception as exc:
        # Never let a transient API/data-shape hiccup take down the entire mobile app.
        # The fragment will retry automatically on the next interval.
        st.session_state["_last_live_render_error"] = f"{type(exc).__name__}: {exc}"
        st.warning("Live data hit a temporary refresh error. Keeping the app open and retrying automatically…")
        last_ok = st.session_state.get("_last_live_render_ok")
        if last_ok:
            st.caption(f"Last successful live render: {max(0, int(time.time()-float(last_ok)))}s ago")
        with st.expander("Technical detail", expanded=False):
            st.code(st.session_state["_last_live_render_error"])

render_live_dashboard()
