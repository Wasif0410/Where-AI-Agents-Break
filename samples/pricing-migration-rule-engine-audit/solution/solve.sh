#!/bin/bash
# Oracle solution for pricing-migration-rule-engine-audit.
# Overwrites buggy project files with correct implementations, then runs the audit.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$SCRIPT_DIR/approval_workbook.py" /root/project/approval_workbook.py

python3 - << 'PYEOF'
import os

PROJECT_DIR = "/root/project"

# ============================================================
# Write correct rules.py
# ============================================================
correct_rules = '''\
"""rules.py - Migration plan assignment and exception processing (corrected)."""

import pandas as pd
from datetime import timedelta

PLAN_MAPPING = {
    ("Legacy Starter",    "Low"):    "Launch",
    ("Legacy Starter",    "Medium"): "Scale",
    ("Legacy Starter",    "High"):   "Scale Plus",
    ("Legacy Growth",     "Low"):    "Scale",
    ("Legacy Growth",     "Medium"): "Scale Plus",
    ("Legacy Growth",     "High"):   "Enterprise",
    ("Legacy Pro",        "Low"):    "Scale Plus",
    ("Legacy Pro",        "Medium"): "Enterprise",
    ("Legacy Pro",        "High"):   "Enterprise Plus",
    ("Legacy Enterprise", "Low"):    "Enterprise Plus",
    ("Legacy Enterprise", "Medium"): "Enterprise Plus",
    ("Legacy Enterprise", "High"):   "Enterprise Plus",
}

PLAN_HIERARCHY = ["Launch", "Scale", "Scale Plus", "Enterprise", "Enterprise Plus"]


def calculate_usage_tier(events_df, account_id, migration_effective_date):
    """Compute usage tier from trailing 90-day API calls ending before migration date."""
    migration_dt = pd.Timestamp(migration_effective_date)
    window_start = migration_dt - pd.Timedelta(days=90)
    acct_events = events_df[
        (events_df["account_id"] == account_id)
        & (events_df["event_date"] >= window_start)
        & (events_df["event_date"] < migration_dt)
    ]
    total_calls = int(acct_events["api_calls"].sum())
    if total_calls >= 500_000:
        return "High"
    elif total_calls >= 100_000:
        return "Medium"
    return "Low"


def _get_default_plan(legacy_plan, usage_tier):
    return PLAN_MAPPING.get((legacy_plan, usage_tier), "Scale")


def apply_exception(account_id, default_plan, approvals_df, migration_effective_date):
    """Apply a valid plan_override; inactive or expired approvals are ignored."""
    if approvals_df is None or approvals_df.empty:
        return default_plan
    from approval_workbook import is_approval_valid
    acct_approvals = approvals_df[
        (approvals_df["account_id"] == account_id)
        & (approvals_df["exception_type"] == "plan_override")
    ]
    for _, row in acct_approvals.iterrows():
        if not is_approval_valid(row.to_dict(), migration_effective_date):
            continue
        approved_plan = row.get("approved_plan")
        if pd.notna(approved_plan) and str(approved_plan).strip():
            return str(approved_plan).strip()
    return default_plan


def apply_grandfathering(account_id, plan, contracts_df, migration_effective_date):
    """Return plan unchanged. Grandfathering applies only to the price floor."""
    return plan


def determine_expected_plan(account_id, legacy_plan, events_df, approvals_df,
                            contracts_df, migration_effective_date):
    """Determine the expected new plan applying rules in correct precedence."""
    usage_tier = calculate_usage_tier(events_df, account_id, migration_effective_date)
    default_plan = _get_default_plan(legacy_plan, usage_tier)
    final_plan = apply_exception(
        account_id, default_plan, approvals_df, migration_effective_date
    )
    return usage_tier, final_plan
'''

with open(os.path.join(PROJECT_DIR, "rules.py"), "w", encoding="utf-8") as f:
    f.write(correct_rules)

