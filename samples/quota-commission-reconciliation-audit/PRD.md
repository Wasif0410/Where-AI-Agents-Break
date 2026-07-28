# PRD: `quota-commission-reconciliation-audit`

**Author:** Wasif Saeed  
**Status:** Ready for implementation  
**Harbor path:** `samples/quota-commission-reconciliation-audit/`

---

## 1. Overview

| Field | Value |
|---|---|
| **Task name** | `quota-commission-reconciliation-audit` |
| **Difficulty** | Hard |
| **Category** | `data-science` |
| **Tags** | `saas`, `revenue-analytics`, `sales-ops`, `commission-reconciliation`, `spreadsheet-repair` |

A SaaS company's sales operations team must audit Q1 2026 commission payouts for twenty account executives. Finance has produced a draft commission statement (`draft_commission_statements.csv`) that may contain errors. The agent reads quota targets, carryover allocations, and deal bookings from heterogeneous source files, applies the authoritative commission plan rules from `commission_plan.pdf`, computes correct attainment and payouts per rep, and writes a structured audit report flagging discrepancies between draft and correct values. The task is hard because three independent **input representation traps** — currency-formatted CSV strings, multi-sheet Excel formula cells (including cross-sheet lookups), and mixed-type JSONL currency fields — silently corrupt revenue and quota parsing; a single parsing mistake cascades across tier assignment, commission amounts, flags, and summary totals, producing 7+ verifier failures from one root cause.

---

## 2. Research Rationale

This task is designed using benchmark-validated failure patterns from Harbor task development (`TASK_BUILDING_GUIDE.md`), aligned with three external benchmark families:

| Benchmark family | Pattern borrowed | How this task applies it |
|---|---|---|
| **DABstep** (Data Agent Benchmark) | Multi-source heterogeneous ingestion → deterministic reconciliation output | Agent must fuse CSV (formatted strings), Excel (multi-sheet + cross-sheet formulas), JSONL (mixed numeric types), and PDF (policy rules) into one per-rep audit |
| **FinRule-Bench** | Authoritative financial policy document + numeric derivation | `commission_plan.pdf` defines tier thresholds, rates, carryover treatment, and non-marginal stacking; all commission math is derivable from policy + inputs |
| **Harbor `pricing-migration-rule-engine-audit` / `usage-billing-dispute-audit`** | Representation trap + cascade verifier | Excel formula cells and CSV string dtypes fail silently under naive `pandas` reads; one wrong quota poisons attainment → tier → commission → delta → flag → summary |

**Why these failure modes were chosen (not policy ambiguity):**

Per `TASK_BUILDING_GUIDE.md` Lessons 2–4 and 265–269: strong agents (Gemini 3.5 Flash) read policy PDFs completely and implement rules correctly. Difficulty must come from **data representation**, not from "read the policy more carefully." The Excel formula trap (Lesson 13) and multi-sheet default-read trap (Step 1 table) are empirically validated at ~30–40% pass@1. The CSV currency-string trap (Step 1 table) adds a second independent failure surface: agents that fix Excel may still fail CSV parsing, and vice versa.

**Why commission reconciliation specifically:**

- Sales-ops commission audits are a realistic FinRule-style domain: ratchet tiers, carryover denominators, and flat-rate-on-all-bookings stacking are common SaaS compensation patterns.
- The carryover Excel sheet mirrors real finance workbooks where Sheet 1 is a cover page and Sheet 2 holds computed allocations as formulas.
- Draft-vs-correct comparison gives unambiguous pass/fail signals without requiring the agent to know *which* reps are wrong upfront (fairness: agent discovers discrepancies by computation).

---

## 3. Failure Mode Analysis

### Trap A — CSV Currency Strings in `rep_quotas.csv`

**Symptom:** `base_quota_usd` column stores values like `"$145,000.00"` (dollar sign, comma thousands separator, `dtype=object`).

#### Code that fails

```python
import pandas as pd

df = pd.read_csv("/root/data/rep_quotas.csv")
print(df.dtypes)
# base_quota_usd    object

total = df["base_quota_usd"].sum()
# Returns string concatenation or NaN — NOT a number

# Partial fix — strips $ but not commas:
df["base_quota_usd"].str.replace("$", "", regex=False).astype(float)
# ValueError: could not convert string to float: '145,000.00'

# Naive float on single value:
float("$145,000.00")
# ValueError

# Silent skip pattern agents use:
df["base_quota_usd"] = pd.to_numeric(df["base_quota_usd"], errors="coerce")
# All values become NaN → carryover-only quota or zero quota
```

#### Why it fails

1. `pd.read_csv()` does not infer currency formatting; strings stay `object`.
2. Stripping `$` alone leaves comma separators, which Python `float()` rejects.
3. `errors="coerce"` silently converts all values to `NaN`, which agents often treat as "no quota."
4. The column name `base_quota_usd` looks numeric; agents skip dtype inspection.

#### Full fix

```python
def parse_currency(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .astype(float)
    )
```

**Order matters:** remove `$` first, then `,`, then cast to float.

---

### Trap B — Multi-Sheet Excel + Cross-Sheet Formula Cells in `quota_carryover.xlsx`

