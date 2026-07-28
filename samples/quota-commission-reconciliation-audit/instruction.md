# Quota Commission Reconciliation Audit

The sales operations team needs an audit of Q1 2026 commission payouts for the account executive team. Finance has produced a draft commission statement that may contain errors. Your task is to compute the correct commission for each rep using the authoritative commission plan, compare against the draft, repair the draft audit workbook, and produce a structured audit report.

All input files are under `/root/data`:

- `rep_quotas.csv` — per-rep base quota targets for Q1 2026
- `quota_carryover.xlsx` — carryover quota allocations
- `bookings.jsonl` — Q1 2026 closed-won deals with ARR amounts
- `commission_plan.pdf` — authoritative commission plan defining tier thresholds, commission rates, carryover treatment, and stacking rules
- `draft_commission_statements.csv` — finance draft commission amounts to verify
- `draft_commission_audit.xlsx` — draft audit workbook that must be repaired

Create `/root/out` if it does not exist.

Produce exactly these files:

1. `/root/out/commission_audit_repaired.xlsx`
2. `/root/out/audit_summary.json`

Use `commission_plan.pdf` as the source of truth for tier thresholds, commission rates, carryover treatment, and the non-marginal accelerator stacking rule.

## Workbook repair requirement

Repair `/root/data/draft_commission_audit.xlsx` in place and save the repaired copy to `/root/out/commission_audit_repaired.xlsx`.

Do not create a new workbook from scratch.

The workbook contains a hidden `Control` sheet that defines the editable columns, formula-controlled columns, preservation-only columns, and the active rep row range for the `Commission Audit` sheet. Read this sheet before editing.

Only write to cells marked editable by the workbook's control metadata. Preserve formula-controlled cells as formulas and preservation-only cells unchanged.

The draft workbook may contain stale formulas, data validation ranges, filters, and helper ranges from a prior smaller audit cycle. Repair those ranges so they cover the full active rep range defined in the `Control` sheet.

The draft workbook may contain stale Excel table ranges, workbook-level named ranges, conditional formatting ranges, and incomplete formula-controlled columns from a prior smaller audit cycle. Repair these workbook objects so they cover the full active rep range defined in the hidden `Control` sheet. Preserve the workbook's formula-driven design; do not replace formulas with hardcoded values.

Do not replace Summary formulas with hardcoded values. Preserve hidden sheets, formulas, sheet order, data validation lists, frozen panes, styles, and number formats.

All editable numeric cells must be literal numeric values, not strings and not formulas.

For each rep present in the input sources, compute:
- Total quota (base plus carryover)
- Q1 bookings ARR from closed deals (parse all records in `bookings.jsonl`)
- Quota attainment
- Commission tier and commission amount
- Delta against the draft statement and discrepancy flag

Use `draft_commission_statements.csv` as the authoritative source for `draft_commission_usd`.

Rows on `Commission Audit` must remain sorted by `rep_id` ascending (REP-001 through REP-020).

- `attainment_pct` is a ratio (e.g., 1.05 for 105% attainment), not a percentage integer.
- `delta_usd = draft_commission_usd - commission_usd`
- `flag` is exactly one of: `OVERPAID`, `UNDERPAID`, `CORRECT`
  - `OVERPAID` if `delta_usd > 0.01`
  - `UNDERPAID` if `delta_usd < -0.01`
  - `CORRECT` if `|delta_usd| <= 0.01`
- `commission_tier` is exactly one of: `Below Threshold`, `Base`, `Accelerator 1`, `Accelerator 2`, `Accelerator 3`

**`audit_summary.json`** — keys:

`total_reps_audited, reps_with_discrepancy, total_overpaid_usd, total_underpaid_usd, tier_distribution, highest_delta_rep`

- `total_reps_audited`: count of reps in the audit; must match the row count on the `Commission Audit` sheet (20 rows)
- `reps_with_discrepancy`: count of reps where `flag` is not `CORRECT`
- `total_overpaid_usd`: sum of `delta_usd` for reps with `flag == "OVERPAID"`, rounded to 2 decimal places
- `total_underpaid_usd`: sum of `abs(delta_usd)` for reps with `flag == "UNDERPAID"`, rounded to 2 decimal places
- `highest_delta_rep`: rep with the largest absolute delta; ties broken by lowest `rep_id`
- `tier_distribution`: object mapping each allowed `commission_tier` string to its rep count; include every allowed tier label, using `0` when no reps are in that tier

All numeric values must be stored as numbers, not strings.
