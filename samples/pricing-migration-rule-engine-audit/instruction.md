# Pricing Migration Rule Engine Audit

The revenue operations team migrated SaaS customers from legacy plans to new 2026 pricing packages. The migration audit tool under `/root/project` is producing incorrect results.

Your task is to repair the migration audit pipeline so it correctly applies the pricing migration rules, compares expected migration outcomes against the actual assignments, and writes the required audit outputs.

All input files are under `/root/data`:

- `legacy_accounts.csv` — account master with legacy plan, segment, seats, and migration date
- `product_usage_events.csv` — raw usage events used to determine usage tier
- `contract_terms.jsonl` — contract metadata including grandfathering terms
- `exception_approvals.xlsx` — approved plan or price exceptions
- `migration_rules.pdf` — authoritative rule document defining plan mapping, price floors, exceptions, precedence, and output schemas
- `new_plan_assignments.csv` — actual migration assignments from the company system

The project code is under `/root/project`:

- `rules.py`
- `pricing.py`
- `audit_migration.py`
- `config.yaml`

Repair the code so this command succeeds:

```bash
python3 /root/project/audit_migration.py --config /root/project/config.yaml
```

Create `/root/out` if it does not exist.

The command must produce exactly these files:

1. `/root/out/migration_audit.csv`
2. `/root/out/rule_violations.json`
3. `/root/out/revenue_impact_summary.csv`
4. `/root/out/exception_review.csv`

Use `migration_rules.pdf` as the source of truth for plan mapping, price floors, exception validity, grandfathering behavior, output schemas, and allowed string values.

The verifier imports functions by name from the project modules. Preserve the following public API when making repairs:

- `rules.py`: `calculate_usage_tier`, `apply_exception`, `apply_grandfathering`, `determine_expected_plan`
- `pricing.py`: `calculate_price_floor`, `calculate_expected_price`

Do not rename these functions. You may add helper functions. The CLI entrypoint `python3 audit_migration.py --config` must remain unchanged.

All numeric outputs must be stored as numbers, not strings. CSV files must contain only the requested columns.