**Symptom:** Workbook has four sheets (`Cover`, `RateTable`, `Allocations`, `BaseRef`). Carryover amounts live on `Allocations` as Excel formulas with cross-sheet `VLOOKUP` references; formula cells have no cached values.

#### Code that fails

```python
import pandas as pd

# Failure 1: reads wrong sheet (default sheet 0 = Cover)
df = pd.read_excel("/root/data/quota_carryover.xlsx")
# No carryover_quota_usd column with numeric data

# Failure 2: correct Allocations sheet, but formulas return NaN
df = pd.read_excel("/root/data/quota_carryover.xlsx", sheet_name="Allocations")
print(df["carryover_quota_usd"].tolist())
# [nan, nan, ...] — pd.read_excel() cannot evaluate VLOOKUP/ROUND/MAX without cached values

# Failure 3: naive eval on formula string
val = "=ROUND(VLOOKUP(A2,RateTable!$A$2:$B$21,2,FALSE)*VLOOKUP(A2,BaseRef!$A$2:$B$21,2,FALSE),-3)"
eval(val.lstrip("="))
# SyntaxError / NameError — VLOOKUP and sheet references are not Python
```

#### Why it fails

1. `pd.read_excel()` defaults to `sheet_name=0` → Cover sheet with narrative text only.
2. Even on `Allocations`, `carryover_quota_usd` cells contain formulas referencing `RateTable` and `BaseRef`, not literal numbers.
3. Without cached values at save time, openpyxl/pandas return `NaN`.
4. Formulas use `VLOOKUP(rep_id, ...)` — agent must inspect workbook structure and resolve lookups from referenced sheets.
5. REP-012 uses `MAX(..., 5000)` instead of `ROUND(..., -3)` — requires recognizing the alternate formula pattern.

#### Oracle approach (not agent-visible)

The oracle inspects formula cells on the allocations sheet, resolves `VLOOKUP` inputs from `RateTable` and `BaseRef` by `rep_id`, then applies `ROUND(..., -3)` or `MAX(..., 5000)`. Formulas are simple and fully derivable from literal values on referenced sheets — no Excel formula engine required.

**Note for `solve.sh`:** Inside a `'''...'''` heredoc, avoid `r'\bMAX\b'` — `\b` becomes backspace. Use `.replace("MAX(", "max(")` instead.

---

### Trap C — Mixed-Type `arr_usd` in `bookings.jsonl`

**Symptom:** Most deals store `arr_usd` as a JSON number, but a subset use formatted currency strings like `"$35,000.00"`.

#### Code that fails

```python
import json

total = 0.0
with open("/root/data/bookings.jsonl") as f:
    for line in f:
        row = json.loads(line)
        total += row["arr_usd"]  # TypeError on string rows
```

#### Why it fails

1. `json.loads()` preserves per-row types — mixed float and string in the same field.
2. Naive `sum()` or `pd.read_json(lines=True)` may coerce strings to NaN or skip rows.
3. One wrong booking total poisons attainment → tier → commission → flag → summary.

#### Full fix

Normalize each `arr_usd` value to float before aggregating (same currency parsing as Trap A).

---

## 4. Cascade Design

A single carryover parsing failure (Trap B: all carryover = 0) poisons the entire downstream chain. Example: **REP-007 (Aisha Khan)**.

| Step | Correct value | Wrong value (carryover = 0) | Test that fails |
|---|---|---|---|
| 1. `carryover_quota_usd` | 16,000 | 0 | `TestQuotaValues.test_carryover_nonzero` (if ALL reps = 0) + per-rep carryover |
| 2. `total_quota_usd` | 176,000 | 160,000 | `TestQuotaValues.test_total_quota` |
| 3. `attainment_pct` | 1.1000 | 1.2100 | `TestAttainmentAndTiers.test_attainment` |
| 4. `commission_tier` | Accelerator 1 | Accelerator 2 | `TestAttainmentAndTiers.test_commission_tier` |
| 5. `commission_usd` | 19,360.00 | 23,232.00 | `TestCommissionAmounts.test_commission_usd` |
| 6. `delta_usd` | -560.00 | -2,432.00 | `TestCommissionAmounts.test_delta_usd` |
| 7. `flag` | UNDERPAID | UNDERPAID (still, but wrong delta) | `TestCommissionAmounts.test_flag` (if delta sign changes on other reps) |
| 8. `audit_summary.total_underpaid_usd` | 560.00 | 2,432.00+ | `TestAuditSummary.test_total_underpaid` |
| 9. `audit_summary.highest_delta_rep` | REP-007 | may shift to REP-005 | `TestAuditSummary.test_highest_delta_rep` |
| 10. `audit_summary.tier_distribution` | Acc1: 2 | Acc1: 1, Acc2: 2 | `TestAuditSummary.test_tier_distribution` |

**Minimum cascade from one root cause: 7+ independent test failures** across `TestQuotaValues`, `TestAttainmentAndTiers`, `TestCommissionAmounts`, and `TestAuditSummary`.

Additional cascade examples if Trap A also fails (base quota = NaN → 0):

