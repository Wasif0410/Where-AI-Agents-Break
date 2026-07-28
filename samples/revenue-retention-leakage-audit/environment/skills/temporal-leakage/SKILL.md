---
name: temporal-leakage
description: Detect and remove temporal leakage in ML feature pipelines. Use when auditing feature generation code for time-based prediction tasks where features must only use data available at the prediction date.
---

# Temporal Leakage Detection

## What is Temporal Leakage?

Temporal leakage occurs when a feature for a prediction at date D uses information that was not yet available on date D. This inflates model performance in backtesting but collapses in production.

## Audit workflow

1. Read the feature availability document and list each permitted feature family with its timing rule.
2. Inspect every engineered column in the pipeline — names are not trustworthy.
3. For each column, trace which warehouse tables, fields, and date filters are used.
4. Map the column to exactly one PDF family and verify the SQL boundary matches the rule.
5. Remove PROHIBITED / NOT-available families entirely from both the feature matrix and pipeline source.
6. Repair conditional families whose date boundaries were wrong. Document repairs under `repaired_features` using the column name in the final model — even when that column differs from the leaky starter implementation.

## Common patterns to investigate

- Aggregates whose window extends past period open
- Ledger or billing fields from future cycles
- Outcome-correlated categorical fields finalized after period open
- One-to-many joins without prior aggregation

## Do not assume

- Column names reveal intent
- A column using a long window is automatically leaky (verify against the PDF)
- Multiple implementations of the same family can all be kept — pick one honest version and document boundary fixes in `repaired_features`, not `kept_features`
