# Where AI Agents Break

An independent study of AI agents on realistic SaaS Revenue Operations tasks.

📄 **Read the full report: [report/where-ai-agents-break.pdf](report/where-ai-agents-break.pdf)** — the complete write-up, covering the task distribution, per-task failure analysis, difficulty calibration, verifier design, the plan to scale from 5 tasks to 1,000, and references.

This repository holds the five selected Harbor-format task samples from the study. Each task is a self-contained environment with a deterministic verifier, a reference (oracle) solution, and the recorded agent trial artifacts (trajectories, terminal recordings, and verifier results).

**Model evaluated:** `gemini/gemini-3.5-flash` via `terminus-2`.

## Results at a glance

15 trials across 5 tasks; 2 passed. Full failure analysis for each task is in the [report](report/where-ai-agents-break.pdf).

| Task | Trials passed | pass@1 | pass@3 |
|---|---|---|---|
| `structured-mrr-rebuild` | 2 / 3 | 0.667 | 1.000 |
| `pricing-migration-rule-engine-audit` | 0 / 3 | 0.000 | 0.000 |
| `quota-commission-reconciliation-audit` | 0 / 3 | 0.000 | 0.000 |
| `revenue-retention-leakage-audit` | 0 / 3 | 0.000 | 0.000 |
| `usage-billing-dispute-audit` | 0 / 3 | 0.000 | 0.000 |
| **Aggregate** | **2 / 15** | **13.3%** | **20.0%** |

## Repository layout

```
.
├── report/
│   └── where-ai-agents-break.pdf          # the full study (start here)
└── samples/
    ├── structured-mrr-rebuild/
    ├── pricing-migration-rule-engine-audit/
    ├── quota-commission-reconciliation-audit/
    ├── revenue-retention-leakage-audit/
    └── usage-billing-dispute-audit/
```

- **`report/`** — the full PDF report.
- **`samples/`** — the five benchmark tasks. Each was added through its own pull request.

## The five samples

| Sample | Workflow | Skill isolated |
|---|---|---|
| [`structured-mrr-rebuild`](samples/structured-mrr-rebuild) | Rebuild SaaS MRR from raw billing exports | Structured ETL baseline |
| [`pricing-migration-rule-engine-audit`](samples/pricing-migration-rule-engine-audit) | Repair a plan-migration rule engine | Multi-module code repair + formula workbook |
| [`quota-commission-reconciliation-audit`](samples/quota-commission-reconciliation-audit) | Repair a Q1 commission workbook in place | In-place workbook repair + Excel semantics |
| [`revenue-retention-leakage-audit`](samples/revenue-retention-leakage-audit) | Audit a churn pipeline for temporal leakage | Leakage removal + source-code hygiene |
| [`usage-billing-dispute-audit`](samples/usage-billing-dispute-audit) | Investigate a customer billing dispute | Multi-modal parsing + FX reconciliation |

## What's inside each sample

Every `samples/<name>/` folder is a complete, runnable task:

| Path | What it is |
|---|---|
| `instruction.md` | The task prompt given to the agent |
| `task.toml` | Task configuration and metadata |
| `environment/` | Dockerfile, input generators (`data/build_inputs.py`), and task skills |
| `solution/` | The reference (oracle) solution that scores reward 1.0 |
| `tests/` | The deterministic verifier (`test_outputs.py`, `test.sh`) |
| `jobs/` | Recorded trial artifacts: agent trajectories, terminal recordings (`.cast`), and per-trial verifier output and rewards |

Two samples carry extras: `quota-commission-reconciliation-audit` includes a `PRD.md`, and `usage-billing-dispute-audit` includes a `scripts/` directory.

## How the evaluation works

Each task ships with two guardrails so results can be trusted:

- an **oracle** solution that must score reward **1.0**, and
- a **nop** agent (does nothing) that must score **0.0**.

Scoring is deterministic pytest against the final container state — output files, schemas, numeric values, workbook artifacts, and patched source code. No task uses LLM-as-judge grading. Because every expected value traces back to a visible input (data, policy PDF, workbook formula, or source), each failure can be explained from the recorded trajectory. See the [report](report/where-ai-agents-break.pdf) for the full methodology and the failure taxonomy.