| Rep | Effect |
|---|---|
| REP-005 | Attainment explodes → tier may flip to Accelerator 3 (15% vs 12%) → $9,315 commission error |
| REP-006 | Attainment rises from 75% to 84.4% → tier flips Below Threshold → Base → $2,700 commission instead of $0 |
| REP-002 | Attainment rises from 70% to 75.8% → still Below Threshold but wrong attainment_pct |

**Anti-naive tests reinforce cascade:**

- `test_carryover_nonzero`: fails if agent read Sheet 1 or skipped formula cells (all carryover = 0).
- `test_not_all_below_threshold`: fails if quotas are so wrong that every rep lands Below Threshold.

---

## 5. Input File Specifications

### Summary table

| File | Format | Rows | Trap | Agent-visible source for |
|---|---|---|---|---|
| `rep_quotas.csv` | CSV | 20 reps | **Trap A** | `base_quota_usd` per rep |
| `quota_carryover.xlsx` | Excel, 4 sheets | 20 reps on Allocations | **Trap B** | `carryover_quota_usd` per rep |
| `bookings.jsonl` | JSONL | ~80 deals | **Trap C** | `bookings_arr_usd` per rep |
| `commission_plan.pdf` | PDF | 1 page | None | Tier rules, rates, carryover treatment, stacking |
| `draft_commission_statements.csv` | CSV | 20 reps | None (intentional draft errors) | `draft_commission_usd` per rep |

All files are written to `/root/data/` by `build_inputs.py` at Docker build time.

---

### 5.1 `rep_quotas.csv`

| Column | Type in file | Type after parsing | Example | Notes |
|---|---|---|---|---|
| `rep_id` | string | string | `REP-001` | Primary key |
| `rep_name` | string | string | `Jordan Ellis` | Display only |
| `region` | string | string | `NA-East` | Display only |
| `base_quota_usd` | **string** (currency) | float | `"$145,000.00"` → `145000.00` | **Trap A** |

**20 reps (REP-001 through REP-020).** All `base_quota_usd` values are currency-formatted strings. Full rep list and quotas: `REPS` constant in `environment/data/build_inputs.py`.

---

### 5.2 `quota_carryover.xlsx`

**Sheet 1 — "Cover"** (default read target; no numeric carryover data):

| Content |
|---|
| Title: "Q1 2026 Quota Carryover Allocation" |
| Subtitle: "Prepared by Sales Operations — Internal Use Only" |
| Body text explaining carryover policy at a high level (no numeric allocations) |
| Note: "Per-rep carryover amounts are computed in this workbook." |

**Sheet 2 — "RateTable"** — lookup table: `rep_id`, `carry_rate` (numeric literals).

**Sheet 3 — "Allocations"** (actual carryover output):

| Column | Type in file | Example | Notes |
|---|---|---|---|
| `rep_id` | string | `REP-001` | |
| `carryover_quota_usd` | **Excel formula** | `=ROUND(VLOOKUP(A2,RateTable!$A$2:$B$21,2,FALSE)*VLOOKUP(A2,BaseRef!$A$2:$B$21,2,FALSE),-3)` | **Trap B** |

**Sheet 4 — "BaseRef"** — lookup table: `rep_id`, `base_quota_usd` (numeric literals).

**Formula trap tiers:**
- REP-001 through REP-011, REP-013 through REP-020: `ROUND(VLOOKUP(...) * VLOOKUP(...), -3)`.
- REP-012: `MAX(VLOOKUP(...) * VLOOKUP(...), 5000)` — floor carryover at 5,000.

**Canonical evaluated carryover values:** see `tests/test_outputs.py` `EXPECTED` dict (20 reps). REP-008 and REP-020 have `carry_rate = 0` → carryover 0.

**Build requirement:** Save workbook with `data_only=False` and **no cached formula results** so `pd.read_excel()` returns `NaN` for formula cells.

---

### 5.3 `bookings.jsonl`

~80 JSON objects, one per line. All `close_date` values in Q1 2026 (2026-01-01 through 2026-03-31). Most `arr_usd` values are JSON floats; **Trap C:** four deals use formatted currency strings (e.g. `"$35,000.00"`). See `STRING_ARR_DEALS` in `build_inputs.py`.

| Field | Type | Example |
|---|---|---|
| `rep_id` | string | `REP-001` |
| `deal_id` | string | `D-001-01` |
| `close_date` | string (ISO date) | `2026-01-15` |
| `arr_usd` | float or string | `42000.0` or `"$35,000.00"` | **Trap C** on 4 deals |

**~80 deals across 20 reps.** Full deal list: `DEALS` and `STRING_ARR_DEALS` in `build_inputs.py`. Per-rep booking targets: `BOOKINGS_TARGET` in `build_inputs.py` (canonical values also in `tests/test_outputs.py` `EXPECTED`).

---

### 5.4 `commission_plan.pdf`

Single-page authoritative policy document generated by `reportlab` in `build_inputs.py`. Contains business context, tier definitions, rates, carryover rule, stacking rule, and flag semantics. **Output schemas are in `instruction.md`, not the PDF.** No worked examples (per task design — agent must implement, not transcribe).

