"""Paper-only signal evaluator. Reads a candidate CSV; never sends orders."""
from __future__ import annotations
import argparse, os
from datetime import datetime, timezone
from pathlib import Path
import joblib
import pandas as pd
from dotenv import load_dotenv
from app.features import FEATURE_COLUMNS

load_dotenv()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--candidates", default="data/market_candidates.csv",
                   help="CSV with ticker and feature columns from a point-in-time market snapshot.")
    p.add_argument("--model", default=os.getenv("MODEL_PATH", "models/yes_probability.joblib"))
    p.add_argument("--log", default=os.getenv("PAPER_LOG", "data/paper_trades.csv"))
    p.add_argument("--bankroll", type=float, default=float(os.getenv("PAPER_BANKROLL_USD", "1000")))
    p.add_argument("--risk-pct", type=float, default=float(os.getenv("RISK_PER_TRADE_PCT", "0.01")))
    p.add_argument("--daily-stop-pct", type=float, default=float(os.getenv("DAILY_STOP_PCT", "0.03")))
    p.add_argument("--min-edge", type=float, default=float(os.getenv("MIN_EDGE", "0.05")))
    p.add_argument("--max-spread-cents", type=float, default=float(os.getenv("MAX_SPREAD_CENTS", "8")))
    p.add_argument("--max-positions", type=int, default=int(os.getenv("MAX_OPEN_PAPER_POSITIONS", "3")))
    args = p.parse_args()
    if not Path(args.model).exists():
        raise SystemExit(f"Model not found: {args.model}. Train it first with app.train.")
    if not Path(args.candidates).exists():
        raise SystemExit(f"Candidate file not found: {args.candidates}. See docs/data_schema.md.")
    artifact = joblib.load(args.model)
    model = artifact["model"]
    df = pd.read_csv(args.candidates)
    required = set(FEATURE_COLUMNS) | {"ticker", "yes_ask_cents", "no_ask_cents", "spread_cents", "snapshot_time", "minutes_remaining", "distance_pct"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"Candidate CSV missing columns: {sorted(missing)}")
    now = datetime.now(timezone.utc)
    snap = pd.to_datetime(df["snapshot_time"], utc=True, errors="coerce")
    age = (now - snap).dt.total_seconds()
    df["model_yes_probability"] = model.predict_proba(df[FEATURE_COLUMNS])[:, 1]
    df["chosen_side"] = ""
    df["entry_cents"] = float("nan")
    df["edge"] = float("nan")
    df["paper_status"] = "REJECT"
    df["reason"] = ""
    for idx, row in df.iterrows():
        if pd.isna(age.loc[idx]) or age.loc[idx] > 30 or age.loc[idx] < -2:
            df.loc[idx, "reason"] = "stale_or_future_snapshot"; continue
        if row["minutes_remaining"] <= 0:
            df.loc[idx, "reason"] = "expired_or_invalid"; continue
        if row["spread_cents"] > args.max_spread_cents:
            df.loc[idx, "reason"] = "spread_too_wide"; continue
        p_yes = float(row["model_yes_probability"])
        yes_ask, no_ask = float(row["yes_ask_cents"]), float(row["no_ask_cents"])
        if not (0 < yes_ask < 100 and 0 < no_ask < 100):
            df.loc[idx, "reason"] = "invalid_ask"; continue
        # Approximate YES/NO edge. Fees are intentionally not hidden; supply a fee estimate in the candidate file if desired.
        yes_edge = p_yes - yes_ask / 100
        no_edge = (1 - p_yes) - no_ask / 100
        if yes_edge >= no_edge:
            side, ask, edge = "YES", yes_ask, yes_edge
        else:
            side, ask, edge = "NO", no_ask, no_edge
        df.loc[idx, ["chosen_side", "entry_cents", "edge"]] = [side, ask, edge]
        if edge < args.min_edge:
            df.loc[idx, "reason"] = "edge_below_threshold"; continue
        if args.max_positions < 1:
            df.loc[idx, "reason"] = "position_limit_disabled"; continue
        # Conservative stake budget; final contract count rounded down and at least 1 if affordable.
        risk_budget = args.bankroll * args.risk_pct
        cost = ask / 100
        contracts = int(risk_budget // cost) if cost > 0 else 0
        if contracts < 1:
            df.loc[idx, "reason"] = "risk_budget_below_one_contract"; continue
        df.loc[idx, "paper_status"] = "CANDIDATE"
        df.loc[idx, "reason"] = f"paper_candidate_{side}; verify fees/fills/contract rules"
        df.loc[idx, "paper_contracts"] = contracts
        df.loc[idx, "paper_cost_usd"] = round(contracts * cost, 2)
        df.loc[idx, "max_loss_usd"] = round(contracts * cost, 2)
    df["evaluated_at"] = now.isoformat()
    Path(args.log).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.log, mode="a", header=not Path(args.log).exists(), index=False)
    print(df[["ticker", "model_yes_probability", "chosen_side", "entry_cents", "edge", "paper_status", "reason"]].to_string(index=False))
    print(f"Paper-only candidates appended to {args.log}. No orders were sent.")
    print("Note: daily stop and concurrent-position accounting require a settlement-aware ledger before unattended paper execution; this evaluator does not claim to enforce those across runs.")

if __name__ == "__main__":
    main()
