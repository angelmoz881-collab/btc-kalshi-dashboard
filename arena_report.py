"""Offline, no-network report for Bot Arena research. Never places orders."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from arena_core import score_models, validate_blend, verified_snapshots


def main():
    parser = argparse.ArgumentParser(description="Evaluate unique settled Kalshi BTC contract forecasts.")
    parser.add_argument("--history", default="data/btc_kalshi_learning.csv",
                        help="Exported dashboard learning CSV (official result labels required)")
    args = parser.parse_args()
    file = Path(args.history)
    if not file.is_file():
        raise SystemExit(f"Missing history: {file}. Export settled learning CSV from the dashboard.")
    data = pd.read_csv(file)
    verified = verified_snapshots(data)
    if verified.empty:
        raise SystemExit("No usable officially settled BTC checkpoints yet. No scores can be claimed.")
    print(f"Distinct officially settled markets scored: {len(verified)}")
    rows = score_models(data)
    if rows:
        print(pd.DataFrame(rows).drop(columns=["key"]).to_string(index=False))
    verdict = validate_blend(data)
    print(f"\nArena blend state: {verdict['status']}")
    if verdict.get("recent_base_brier") is not None:
        print("Last 120 unique contracts: "
              f"base Brier {verdict['recent_base_brier']:.4f}, "
              f"fixed blend Brier {verdict['recent_blend_brier']:.4f}")
    print("These are probability scores, not realized trades or profit. Live order execution is disabled.")


if __name__ == "__main__":
    main()