See **Section 7** for full PDF text content.

---

### 5.5 `draft_commission_statements.csv`

Finance draft with intentional errors in **4 of 20 reps** (agent must discover which by computation).

| Column | Type | Notes |
|---|---|---|
| `rep_id` | string | |
| `draft_commission_usd` | float | Clean numeric (no Trap A) |

**Intentional discrepancies (not agent-visible):**

| rep_id | Error type | delta_usd |
|---|---|---|
| REP-001 | Overpaid | +400.00 |
| REP-003 | Overpaid | +505.00 |
| REP-007 | Underpaid | -560.00 |
| REP-012 | Overpaid | +580.00 |

All other reps: draft matches computed commission. Full draft values: `DRAFT_COMMISSIONS` in `build_inputs.py`.

---

## 6. Output File Specifications

Create `/root/out/` if it does not exist. Produce exactly two files.

### 6.1 `/root/out/commission_audit.csv`

**One row per rep (20 rows). Sorted by `rep_id` ascending.**

| Column | Type | Description |
|---|---|---|
| `rep_id` | string | |
| `base_quota_usd` | float | Parsed from `rep_quotas.csv` |
| `carryover_quota_usd` | float | Evaluated from `quota_carryover.xlsx` Allocations sheet (Trap B) |
| `total_quota_usd` | float | `base_quota_usd + carryover_quota_usd` |
| `bookings_arr_usd` | float | Sum of `arr_usd` from `bookings.jsonl` for rep |
| `attainment_pct` | float | `bookings_arr_usd / total_quota_usd` (ratio, not ×100) |
| `commission_tier` | string | Exactly one allowed label (see below) |
| `commission_usd` | float | `bookings_arr_usd × tier_rate` |
| `draft_commission_usd` | float | From `draft_commission_statements.csv` |
| `delta_usd` | float | `draft_commission_usd - commission_usd` |
| `flag` | string | `OVERPAID`, `UNDERPAID`, or `CORRECT` |

**Allowed `commission_tier` values (exact strings, case-sensitive):**

- `Below Threshold`
- `Base`
- `Accelerator 1`
- `Accelerator 2`
- `Accelerator 3`

**Allowed `flag` values:**

- `OVERPAID` — `delta_usd > 0.01`
- `UNDERPAID` — `delta_usd < -0.01`
- `CORRECT` — `|delta_usd| ≤ 0.01`

**Numeric precision:**

- Money columns: full float precision acceptable; verifier uses `MONEY_TOL = 0.01`.
- `attainment_pct`: ratio format (e.g., `1.05` for 105%); verifier uses `SHARE_TOL = 0.0005`.
- All numeric columns must be numeric dtypes, not strings.

**Column order (exact):**

```
rep_id, base_quota_usd, carryover_quota_usd, total_quota_usd,
bookings_arr_usd, attainment_pct, commission_tier,
commission_usd, draft_commission_usd, delta_usd, flag
```

---

### 6.2 `/root/out/audit_summary.json`

```json
{
  "total_reps_audited": 20,
  "reps_with_discrepancy": 4,
  "total_overpaid_usd": 1485.00,
  "total_underpaid_usd": 560.00,
  "tier_distribution": {
    "Below Threshold": 5,
    "Base": 5,
    "Accelerator 1": 4,
    "Accelerator 2": 3,
    "Accelerator 3": 3
  },
  "highest_delta_rep": "REP-012"
}
```

| Key | Type | Rule |
|---|---|---|
| `total_reps_audited` | int | Count of reps in audit (= 20) |
| `reps_with_discrepancy` | int | Count where `flag != "CORRECT"` |
| `total_overpaid_usd` | float | Sum of `delta_usd` where `flag == "OVERPAID"`; round to 2 dp |
| `total_underpaid_usd` | float | Sum of `abs(delta_usd)` where `flag == "UNDERPAID"`; round to 2 dp |
| `tier_distribution` | object | Count per tier label; keys must match allowed tier strings exactly |
| `highest_delta_rep` | string | `rep_id` with largest `abs(delta_usd)`; ties broken by lowest `rep_id` |

---

## 7. Commission Plan Rules

Full text to embed in `commission_plan.pdf`:

---

**Abundant Cloud Platform — Q1 2026 AE Commission Plan**

Effective period: January 1, 2026 – March 31, 2026  
Audience: Account Executive commission audit

### Plan overview

Account Executives earn quarterly commission on New ARR booked during the period. Commission is determined by quota attainment against a total quota that includes any approved carryover allocation from the prior period.

### Quota components

- **Base quota:** The rep's assigned Q1 2026 target, sourced from `rep_quotas.csv`.
- **Carryover quota:** Additional quota credit allocated per rep, sourced from `quota_carryover.xlsx`.
- Commission workbook formula values should be interpreted using standard Excel formula semantics.
- **Total quota:** `total_quota_usd = base_quota_usd + carryover_quota_usd`

Carryover amounts add to the quota denominator. They do not count as bookings.

### Attainment

```
attainment_pct = bookings_arr_usd / total_quota_usd
```

