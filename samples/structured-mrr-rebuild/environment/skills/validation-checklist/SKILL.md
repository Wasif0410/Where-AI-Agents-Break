---
name: validation-checklist
description: Pre-submission checks for the MRR rebuild task. Use before finishing to verify output files exist and schemas match the instruction.
---

# Validation Checklist

Run these checks before finishing.

## File checks

- `/root/out/mrr_by_account.parquet` exists.
- `/root/out/mrr_summary.json` exists.
- `/root/out/monthly_summary.csv` exists.

## Schema checks

Confirm each output file has exactly the columns or keys defined in the task instruction — no extras, none missing.

Confirm the parquet grain is one row per `(account_id, month)` with no duplicate pairs.

## Sanity checks

If totals look implausible, re-read the instruction and trace a few accounts manually before resubmitting.
