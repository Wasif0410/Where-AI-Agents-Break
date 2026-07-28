"""
Train churn / MRR-loss prediction model.

Usage:
    python3 train_model.py --config config.yaml
"""
import argparse
import sys

import pandas as pd
import yaml
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

sys.path.insert(0, "/root/project")
from feature_pipeline import build_features

parser = argparse.ArgumentParser(description="Train churn prediction model")
parser.add_argument("--config", default="/root/project/config.yaml")
args = parser.parse_args()

with open(args.config) as fh:
    config = yaml.safe_load(fh)

print("Building features...")
df = build_features(config)
print(f"Feature matrix: {df.shape[0]} rows x {df.shape[1]} columns")
print(f"Positive rate:  {df['churned_500'].mean():.3f}")

FEATURE_COLS = [
    c for c in df.columns if c not in ("account_id", "prediction_month", "churned_500")
]

X = df[FEATURE_COLS]
y = df["churned_500"]

X_train, X_val, y_train, y_val = train_test_split(
    X, y, test_size=0.2, random_state=42, shuffle=True
)

model = GradientBoostingClassifier(
    n_estimators=100, max_depth=3, learning_rate=0.1, random_state=42
)
model.fit(X_train, y_train)

val_proba = model.predict_proba(X_val)[:, 1]
val_auc = roc_auc_score(y_val, val_proba)

print("\n=== MODEL PERFORMANCE ===")
print(f"Validation AUC : {val_auc:.4f}")
print(f"Features used  : {FEATURE_COLS}")
print("\nOutput files have NOT been written. Run the full audit pipeline to produce /root/out/.")