# ============================================================
# Write correct pricing.py
# ============================================================
correct_pricing = '''\
"""pricing.py - Price floor and monthly price calculations (corrected)."""

import pandas as pd

BASE_PRICES = {
    "Launch":          500.0,
    "Scale":           1200.0,
    "Scale Plus":      2200.0,
    "Enterprise":      4200.0,
    "Enterprise Plus": 7200.0,
}

SEAT_FLOORS = {
    "Launch":          50.0,
    "Scale":           60.0,
    "Scale Plus":      75.0,
    "Enterprise":      90.0,
    "Enterprise Plus": 110.0,
}


def _normalize_discount_pct(raw):
    """Normalize contract discount to a decimal fraction."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return 0.0
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if val > 1.0:
        val = val / 100.0
    return val


def calculate_price_floor(plan, seats, contract_row, migration_effective_date):
    """Return the per-seat price floor after applying grandfathering discount."""
    seat_floor = SEAT_FLOORS.get(plan, 0.0)
    if contract_row is not None:
        gf_until = contract_row.get("grandfathered_until")
        if gf_until and not (isinstance(gf_until, float) and pd.isna(gf_until)):
            try:
                gf_dt = pd.Timestamp(gf_until)
                migration_dt = pd.Timestamp(migration_effective_date)
                if gf_dt >= migration_dt:
                    discount = _normalize_discount_pct(
                        contract_row.get("price_floor_discount_pct", 0.0)
                    )
                    seat_floor = seat_floor * (1.0 - discount)
            except Exception:
                pass
    return seat_floor


def calculate_expected_price(plan, seats, contract_row, migration_effective_date):
    """Calculate the expected monthly price from plan, seat count, and contract terms."""
    floor_per_seat = calculate_price_floor(plan, seats, contract_row, migration_effective_date)
    base = BASE_PRICES.get(plan, 0.0)
    return round(max(base, seats * floor_per_seat), 2)


def apply_price_exception(account_id, computed_price, approvals_df, migration_effective_date):
    """Apply the most recent valid price_override for the account."""
    if approvals_df is None or approvals_df.empty:
        return computed_price
    from approval_workbook import is_approval_valid
    acct_approvals = approvals_df[
        (approvals_df["account_id"] == account_id)
        & (approvals_df["exception_type"] == "price_override")
    ]
    valid_rows = []
    for _, row in acct_approvals.iterrows():
        if not is_approval_valid(row.to_dict(), migration_effective_date):
            continue
        approved_price = row.get("approved_price")
        if pd.notna(approved_price):
            valid_rows.append(row)
    if not valid_rows:
        return computed_price
    best = max(valid_rows, key=lambda r: pd.Timestamp(r.get("effective_date")))
    return round(float(best["approved_price"]), 2)
'''

with open(os.path.join(PROJECT_DIR, "pricing.py"), "w", encoding="utf-8") as f:
    f.write(correct_pricing)

