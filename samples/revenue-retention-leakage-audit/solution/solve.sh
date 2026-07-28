#!/bin/bash
# Reference solution — hardened v5
set -e

cat > /root/project/period_utils.py << 'EOF'
from datetime import date, timedelta
import calendar

def pm_prior(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"

def ts_open(ym: str) -> str:
    return f"{ym}-01"

def ts_ws(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:])
    return (date(y, m, 1) - timedelta(days=30)).strftime("%Y-%m-%d")

def ts_prior_last(ym: str) -> str:
    prev_m = pm_prior(ym)
    y, m = int(prev_m[:4]), int(prev_m[5:])
    last = calendar.monthrange(y, m)[1]
    return f"{prev_m}-{last:02d}"

def months_enrolled(signup_date: str, ym: str) -> int:
    sd = date.fromisoformat(signup_date)
    pd_ = date(int(ym[:4]), int(ym[5:]), 1)
    return max(0, (pd_.year - sd.year) * 12 + (pd_.month - sd.month))
EOF

cat > /root/project/warehouse_ops.py << 'EOF'
from datetime import date, timedelta

def wq_a(conn, account_id: str, period_month: str) -> float:
    row = conn.execute(
        "SELECT mrr_usd FROM subscription_snapshots WHERE account_id=? AND snapshot_month=?",
        (account_id, period_month),
    ).fetchone()
    return float(row[0]) if row else 0.0

def wq_b(conn, account_id: str, t0: str, t1: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(event_count), 0) FROM product_events "
        "WHERE account_id=? AND event_date >= ? AND event_date < ?",
        (account_id, t0, t1),
    ).fetchone()
    return int(row[0])

def wq_c(conn, account_id: str, t0: str, t1: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM support_tickets "
        "WHERE account_id=? AND ticket_created_at >= ? AND ticket_created_at < ?",
        (account_id, t0, t1),
    ).fetchone()
    return int(row[0])

def wq_g(conn, account_id: str, cutoff_date: str) -> float:
    row = conn.execute(
        "SELECT health_score FROM customer_health_scores "
        "WHERE account_id=? AND score_date <= ? ORDER BY score_date DESC LIMIT 1",
        (account_id, cutoff_date),
    ).fetchone()
    return float(row[0]) if row else 70.0

def wq_h(conn, account_id: str, pred_month: str) -> int:
    prev_m = pm_prior(pred_month)
    pred_date = date(int(pred_month[:4]), int(pred_month[5:]), 1)
    row = conn.execute(
        "SELECT due_date, paid_date, paid_status FROM invoices "
        "WHERE account_id=? AND invoice_month=?",
        (account_id, prev_m),
    ).fetchone()
    if not row or not row[0]:
        return 0
    if date.fromisoformat(row[0]) + timedelta(days=3) >= pred_date:
        return 0
    if row[2] != "paid" or not row[1]:
        return 0
    if date.fromisoformat(row[1]) >= pred_date:
        return 0
    return 1

