# Revenue Retention Leakage Audit

The revenue analytics team built a model to predict which accounts will suffer at least $500 in MRR loss during the next 30 days. Validation AUC is suspiciously high relative to the customer signals that should exist at prediction time.

Audit the modelling codebase and warehouse-backed feature pipeline for temporal leakage. Repair or remove every feature that violates `feature_availability.pdf`, rebuild an honest rolling backtest, and produce April 2026 holdout predictions.

---

## Inputs

Under `/root/data`:

- `revenue_warehouse.sqlite`
- `feature_availability.pdf` — authoritative timing rules for feature families (not pipeline column names)
- `backtest_windows.csv` — rolling validation windows (`validate_month`, `train_end_month`); April 2026 is holdout and does not appear here
- `model_readme.md`

Under `/root/project`: the feature pipeline, training script, and `config.yaml`. Inspect every module — leakage may sit in helper layers, not only the entrypoint.

---

## Outputs (write to `/root/out`)

**`leakage_audit.json`**

```json
{
  "dropped_features": [
    {"name": "...", "pdf_family": "...", "reason": "...", "source": "..."}
  ],
  "repaired_features": [
    {"name": "...", "pdf_family": "...", "reason": "...", "source": "..."}
  ],
  "kept_features": ["..."],
  "backtest_strategy": "...",
  "holdout_month": "2026-04",
  "leakage_risk_summary": "..."
}
```

Document each dropped or repaired column with its PDF family, rationale, and warehouse fields involved.

Use these categories consistently:

- **Dropped** — removed because the PDF family is PROHIBITED or NOT available at period open.
- **Repaired** — kept in the final model, but the starter pipeline used the wrong date boundary, join, or settlement rule. Record the **column name actually used in the final model** (which may differ from the leaky starter column), cite the PDF family, and explain what was fixed.
- **Kept** — already honest in the starter code; no boundary logic changed.

If you swap in a different honest implementation of the same PDF family, document that column under `repaired_features`, not `kept_features`.

Prohibited and NOT-available families must disappear from the feature matrix **and** from `/root/project` source. The verifier reruns the patched pipeline and inspects project modules — unused queries, horizon-inclusive windows, and other leaky code paths still count as failure even if the exported feature list looks clean.

**`backtest_results.csv`** — columns `validate_month, n_train, n_val, n_positive, validation_auc`; one row per window in `backtest_windows.csv`; honest temporal training only.

**`holdout_predictions.parquet`** — columns `account_id, prediction_month, churn_probability, predicted_label`; all rows `prediction_month = "2026-04"`; probabilities in [0, 1]; labels 0/1 at threshold 0.5.

**`selected_features.txt`** — one honest feature name per line for the final model.

---

## Execution

Patched code must run end-to-end:

```
python3 /root/project/train_model.py --config /root/project/config.yaml
```

This must write all four output files to `/root/out/`.

---

## Notes

- `feature_availability.pdf` governs what may be used at period open. Map pipeline columns to PDF families by reading the code and warehouse schema — not by name alone.
- Holdout month `2026-04` must never appear in backtest training or validation folds.
- Grain: one row per (account, prediction_month).
- `selected_features.txt` must list exactly the columns your patched pipeline builds for training and holdout — not a hand-maintained list that drifts from the code.