# ============================================================
# Write correct audit_migration.py
# ============================================================
correct_audit = '''\
"""audit_migration.py - Migration audit orchestration (corrected)."""

import argparse
import json
import os
import sys

import pandas as pd
import yaml


def load_config(config_path):
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_exception_approvals(data_dir):
    """Load formula-backed exception approvals from the multi-sheet workbook."""
    from approval_workbook import load_exception_approvals as load_workbook_approvals
    return load_workbook_approvals(data_dir)


def run_audit(config_path):
    cfg = load_config(config_path)
    data_dir = cfg["data_dir"]
    out_dir = cfg["out_dir"]
    migration_date = cfg["migration_effective_date"]

    os.makedirs(out_dir, exist_ok=True)

    accounts_df = pd.read_csv(os.path.join(data_dir, "legacy_accounts.csv"))
    events_df = pd.read_csv(os.path.join(data_dir, "product_usage_events.csv"),
                            parse_dates=["event_date"])
    contracts = {}
    with open(os.path.join(data_dir, "contract_terms.jsonl")) as f:
        for line in f:
            rec = json.loads(line.strip())
            contracts[rec["account_id"]] = rec
    approvals_df = load_exception_approvals(data_dir)
    assignments_df = pd.read_csv(os.path.join(data_dir, "new_plan_assignments.csv"))

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from rules import determine_expected_plan
    from pricing import calculate_expected_price, apply_price_exception

    contracts_df = pd.DataFrame(contracts.values())
    audit_rows = []

    for _, acct in accounts_df.iterrows():
        account_id = acct["account_id"]
        legacy_plan = acct["legacy_plan"]
        seats = int(acct["current_seats"])
        contract_row = contracts.get(account_id)

        usage_tier, expected_plan = determine_expected_plan(
            account_id, legacy_plan, events_df, approvals_df,
            contracts_df=contracts_df,
            migration_effective_date=migration_date,
        )

        computed_price = calculate_expected_price(
            expected_plan, seats, contract_row, migration_date
        )
        expected_price = apply_price_exception(
            account_id, computed_price, approvals_df, migration_date
        )

        assignment = assignments_df[assignments_df["account_id"] == account_id]
        assigned_plan = assignment["assigned_new_plan"].values[0]
        assigned_price = float(assignment["assigned_monthly_price"].values[0])

        violation_type = _determine_violation(
            account_id, legacy_plan, usage_tier, expected_plan, assigned_plan,
            expected_price, assigned_price, approvals_df, contracts,
            migration_date, events_df,
        )
        migration_status = "pass" if violation_type == "no_violation" else "fail"
        # revenue_impact = assigned - expected (positive = overcharged)
        revenue_impact = round(assigned_price - expected_price, 2)

        audit_rows.append({
            "account_id": account_id,
            "legacy_plan": legacy_plan,
            "usage_tier": usage_tier,
            "expected_new_plan": expected_plan,
            "assigned_new_plan": assigned_plan,
            "expected_monthly_price": expected_price,
            "assigned_monthly_price": assigned_price,
            "migration_status": migration_status,
            "violation_type": violation_type,
            "revenue_impact_usd": revenue_impact,
        })

    audit_df = pd.DataFrame(audit_rows)
    audit_df.to_csv(os.path.join(out_dir, "migration_audit.csv"), index=False)

    # rule_violations.json — all required keys
    failed_df = audit_df[audit_df["migration_status"] == "fail"]
    passed_df = audit_df[audit_df["migration_status"] == "pass"]
    vc = failed_df["violation_type"].value_counts().to_dict()

    abs_impacts = audit_df["revenue_impact_usd"].abs()
    highest_idx = abs_impacts.idxmax()
    highest_account = audit_df.loc[highest_idx, "account_id"]

    violations_summary = {
        "total_accounts": int(len(audit_df)),
        "failed_accounts": int(len(failed_df)),
        "passed_accounts": int(len(passed_df)),
        "violation_counts": {
            "wrong_plan":              int(vc.get("wrong_plan", 0)),
            "wrong_price_floor":       int(vc.get("wrong_price_floor", 0)),
            "expired_exception":       int(vc.get("expired_exception", 0)),
            "missing_grandfathering":  int(vc.get("missing_grandfathering", 0)),
            "usage_tier_miscalculated":int(vc.get("usage_tier_miscalculated", 0)),
        },
        "highest_revenue_impact_account": highest_account,
        "net_revenue_impact_usd": round(float(audit_df["revenue_impact_usd"].sum()), 2),
        "policy_sources": [
            "migration_rules.pdf",
            "legacy_accounts.csv",
            "product_usage_events.csv",
            "contract_terms.jsonl",
            "exception_approvals.xlsx",
            "new_plan_assignments.csv",
        ],
    }

    with open(os.path.join(out_dir, "rule_violations.json"), "w") as f:
        json.dump(violations_summary, f, indent=2)

    # revenue_impact_summary.csv
    pos = audit_df[audit_df["revenue_impact_usd"] > 0]["revenue_impact_usd"]
    neg = audit_df[audit_df["revenue_impact_usd"] < 0]["revenue_impact_usd"]
    summary_rows = [
        {"metric": "total_overcharge_usd",        "value": round(float(pos.sum()), 2)},
        {"metric": "total_undercharge_usd",        "value": round(float(neg.abs().sum()), 2)},
        {"metric": "net_revenue_impact_usd",       "value": round(float(audit_df["revenue_impact_usd"].sum()), 2)},
        {"metric": "absolute_revenue_impact_usd",  "value": round(float(audit_df["revenue_impact_usd"].abs().sum()), 2)},
        {"metric": "failed_account_count",         "value": int(len(failed_df))},
    ]
    pd.DataFrame(summary_rows).to_csv(
        os.path.join(out_dir, "revenue_impact_summary.csv"), index=False
    )

    # exception_review.csv
    review_rows = _build_exception_review(approvals_df, audit_df, migration_date)
    pd.DataFrame(review_rows).to_csv(
        os.path.join(out_dir, "exception_review.csv"), index=False
    )

    print(f"Audit complete. Results written to {out_dir}")
    print(f"  Failed accounts: {len(failed_df)}/{len(audit_df)}")
    print(f"  Net revenue impact: ${violations_summary['net_revenue_impact_usd']:,.2f}")


def _naive_usage_tier(events_df, account_id, migration_date):
    """Compute usage tier from migration-month events (detects the common naive bug)."""
    migration_dt = pd.Timestamp(migration_date)
    acct_events = events_df[
        (events_df["account_id"] == account_id)
        & (events_df["event_date"].dt.month == migration_dt.month)
        & (events_df["event_date"].dt.year == migration_dt.year)
    ]
    total = int(acct_events["api_calls"].sum())
    if total >= 500_000:
        return "High"
    elif total >= 100_000:
        return "Medium"
    return "Low"


_PLAN_MAPPING = {
    ("Legacy Starter",    "Low"):    "Launch",
    ("Legacy Starter",    "Medium"): "Scale",
    ("Legacy Starter",    "High"):   "Scale Plus",
    ("Legacy Growth",     "Low"):    "Scale",
    ("Legacy Growth",     "Medium"): "Scale Plus",
    ("Legacy Growth",     "High"):   "Enterprise",
    ("Legacy Pro",        "Low"):    "Scale Plus",
    ("Legacy Pro",        "Medium"): "Enterprise",
    ("Legacy Pro",        "High"):   "Enterprise Plus",
    ("Legacy Enterprise", "Low"):    "Enterprise Plus",
    ("Legacy Enterprise", "Medium"): "Enterprise Plus",
    ("Legacy Enterprise", "High"):   "Enterprise Plus",
}


def _determine_violation(account_id, legacy_plan, usage_tier, expected_plan,
                         assigned_plan, expected_price, assigned_price,
                         approvals_df, contracts, migration_date, events_df):
    migration_dt = pd.Timestamp(migration_date)

    # Check for expired exception applied in assignment
    if approvals_df is not None and not approvals_df.empty:
        acct_approvals = approvals_df[approvals_df["account_id"] == account_id]
        for _, row in acct_approvals.iterrows():
            expiry = row.get("expiry_date")
            try:
                expiry_dt = pd.Timestamp(expiry)
                if expiry_dt < migration_dt:
                    # This approval is expired
                    if (row["exception_type"] == "plan_override"
                            and assigned_plan != expected_plan):
                        return "expired_exception"
                    if (row["exception_type"] == "price_override"
                            and abs(assigned_price - expected_price) > 0.01):
                        return "expired_exception"
            except Exception:
                pass

    if assigned_plan != expected_plan:
        # Check if the wrong plan is explainable by a naive usage-tier computation
        naive_tier = _naive_usage_tier(events_df, account_id, migration_date)
        naive_plan = _PLAN_MAPPING.get((legacy_plan, naive_tier), "Scale")
        if naive_plan == assigned_plan and naive_tier != usage_tier:
            return "usage_tier_miscalculated"
        return "wrong_plan"

    if abs(assigned_price - expected_price) > 0.01:
        # If a valid price_override was applied, the expected price was set by the override,
        # not by grandfathering floor. Any discrepancy is wrong_price_floor, not missing_grandfathering.
        has_valid_price_override = False
        if approvals_df is not None and not approvals_df.empty:
            for _, prow in approvals_df[approvals_df["account_id"] == account_id].iterrows():
                if prow.get("exception_type") == "price_override":
                    try:
                        if pd.Timestamp(prow["expiry_date"]) >= migration_dt and pd.notna(prow.get("approved_price")):
                            has_valid_price_override = True
                            break
                    except Exception:
                        pass
        if not has_valid_price_override:
            contract = contracts.get(account_id, {})
            gf = contract.get("grandfathered_until")
            is_grandfathered = False
            if gf and not (isinstance(gf, float) and str(gf) == "nan"):
                try:
                    if pd.Timestamp(gf) >= migration_dt:
                        is_grandfathered = True
                except Exception:
                    pass
            if is_grandfathered:
                return "missing_grandfathering"
        return "wrong_price_floor"

    return "no_violation"


def _build_exception_review(approvals_df, audit_df, migration_date):
    from approval_workbook import is_approval_valid, is_approval_status_active
    migration_dt = pd.Timestamp(migration_date)
    rows = []
    for _, row in approvals_df.iterrows():
        account_id = row["account_id"]
        approval_id = row["approval_id"]
        exc_type = row["exception_type"]
        expiry = row.get("expiry_date")
        row_dict = row.to_dict()
        is_valid = is_approval_valid(row_dict, migration_date)

        if is_valid:
            applied = True
            review_status = "valid_applied"
        else:
            applied = False
            from approval_workbook import _norm_status
            status = _norm_status(row.get("approval_status"))
            if status == "superseded":
                review_status = "superseded_not_applied"
            elif status in ("expired", "cancelled", "denied", "rejected"):
                review_status = "expired_not_applied"
            elif status == "pending":
                review_status = "pending_not_applied"
            else:
                try:
                    effective = pd.Timestamp(row.get("effective_date"))
                    if effective > migration_dt:
                        review_status = "pending_not_applied"
                    else:
                        review_status = "expired_not_applied"
                except Exception:
                    review_status = "expired_not_applied"

        expiry_str = str(expiry)[:10] if pd.notna(expiry) else ""

        rows.append({
            "account_id": account_id,
            "approval_id": approval_id,
            "exception_type": exc_type,
            "expiry_date": expiry_str,
            "is_valid_on_migration_date": is_valid,
            "applied_to_expected_result": applied,
            "review_status": review_status,
        })
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    run_audit(args.config)
'''

with open(os.path.join(PROJECT_DIR, "audit_migration.py"), "w", encoding="utf-8") as f:
    f.write(correct_audit)

print("Oracle: project files replaced with correct implementations.")
PYEOF

python3 /root/project/audit_migration.py --config /root/project/config.yaml
