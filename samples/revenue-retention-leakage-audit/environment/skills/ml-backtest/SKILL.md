---
name: ml-backtest
description: Build honest rolling time-series backtests for churn/retention models. Use when splitting training data for a temporal prediction task, constructing rolling windows, or evaluating model performance without leakage.
---

# ML Backtesting for Time-Series Prediction

## Why Random Split is Wrong

Shuffled train/validation splits on monthly prediction tasks introduce look-ahead bias and inflate AUC.

## Rolling Temporal Split

Each validation fold must train on months strictly before the validation month. Use the task's `backtest_windows.csv` when provided.

## Holdout Discipline

The holdout month must never appear in any training or validation fold. Final holdout predictions use a model trained on all other months.

## Suspicious Performance

Unusually high validation AUC on a low-signal churn task may indicate temporal leakage — re-audit feature boundaries even if the model runs without error.

## Honest Metrics

Report per-fold row counts, positive rate, and AUC for every window in the backtest specification.