where `bookings_arr_usd` is the sum of `arr_usd` for all deals closed in Q1 2026 for that rep in `bookings.jsonl`.

### Commission tiers (ratchet schedule)

Commission tier is determined by `attainment_pct` using these thresholds:

| Tier name | Attainment range | Commission rate |
|---|---|---|
| Below Threshold | attainment < 80% | 0% |
| Base | 80% ≤ attainment < 100% | 8% |
| Accelerator 1 | 100% ≤ attainment < 120% | 10% |
| Accelerator 2 | 120% ≤ attainment < 150% | 12% |
| Accelerator 3 | attainment ≥ 150% | 15% |

Boundary behavior: inclusive on the lower bound, exclusive on the upper bound (e.g., exactly 100% → Accelerator 1; exactly 120% → Accelerator 2).

### Accelerator stacking rule (non-marginal)

The commission rate for the tier reached applies to **all** Q1 bookings for that rep — not marginally by tier band.

```
commission_usd = bookings_arr_usd × commission_rate
```

### Audit comparison

Compare computed `commission_usd` against `draft_commission_usd` from `draft_commission_statements.csv`.

```
delta_usd = draft_commission_usd - commission_usd
```

Flag rules:
- `OVERPAID` if `delta_usd > 0.01`
- `UNDERPAID` if `delta_usd < -0.01`
- `CORRECT` if `|delta_usd| <= 0.01`

Output schemas and allowed string values are defined in `instruction.md` (not embedded in the PDF).

---

## 8. Folder Structure

```
samples/quota-commission-reconciliation-audit/
├── instruction.md
├── task.toml
├── PRD.md                          # this document
├── environment/
│   ├── Dockerfile
│   ├── data/
│   │   └── build_inputs.py
│   └── skills/
│       └── spreadsheet-input-guidance/
│           └── SKILL.md
├── tests/
│   ├── test.sh
│   └── test_outputs.py
└── solution/
    └── solve.sh
```

**`tests/test.sh` responsibilities:**

1. **Do not** wipe `/root/out` — this is an output-file task; the agent must produce files before the verifier runs. Nop fails because outputs are absent; Oracle passes because `solve.sh` writes them.
2. Install pytest + dependencies
3. Run `pytest /tests/test_outputs.py`
4. Write `reward.txt` (1 = pass, 0 = fail)

**Docker build:** creates `/root/data` only. `/root/out` is never pre-populated. Solution outputs are not copied into the image.

---

## 9. task.toml

```toml
version = "1.0"

[metadata]
author_name = "Wasif Saeed"
author_email = ""
difficulty = "hard"
category = "data-science"
tags = ["saas", "revenue-analytics", "sales-ops", "commission-reconciliation", "spreadsheet-repair"]

[verifier]
timeout_sec = 300.0

[agent]
timeout_sec = 600.0

[environment]
build_timeout_sec = 600.0
cpus = 1
memory_mb = 4096
storage_mb = 10240

[environment.env]
GEMINI_CLI_TRUST_WORKSPACE = "true"
```

---

## 10. Dockerfile

```dockerfile
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages \
    pandas==2.2.3 numpy==2.1.3 openpyxl==3.1.5 \
    pytest==8.4.1 pytest-json-ctrf==0.3.5 \
    reportlab==4.2.5 pdfplumber==0.11.4

WORKDIR /root

COPY data /tmp/task-data
RUN mkdir -p /root/data && python3 /tmp/task-data/build_inputs.py

# Claude Code
COPY skills /root/.claude/skills
# Codex
COPY skills /root/.codex/skills
# OpenCode
COPY skills /root/.opencode/skill
# Goose
COPY skills /root/.goose/skills
# Factory
COPY skills /root/.factory/skills
# Portable agents format
COPY skills /root/.agents/skills
# GitHub Copilot
COPY skills /root/.github/skills
# Gemini
COPY skills /root/.gemini/skills
```

---

## 11. instruction.md Spec

Full draft of `instruction.md`:

