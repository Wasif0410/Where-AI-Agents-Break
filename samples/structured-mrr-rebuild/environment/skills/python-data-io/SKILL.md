---
name: python-data-io
description: Load and join structured billing data with pandas. Use when reading CSV and JSONL input files, parsing dates, and joining multiple sources before computing revenue metrics.
---

# Python Data I/O

Use Python and pandas for this task. All input files are under `/root/data`.

## File formats

- CSV files: use `pd.read_csv()`
- JSONL files (one JSON object per line): use `pd.read_json(..., lines=True)`

## Date handling

Parse date columns with `pd.to_datetime()` before extracting year-month strings. Use `strftime("%Y-%m")` to produce `YYYY-MM` formatted month labels.

## Joining sources

Join dataframes on shared keys using `DataFrame.merge()`. After joining, always check that expected columns are fully populated — missing join results indicate a schema or key mismatch.

## Checklist

- Validate required columns before calculations.
- Parse numeric fields explicitly; avoid relying on inferred types.
- Sort output rows by stable business keys.
- Check for and handle duplicate rows before aggregating.