def pm_prior(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"
EOF

cat > /root/project/alt_aggregates.py << 'EOF'
"""No supplementary columns in repaired pipeline."""
import pandas as pd

def attach(conn, df: pd.DataFrame) -> pd.DataFrame:
    return df
EOF

cat > /root/project/feature_blocks.py << 'EOF'
import sqlite3
import pandas as pd
from period_utils import months_enrolled, pm_prior, ts_open, ts_prior_last, ts_ws
from warehouse_ops import wq_a, wq_b, wq_c, wq_g, wq_h

def build_matrix(conn: sqlite3.Connection, prediction_months: list[str], *, include_label: bool) -> pd.DataFrame:
    accounts = pd.read_sql("SELECT * FROM accounts", conn)
    rows = []
    for pred_month in prediction_months:
        t_open = ts_open(pred_month)
        t_prev = pm_prior(pred_month)
        t_ws = ts_ws(pred_month)
        t_vit = ts_prior_last(pred_month)
        for _, acct in accounts.iterrows():
            aid = acct["account_id"]
            row = {
                "account_id": aid,
                "prediction_month": pred_month,
                "f01": wq_a(conn, aid, t_prev),
                "f02": wq_b(conn, aid, t_ws, t_open),
                "f08": wq_g(conn, aid, t_vit),
                "f03": wq_c(conn, aid, t_ws, t_open),
                "f05": wq_h(conn, aid, pred_month),
                "f11": float(months_enrolled(acct["signup_date"], pred_month)),
            }
            if include_label:
                lbl = conn.execute(
                    "SELECT churned_500 FROM labels WHERE account_id=? AND prediction_month=?",
                    (aid, pred_month),
                ).fetchone()
                row["churned_500"] = int(lbl[0]) if lbl else 0
            rows.append(row)
    return pd.DataFrame(rows)
EOF

cat > /root/project/feature_pipeline.py << 'EOF'
import sqlite3
import pandas as pd
from alt_aggregates import attach
from feature_blocks import build_matrix

def _build(conn, months, *, include_label):
    return attach(conn, build_matrix(conn, months, include_label=include_label))

def build_features(config):
    db = config["database"]
    holdout = config.get("holdout_month", "2026-04")
    months = [m for m in config.get("feature_pipeline", {}).get("prediction_months", []) if m != holdout]
    conn = sqlite3.connect(db)
    df = _build(conn, months, include_label=True)
    conn.close()
    return df

def build_holdout_features(config):
    db = config["database"]
    holdout = config.get("holdout_month", "2026-04")
    conn = sqlite3.connect(db)
    df = _build(conn, [holdout], include_label=False)
    conn.close()
    return df
EOF

cat > /root/project/train_model.py << 'TRAIN_EOF'
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

sys.path.insert(0, "/root/project")
from feature_pipeline import build_features, build_holdout_features

parser = argparse.ArgumentParser()
parser.add_argument("--config", default="/root/project/config.yaml")
args = parser.parse_args()
config = yaml.safe_load(open(args.config))
out_dir = Path(config.get("output_dir", "/root/out"))
out_dir.mkdir(parents=True, exist_ok=True)

train_df = build_features(config)
holdout_df = build_holdout_features(config)
FEATURE_COLS = [c for c in train_df.columns if c not in ("account_id", "prediction_month", "churned_500")]

bw = pd.read_csv(config["backtest_windows"])
records = []
for _, win in bw.iterrows():
    tr = train_df[train_df["prediction_month"] <= win["train_end_month"]]
    va = train_df[train_df["prediction_month"] == win["validate_month"]]
    m = make_pipeline(StandardScaler(), LogisticRegression(random_state=42, max_iter=1000, C=0.5))
    m.fit(tr[FEATURE_COLS], tr["churned_500"])
    y = va["churned_500"].values
    p = m.predict_proba(va[FEATURE_COLS])[:, 1]
    records.append({"validate_month": win["validate_month"], "n_train": len(tr), "n_val": len(va),
                    "n_positive": int(y.sum()), "validation_auc": round(float(roc_auc_score(y, p)), 4)})
pd.DataFrame(records).to_csv(out_dir / "backtest_results.csv", index=False)

final = make_pipeline(StandardScaler(), LogisticRegression(random_state=42, max_iter=1000, C=0.5))
final.fit(train_df[FEATURE_COLS], train_df["churned_500"])
proba = final.predict_proba(holdout_df[FEATURE_COLS])[:, 1]
ho = holdout_df[["account_id", "prediction_month"]].copy()
ho["churn_probability"] = np.round(proba, 4)
ho["predicted_label"] = (proba >= 0.5).astype(int)
pq.write_table(pa.Table.from_pandas(ho, preserve_index=False), str(out_dir / "holdout_predictions.parquet"))
(out_dir / "selected_features.txt").write_text("\n".join(FEATURE_COLS) + "\n")

mean_auc = pd.DataFrame(records)["validation_auc"].mean()
audit = {
    "dropped_features": [
        {"name": "f04", "pdf_family": "Case closure classification", "reason": "PROHIBITED", "source": "support_tickets.resolution_code"},
        {"name": "f06", "pdf_family": "In-period billing settlement indicator", "reason": "NOT available at period open", "source": "invoices.paid_status"},
        {"name": "f07", "pdf_family": "Advance billing-cycle charge", "reason": "PROHIBITED", "source": "invoices.amount_usd"},
        {"name": "f09", "pdf_family": "Post-period ledger drift", "reason": "PROHIBITED", "source": "subscription_snapshots.mrr_usd"},
        {"name": "f10", "pdf_family": "Period-span ledger comparison", "reason": "PROHIBITED", "source": "subscription_snapshots.mrr_usd"},
        {"name": "f12", "pdf_family": "Rolling engagement signal (30-day)", "reason": "Removed duplicate aggregate module", "source": "product_events"},
        {"name": "f13", "pdf_family": "Case file volume (30-day rolling)", "reason": "Removed duplicate aggregate module", "source": "support_tickets"},
    ],
    "repaired_features": [
        {"name": "f02", "pdf_family": "Rolling engagement signal (30-day)", "reason": "Window ends strictly before period open", "source": "product_events.event_date"},
        {"name": "f08", "pdf_family": "Customer vitality score", "reason": "Capped at last day of prior billing period", "source": "customer_health_scores.score_date"},
        {"name": "f03", "pdf_family": "Case file volume (30-day rolling)", "reason": "Counts cases opened strictly before period open", "source": "support_tickets.ticket_created_at"},
        {"name": "f05", "pdf_family": "Prior billing-cycle settlement indicator", "reason": "Grace period and settlement timestamp enforced", "source": "invoices.due_date, invoices.paid_date"},
    ],
    "kept_features": ["f01", "f11"],
    "backtest_strategy": "Rolling temporal split from backtest_windows.csv",
    "holdout_month": "2026-04",
    "leakage_risk_summary": f"Removed PROHIBITED families and repaired f02/f03/f05/f08 boundaries. Mean AUC {mean_auc:.4f}.",
}
(out_dir / "leakage_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
TRAIN_EOF

python3 /root/project/train_model.py --config /root/project/config.yaml