```markdown
# Quota Commission Reconciliation Audit

The sales operations team needs an audit of Q1 2026 commission payouts for the account executive team. Finance has produced a draft commission statement that may contain errors. Your task is to compute the correct commission for each rep using the authoritative commission plan, compare against the draft, and produce a structured audit report.

All input files are under `/root/data`:

- `rep_quotas.csv` — per-rep base quota targets for Q1 2026
- `quota_carryover.xlsx` — carryover quota allocations (may span multiple sheets)
- `bookings.jsonl` — Q1 2026 closed-won deals with ARR amounts
- `commission_plan.pdf` — authoritative commission plan defining tier thresholds, commission rates, carryover treatment, stacking rules, and output schemas
- `draft_commission_statements.csv` — finance draft commission amounts to verify

Create `/root/out` if it does not exist.

Produce exactly these files:

1. `/root/out/commission_audit.csv`
2. `/root/out/audit_summary.json`

Use `commission_plan.pdf` as the source of truth for tier thresholds, commission rates, carryover treatment, the non-marginal accelerator stacking rule, output column names, JSON keys, and allowed string values for `commission_tier` and `flag`.

For each rep, compute:
- Total quota (base plus carryover)
- Q1 bookings ARR from closed deals
- Quota attainment
- Commission tier and commission amount
- Delta against the draft statement and discrepancy flag

**`commission_audit.csv`** — one row per rep, sorted by `rep_id`, columns:

`rep_id, base_quota_usd, carryover_quota_usd, total_quota_usd, bookings_arr_usd, attainment_pct, commission_tier, commission_usd, draft_commission_usd, delta_usd, flag`

- `attainment_pct` is a ratio (e.g., 1.05 for 105% attainment), not a percentage integer.
- `delta_usd = draft_commission_usd - commission_usd`
- `flag` is exactly one of: `OVERPAID`, `UNDERPAID`, `CORRECT`
- `commission_tier` is exactly one of: `Below Threshold`, `Base`, `Accelerator 1`, `Accelerator 2`, `Accelerator 3`

**`audit_summary.json`** — keys:

`total_reps_audited, reps_with_discrepancy, total_overpaid_usd, total_underpaid_usd, tier_distribution, highest_delta_rep`

- `total_overpaid_usd`: sum of positive deltas for overpaid reps, rounded to 2 decimal places
- `total_underpaid_usd`: sum of absolute deltas for underpaid reps, rounded to 2 decimal places
- `highest_delta_rep`: rep with the largest absolute delta
- `tier_distribution`: count of reps in each commission tier

All numeric values must be stored as numbers, not strings. CSV files must contain only the requested columns.
```

---

## 12. build_inputs.py Spec

**Canonical implementation:** `environment/data/build_inputs.py` (do not duplicate here — it changes with the task).

### What it generates (20 reps)

| Output file | Trap | Notes |
|---|---|---|
| `rep_quotas.csv` | **Trap A** | 20 reps; `base_quota_usd` as currency strings |
| `quota_carryover.xlsx` | **Trap B** | 4 sheets: Cover, RateTable, Allocations (VLOOKUP formulas), BaseRef |
| `bookings.jsonl` | **Trap C** | ~80 deals; 4 deals use string `arr_usd` |
| `commission_plan.pdf` | — | Policy only (tiers, rates, stacking, flag semantics) |
| `draft_commission_statements.csv` | — | 20 reps; 4 intentional draft errors |

### Key constants in `build_inputs.py`

- `REPS` — 20 rep master records (`formula`: `"ROUND"` or `"MAX"` for REP-012 only)
- `DEALS` / `STRING_ARR_DEALS` / `BOOKINGS_TARGET` — booking data
- `DRAFT_COMMISSIONS` — draft values with errors on REP-001, REP-003, REP-007, REP-012

### Expected verifier values

**Do not maintain duplicate tables in this PRD.** Canonical expected outputs:

- Per-rep audit rows: `tests/test_outputs.py` → `EXPECTED` (20 reps)
- Summary totals: `tests/test_outputs.py` → `EXPECTED_SUMMARY`

```python
EXPECTED_SUMMARY = {
    "total_reps_audited": 20,
    "reps_with_discrepancy": 4,
    "total_overpaid_usd": 1485.00,   # 400 + 505 + 580
    "total_underpaid_usd": 560.00,
    "tier_distribution": {
        "Below Threshold": 5, "Base": 5,
        "Accelerator 1": 4, "Accelerator 2": 3, "Accelerator 3": 3,
    },
    "highest_delta_rep": "REP-012",
}
```

---

## 13. test_outputs.py Spec

**Canonical implementation:** `tests/test_outputs.py`

### Constants

- `EXPECTED` — 20 reps (REP-001 through REP-020)
- `EXPECTED_SUMMARY` — `total_reps_audited: 20`, `reps_with_discrepancy: 4`, `highest_delta_rep: "REP-012"`
- `MONEY_TOL = 0.01`, `SHARE_TOL = 0.0005`

### Test classes

| Class | Key assertions |
|---|---|
| `TestOutputFilesExist` | Both output files exist under `/root/out` |
| `TestCommissionAuditSchema` | 11 columns in order; **20 rows**; sorted by `rep_id`; **numeric dtypes** on all 8 money/ratio columns; allowed tier/flag strings |
| `TestQuotaValues` | Per-rep base/carryover/total quota; anti-naive `carryover_nonzero` |
| `TestAttainmentAndTiers` | Per-rep attainment/tier; anti-naive `not_all_below_threshold` |
| `TestCommissionAmounts` | Per-rep commission, delta, flag |
| `TestAuditSummary` | All 6 JSON keys; summary totals match `EXPECTED_SUMMARY` |
| `TestAntiNaive` | REP-012 MAX carryover = 5000; REP-008 and REP-020 zero carryover preserved |

### Numeric dtype enforcement

`TestCommissionAuditSchema.test_numeric_dtypes` rejects text columns — if an agent writes `"145000.00"` as strings, `pd.read_csv` loads `dtype=object` and the test fails. Columns checked:

`base_quota_usd`, `carryover_quota_usd`, `total_quota_usd`, `bookings_arr_usd`, `attainment_pct`, `commission_usd`, `draft_commission_usd`, `delta_usd`

