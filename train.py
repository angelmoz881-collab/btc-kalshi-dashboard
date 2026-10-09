"""Train a probability model from a manually verified point-in-time labeled dataset."""
from __future__ import annotations
import argparse
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.calibration import CalibratedClassifierCV
from app.features import FEATURE_COLUMNS, validate_training_csv

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--labels", default="data/contract_outcomes.csv")
    p.add_argument("--model", default="models/yes_probability.joblib")
    p.add_argument("--test-fraction", type=float, default=0.2)
    args = p.parse_args()
    df = pd.read_csv(args.labels)
    df = validate_training_csv(df).sort_values("timestamp") if "timestamp" in df.columns else validate_training_csv(df)
    if "timestamp" not in df.columns:
        raise ValueError("Training data must include a timestamp column for chronological validation.")
    split = int(len(df) * (1 - args.test_fraction))
    if split < 50 or len(df) - split < 20:
        raise ValueError("Need more data for chronological train/test split.")
    train, test = df.iloc[:split], df.iloc[split:]
    if train["label_yes"].nunique() < 2 or test["label_yes"].nunique() < 2:
        raise ValueError("Both chronological train and test sections must contain YES and NO outcomes.")
    base = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", HistGradientBoostingClassifier(max_iter=150, learning_rate=0.06, max_leaf_nodes=15, l2_regularization=1.0, random_state=42))
    ])
    base.fit(train[FEATURE_COLUMNS], train["label_yes"].astype(int))
    probs = base.predict_proba(test[FEATURE_COLUMNS])[:, 1]
    preds = (probs >= 0.5).astype(int)
    print(f"Chronological holdout rows: {len(test)}")
    print(f"Accuracy: {accuracy_score(test['label_yes'], preds):.4f}")
    print(f"Brier score (lower is better): {brier_score_loss(test['label_yes'], probs):.4f}")
    print(f"Log loss (lower is better): {log_loss(test['label_yes'], probs, labels=[0,1]):.4f}")
    try:
        print(f"ROC AUC: {roc_auc_score(test['label_yes'], probs):.4f}")
    except ValueError:
        print("ROC AUC unavailable for this test split.")
    # Save model trained only on the pre-holdout set to preserve honest reported evaluation.
    Path(args.model).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": base, "features": FEATURE_COLUMNS, "trained_rows": len(train)}, args.model)
    print(f"Saved model trained on {len(train)} earlier rows to {args.model}")
    print("Evaluation is not a profitability guarantee. Use walk-forward testing and include fees, spreads, slippage and realistic fills.")

if __name__ == "__main__":
    main()