**No `/root/out` wipe in tests** — verifier reads agent-produced outputs as-is (matches `test.sh`).

---

## 14. solve.sh Spec

**Canonical implementation:** `solution/solve.sh`

Oracle handles all three traps:

1. **Trap A** — parse currency strings from `rep_quotas.csv`
2. **Trap B** — find Allocations sheet by header; resolve VLOOKUP inputs from `RateTable` and `BaseRef` by `rep_id`; apply `ROUND(..., -3)` or `MAX(..., 5000)`
3. **Trap C** — normalize mixed `arr_usd` types in `bookings.jsonl` before summing

Then applies tier rules from PDF, writes both output files, ensures all five tier keys in `tier_distribution`.

**Oracle validation sequence:**

```bash
harbor run -p samples/quota-commission-reconciliation-audit -a oracle   # reward 1
harbor run -p samples/quota-commission-reconciliation-audit -a nop      # reward 0
```

---

## 15. SKILL.md Spec

**Canonical implementation:** `environment/skills/spreadsheet-input-guidance/SKILL.md`

Covers general methodology only — no trap recipes, field names, or sheet names:

- `object` dtype may indicate display-formatted numeric strings (CSV)
- Multi-sheet Excel workbooks (data may not be on sheet 0)
- Excel formula cells (NaN may mean misread, not empty)
- Semi-structured records — inspect raw values before aggregation
- Numeric type verification (outputs must be numeric, not text)
- `scripts/inspect_workbook.py` helper

---

## 16. Fairness Audit

Checklist: every verifier constant must be derivable from agent-visible sources.

| Verifier constant | Agent-visible source | Derivable? |
|---|---|---|
| Output path `/root/out/commission_audit.csv` | `instruction.md` | ✅ |
| Output path `/root/out/audit_summary.json` | `instruction.md` | ✅ |
| Column names (11 columns) | `instruction.md` | ✅ |
| JSON keys (6 keys) | `instruction.md` | ✅ |
| `commission_tier` allowed strings (5) | `instruction.md` + `commission_plan.pdf` | ✅ |
| `flag` allowed strings (3) + ±0.01 tolerance | `instruction.md` + `commission_plan.pdf` | ✅ |
| Numeric dtypes in CSV output | `instruction.md` | ✅ |
| `tier_distribution` all 5 keys required | `instruction.md` | ✅ |
| Tier thresholds (80/100/120/150%) | `commission_plan.pdf` | ✅ |
| Commission rates (0/8/10/12/15%) | `commission_plan.pdf` | ✅ |
| Non-marginal stacking rule | `commission_plan.pdf` | ✅ |
| Carryover adds to denominator | `commission_plan.pdf` | ✅ |
| `delta_usd = draft - commission` | `commission_plan.pdf` | ✅ |
| `attainment_pct` as ratio | `instruction.md` | ✅ |
| Sort by `rep_id` | `instruction.md` | ✅ |
| `base_quota_usd` per rep | `rep_quotas.csv` (after Trap A fix) | ✅ |
| `carryover_quota_usd` per rep | `quota_carryover.xlsx` Allocations sheet (after Trap B fix) | ✅ |
| `bookings_arr_usd` per rep | `bookings.jsonl` (sum arr_usd after Trap C fix) | ✅ |
| `draft_commission_usd` per rep | `draft_commission_statements.csv` | ✅ |
| Expected commission_usd per rep | Derived: bookings × rate from PDF tiers | ✅ |
| Expected flags (4 discrepancies) | Derived: draft vs computed | ✅ |
| `total_reps_audited = 20` | Count of reps in input files | ✅ |
| `reps_with_discrepancy = 4` | Derived from flags | ✅ |
| `total_overpaid_usd = 1485.00` | Derived from OVERPAID deltas | ✅ |
| `total_underpaid_usd = 560.00` | Derived from UNDERPAID deltas | ✅ |
| `tier_distribution` counts | Derived from tier assignments | ✅ |
| `highest_delta_rep = REP-012` | Derived from max abs(delta) | ✅ |
| `MONEY_TOL = 0.01` | Standard rounding tolerance (verifier-only constant) | ✅ (implicit) |
| `SHARE_TOL = 0.0005` | Standard ratio tolerance (verifier-only) | ✅ (implicit) |
| Anti-naive: carryover nonzero | `quota_carryover.xlsx` has nonzero carryover | ✅ (hint in skill + Cover sheet text) |
| Anti-naive: not all Below Threshold | Attainments span tiers when quotas parsed correctly | ✅ (derived) |
| Anti-naive: REP-012 MAX formula | Carryover floor at 5000 | ✅ (derived from formula inspection) |
| No pre-built `/root/out` in image | Docker build creates `/root/data` only; Nop reward = 0 | ✅ |

**Not in agent-visible sources (intentionally withheld — fairness OK):**

- Which specific 4 reps have draft errors (agent must discover via computation)
- Exact expected numeric outputs (agent must compute)
- That REP-012 uses MAX formula specifically (agent must inspect cells)
- Sheet names in `quota_carryover.xlsx` (agent must discover workbook structure)

**Fairness violations to avoid during implementation:**

- Do NOT hardcode expected commission values in `instruction.md` or skills.
- Do NOT name discrepancy reps in any agent-visible file.
- Do NOT put step-by-step parsing code in skills (hints only).

---

## 17. Verifier Taxonomy Completeness

**Canonical counts:** `EXPECTED` and `EXPECTED_SUMMARY` in `tests/test_outputs.py`

### Commission tiers — all 5 covered (20 reps)

| Tier | Count |
|---|---|
| Below Threshold | 5 |
| Base | 5 |
| Accelerator 1 | 4 |
| Accelerator 2 | 3 |
| Accelerator 3 | 3 |

### Flag types — all 3 covered

| Flag | Count | Discrepancy reps |
|---|---|---|
| CORRECT | 16 | — |
| OVERPAID | 3 | REP-001 (+400), REP-003 (+505), REP-012 (+580) |
| UNDERPAID | 1 | REP-007 (-560) |

### Input trap coverage

| Trap | What it tests |
|---|---|
| **Trap A** (CSV currency strings) | `base_quota_usd` parsing from `rep_quotas.csv` |
| **Trap B** (Excel multi-sheet + VLOOKUP formulas) | `carryover_quota_usd` from `quota_carryover.xlsx` |
| **Trap C** (JSONL mixed `arr_usd`) | `bookings_arr_usd` aggregation from `bookings.jsonl` |

### Formula trap tiers

| Formula type | Reps | Validates |
|---|---|---|
| `ROUND(VLOOKUP*VLOOKUP, -3)` | 19 reps | Cross-sheet lookup + rounding |
| `MAX(VLOOKUP*VLOOKUP, 5000)` | REP-012 only | Excel MAX floor at 5,000 |

### Boundary coverage

| Boundary | Tested? | Notes |
|---|---|---|
| All 5 tier bands | ✅ | Spread across 20 reps |
| Zero carryover | ✅ | REP-008, REP-020 (`carry_rate = 0`) |
| Zero commission | ✅ | Multiple Below Threshold reps |
| 4 draft discrepancies | ✅ | 3 overpaid + 1 underpaid |

---

## 18. Expected Difficulty and Pass@1 Estimate

### Difficulty rating: **Hard**

**Reasoning:**

| Factor | Assessment |
|---|---|
| Independent traps | 3 (CSV currency + Excel VLOOKUP/formulas + JSONL mixed types) — partial fixes still fail |
| Policy complexity | Moderate — 5-tier ratchet with non-marginal stacking; PDF-readable by strong models |
| Data volume | Moderate (20 reps, ~80 deals) — too large to eyeball; traps must be representation-based |
| Output complexity | Moderate — 2 files, 11 columns, 6 JSON keys |
| Cascade depth | High — 7+ test failures from one parsing error |
| Skill reliance | Low for Gemini (ignores skills); traps are in data layer |

### Pass@1 estimate: **25–40%** for Gemini 3.5 Flash (`terminus-2`)

**Supporting evidence from `TASK_BUILDING_GUIDE.md`:**

- Lesson 13: Excel formula trap alone → ~40-50% pass@1.
- Cross-sheet VLOOKUP formulas are harder than single-sheet cell references.
- Lesson 14: `MAX()` formula on REP-012 lowers pass rate further.
- Three independent traps: fixing two of three still fails verifier.

**Trial outcome scenarios:**

| Agent behavior | Result |
|---|---|
| Reads Cover sheet only; parses CSV correctly | carryover = 0 → cascade across quota, tier, commission, summary |
| Resolves Excel but skips JSONL string deals | bookings sum wrong for 4 reps → tier/commission failures |
| Strips `$` but not `,` from CSV | base quota NaN → cascade across all reps |
| Evaluates ROUND VLOOKUP but misses MAX on REP-012 | carryover 4000 not 5000 → tier/commission/summary failures |
| Full fix of all three traps | All tests pass |

**Recommended validation protocol:**

```bash
# 1. Oracle must pass
harbor run -p samples/quota-commission-reconciliation-audit -a oracle

# 2. Nop must fail
harbor run -p samples/quota-commission-reconciliation-audit -a nop

# 3. Three Gemini trials before locking difficulty
harbor run -p samples/quota-commission-reconciliation-audit -a terminus-2 -m gemini/gemini-3.5-flash
```

**Acceptance criteria:**

- Oracle reward = 1.0
- Nop reward = 0.0
- Gemini pass@1 ∈ [0.25, 0.45] across 3 trials (if outside range, adjust formula complexity or add second MAX rep)

---

## Appendix: tests/test.sh

```bash
#!/bin/bash
# Does NOT wipe /root/out — agent must produce outputs before verifier runs.

pip3 install --break-system-packages \
  pytest==8.4.1 pytest-json-ctrf==0.3.5 pandas==2.2.3 numpy==2.1.3 openpyxl==3.1.5

mkdir -p /logs/verifier

pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA -v
PYTEST_EXIT_CODE=$?

if [ $PYTEST_EXIT_CODE -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi

exit 0
```

---

*End of PRD*
