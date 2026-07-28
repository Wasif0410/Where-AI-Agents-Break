"""
test_outputs.py — Deterministic pytest verifier for pricing-migration-rule-engine-audit.
Reduced scope: 9 accounts, ~58 tests. Expected values match build_inputs.py canonical data.
"""

import json
import os
import shutil
import subprocess
import sys

import pandas as pd
import pytest

PROJECT_DIR = "/root/project"
OUT_DIR = "/root/out"
MONEY_TOL = 0.01

TOTAL_ACCOUNTS = 9
FAILED_ACCOUNTS = 6
PASSED_ACCOUNTS = 3
EXCEPTION_REVIEW_ROWS = 5

REQUIRED_AUDIT_COLUMNS = [
    "account_id", "legacy_plan", "usage_tier", "expected_new_plan",
    "assigned_new_plan", "expected_monthly_price", "assigned_monthly_price",
    "migration_status", "violation_type", "revenue_impact_usd",
]
REQUIRED_VIOLATION_KEYS = [
    "total_accounts", "failed_accounts", "passed_accounts", "violation_counts",
    "highest_revenue_impact_account", "net_revenue_impact_usd", "policy_sources",
]
REQUIRED_VIOLATION_COUNT_KEYS = [
    "wrong_plan", "wrong_price_floor", "expired_exception",
    "missing_grandfathering", "usage_tier_miscalculated",
]
REQUIRED_SUMMARY_METRICS = [
    "total_overcharge_usd", "total_undercharge_usd",
    "net_revenue_impact_usd", "absolute_revenue_impact_usd", "failed_account_count",
]
REQUIRED_REVIEW_COLUMNS = [
    "account_id", "approval_id", "exception_type", "expiry_date",
    "is_valid_on_migration_date", "applied_to_expected_result", "review_status",
]
REQUIRED_POLICY_SOURCES = [
    "migration_rules.pdf", "legacy_accounts.csv", "product_usage_events.csv",
    "contract_terms.jsonl", "exception_approvals.xlsx", "new_plan_assignments.csv",
]

NET_REVENUE_IMPACT = 1743.75
TOTAL_OVERCHARGE = 5393.75
TOTAL_UNDERCHARGE = 3650.00
ABSOLUTE_REVENUE_IMPACT = 9043.75
HIGHEST_REVENUE_ACCOUNT = "acct_002"


@pytest.fixture(scope="session", autouse=True)
def run_pipeline():
    if os.path.exists(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR, exist_ok=True)
    result = subprocess.run(
        ["python3", f"{PROJECT_DIR}/audit_migration.py",
         "--config", f"{PROJECT_DIR}/config.yaml"],
        capture_output=True,
        text=True,
    )
    yield result


def load_audit():
    return pd.read_csv(os.path.join(OUT_DIR, "migration_audit.csv"))


def load_violations():
    with open(os.path.join(OUT_DIR, "rule_violations.json")) as f:
        return json.load(f)


def load_summary():
    df = pd.read_csv(os.path.join(OUT_DIR, "revenue_impact_summary.csv"))
    return dict(zip(df["metric"], df["value"]))


def load_exception_review():
    return pd.read_csv(os.path.join(OUT_DIR, "exception_review.csv"))


def get_row(df, account_id):
    rows = df[df["account_id"] == account_id]
    assert len(rows) == 1, f"Expected exactly one row for {account_id}, got {len(rows)}"
    return rows.iloc[0]


def to_bool(val):
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    return str(val).strip().lower() in ("true", "1", "yes")


class TestOutputFilesExist:
    def test_migration_audit_exists(self):
        assert os.path.exists(os.path.join(OUT_DIR, "migration_audit.csv"))

    def test_rule_violations_exists(self):
        assert os.path.exists(os.path.join(OUT_DIR, "rule_violations.json"))

    def test_revenue_impact_summary_exists(self):
        assert os.path.exists(os.path.join(OUT_DIR, "revenue_impact_summary.csv"))

    def test_exception_review_exists(self):
        assert os.path.exists(os.path.join(OUT_DIR, "exception_review.csv"))


class TestOutputSchemas:
    def test_audit_columns(self):
        df = load_audit()
        for col in REQUIRED_AUDIT_COLUMNS:
            assert col in df.columns, f"migration_audit.csv missing column: {col}"

    def test_audit_only_required_columns(self):
        df = load_audit()
        assert list(df.columns) == REQUIRED_AUDIT_COLUMNS

    def test_violations_json_keys(self):
        v = load_violations()
        for key in REQUIRED_VIOLATION_KEYS:
            assert key in v, f"rule_violations.json missing key: {key}"

    def test_violations_json_count_keys(self):
        v = load_violations()
        for key in REQUIRED_VIOLATION_COUNT_KEYS:
            assert key in v["violation_counts"], f"violation_counts missing key: {key}"

    def test_summary_metrics(self):
        summary = load_summary()
        for metric in REQUIRED_SUMMARY_METRICS:
            assert metric in summary, f"revenue_impact_summary.csv missing metric: {metric}"

    def test_review_columns(self):
        df = load_exception_review()
        for col in REQUIRED_REVIEW_COLUMNS:
            assert col in df.columns, f"exception_review.csv missing column: {col}"

    def test_audit_numeric_price_columns(self):
        df = load_audit()
        for col in ("expected_monthly_price", "assigned_monthly_price", "revenue_impact_usd"):
            assert pd.api.types.is_numeric_dtype(df[col]), f"{col} must be numeric"

    def test_audit_row_count(self):
        df = load_audit()
        assert len(df) == TOTAL_ACCOUNTS

    def test_policy_sources(self):
        v = load_violations()
        assert v["policy_sources"] == REQUIRED_POLICY_SOURCES


class TestViolationAccounts:
    @pytest.mark.parametrize("account_id,violation", [
        ("acct_002", "usage_tier_miscalculated"),
        ("acct_003", "wrong_plan"),
        ("acct_005", "expired_exception"),
        ("acct_006", "wrong_price_floor"),
        ("acct_007", "missing_grandfathering"),
        ("acct_013", "wrong_price_floor"),
    ])
    def test_fail_account_violation_type(self, account_id, violation):
        row = get_row(load_audit(), account_id)
        assert row["migration_status"] == "fail"
        assert row["violation_type"] == violation


class TestPassAccounts:
    @pytest.mark.parametrize("account_id", ["acct_001", "acct_004", "acct_008"])
    def test_pass_account(self, account_id):
        row = get_row(load_audit(), account_id)
        assert row["migration_status"] == "pass"
        assert row["violation_type"] == "no_violation"


class TestCriticalExpectedValues:
    def test_acct_002_usage_tier_and_plan(self):
        row = get_row(load_audit(), "acct_002")
        assert row["usage_tier"] == "Low"
        assert row["expected_new_plan"] == "Scale"

    def test_acct_003_expected_plan_enterprise(self):
        row = get_row(load_audit(), "acct_003")
        assert row["expected_new_plan"] == "Enterprise"

    def test_acct_004_plan_from_workbook_override(self):
        row = get_row(load_audit(), "acct_004")
        assert row["expected_new_plan"] == "Scale"

    def test_acct_006_scale_seat_floor_price(self):
        row = get_row(load_audit(), "acct_006")
        assert abs(float(row["expected_monthly_price"]) - 1500.00) <= MONEY_TOL

    def test_acct_007_grandfathered_price(self):
        row = get_row(load_audit(), "acct_007")
        assert row["expected_new_plan"] == "Scale Plus"
        assert abs(float(row["expected_monthly_price"]) - 2231.25) <= MONEY_TOL

    def test_acct_008_workbook_formula_price(self):
        row = get_row(load_audit(), "acct_008")
        assert abs(float(row["expected_monthly_price"]) - 3500.00) <= MONEY_TOL

    def test_acct_013_override_price_precedence(self):
        row = get_row(load_audit(), "acct_013")
        assert abs(float(row["expected_monthly_price"]) - 3500.00) <= MONEY_TOL


class TestRevenueImpact:
    def test_acct_002_overcharge(self):
        row = get_row(load_audit(), "acct_002")
        assert abs(float(row["revenue_impact_usd"]) - 3000.00) <= MONEY_TOL

    def test_acct_003_undercharge(self):
        row = get_row(load_audit(), "acct_003")
        assert abs(float(row["revenue_impact_usd"]) - (-3000.00)) <= MONEY_TOL

    def test_revenue_impact_sign_convention(self):
        row = get_row(load_audit(), "acct_002")
        assert float(row["revenue_impact_usd"]) > 0


class TestSummaryCounts:
    def test_total_accounts(self):
        assert load_violations()["total_accounts"] == TOTAL_ACCOUNTS

    def test_failed_accounts(self):
        assert load_violations()["failed_accounts"] == FAILED_ACCOUNTS

    def test_passed_accounts(self):
        assert load_violations()["passed_accounts"] == PASSED_ACCOUNTS

    def test_violation_counts(self):
        vc = load_violations()["violation_counts"]
        assert vc["wrong_plan"] == 1
        assert vc["wrong_price_floor"] == 2
        assert vc["expired_exception"] == 1
        assert vc["missing_grandfathering"] == 1
        assert vc["usage_tier_miscalculated"] == 1

    def test_net_revenue_impact(self):
        net = float(load_violations()["net_revenue_impact_usd"])
        assert abs(net - NET_REVENUE_IMPACT) <= MONEY_TOL

    def test_revenue_summary_totals(self):
        summary = load_summary()
        assert abs(float(summary["total_overcharge_usd"]) - TOTAL_OVERCHARGE) <= MONEY_TOL
        assert abs(float(summary["total_undercharge_usd"]) - TOTAL_UNDERCHARGE) <= MONEY_TOL
        assert abs(float(summary["net_revenue_impact_usd"]) - NET_REVENUE_IMPACT) <= MONEY_TOL
        assert abs(float(summary["absolute_revenue_impact_usd"]) - ABSOLUTE_REVENUE_IMPACT) <= MONEY_TOL
        assert int(summary["failed_account_count"]) == FAILED_ACCOUNTS


class TestHighestRevenueImpact:
    def test_highest_revenue_impact_account(self):
        acct = load_violations()["highest_revenue_impact_account"]
        assert acct == HIGHEST_REVENUE_ACCOUNT


class TestExceptionReview:
    def _get_review_row(self, approval_id):
        df = load_exception_review()
        rows = df[df["approval_id"] == approval_id]
        assert len(rows) == 1
        return rows.iloc[0]

    def test_exc_001_valid_applied(self):
        row = self._get_review_row("EXC-001")
        assert to_bool(row["is_valid_on_migration_date"]) is True
        assert row["review_status"] == "valid_applied"

    def test_exc_002_expired_not_applied(self):
        row = self._get_review_row("EXC-002")
        assert to_bool(row["is_valid_on_migration_date"]) is False
        assert to_bool(row["applied_to_expected_result"]) is False
        assert row["review_status"] == "expired_not_applied"

    def test_exc_003_valid_applied(self):
        row = self._get_review_row("EXC-003")
        assert to_bool(row["is_valid_on_migration_date"]) is True
        assert row["review_status"] == "valid_applied"

    def test_exc_005_valid_applied(self):
        row = self._get_review_row("EXC-005")
        assert to_bool(row["is_valid_on_migration_date"]) is True
        assert row["review_status"] == "valid_applied"

    def test_exc_003a_superseded_not_applied(self):
        row = self._get_review_row("EXC-003A")
        assert to_bool(row["is_valid_on_migration_date"]) is False
        assert to_bool(row["applied_to_expected_result"]) is False
        assert row["review_status"] == "superseded_not_applied"

    def test_exception_review_row_count(self):
        assert len(load_exception_review()) == EXCEPTION_REVIEW_ROWS


class TestAntiNaive:
    def test_acct_002_not_using_current_month_usage(self):
        row = get_row(load_audit(), "acct_002")
        assert row["usage_tier"] != "High"
        assert row["expected_new_plan"] != "Enterprise"

    def test_acct_005_expired_exception_not_valid(self):
        row = get_row(load_audit(), "acct_005")
        assert row["expected_new_plan"] != "Enterprise"

    def test_acct_007_grandfathering_does_not_change_plan(self):
        row = get_row(load_audit(), "acct_007")
        assert row["expected_new_plan"] == "Scale Plus"

    def test_acct_004_excel_header_and_stale_sheet(self):
        row = get_row(load_audit(), "acct_004")
        assert row["expected_new_plan"] == "Scale"
        assert row["expected_new_plan"] != "Launch"

    def test_acct_008_price_not_superseded_row(self):
        row = get_row(load_audit(), "acct_008")
        assert abs(float(row["expected_monthly_price"]) - 4200.00) > MONEY_TOL
        assert abs(float(row["expected_monthly_price"]) - 3500.00) <= MONEY_TOL

    def test_acct_007_whole_number_discount_normalized(self):
        row = get_row(load_audit(), "acct_007")
        assert abs(float(row["expected_monthly_price"]) - 2231.25) <= MONEY_TOL
        assert abs(float(row["expected_monthly_price"]) - 2200.00) > MONEY_TOL

    def test_acct_008_price_not_pre_max_lookup(self):
        row = get_row(load_audit(), "acct_008")
        assert abs(float(row["expected_monthly_price"]) - 3400.00) > MONEY_TOL

    def test_acct_013_price_not_grandfathered_floor(self):
        row = get_row(load_audit(), "acct_013")
        assert abs(float(row["expected_monthly_price"]) - 4455.00) > MONEY_TOL

    def test_acct_006_scale_seat_floor_applied(self):
        row = get_row(load_audit(), "acct_006")
        assert abs(float(row["expected_monthly_price"]) - 1200.00) > MONEY_TOL

    def test_net_revenue_requires_workbook_formulas(self):
        net = float(load_violations()["net_revenue_impact_usd"])
        assert abs(net - NET_REVENUE_IMPACT) <= MONEY_TOL
        assert abs(net - 743.75) > MONEY_TOL


class TestFunctionLevel:
    @pytest.fixture(scope="class")
    def rules_mod(self):
        import importlib
        sys.path.insert(0, PROJECT_DIR)
        for m in ["rules", "pricing"]:
            sys.modules.pop(m, None)
        return importlib.import_module("rules")

    @pytest.fixture(scope="class")
    def pricing_mod(self):
        import importlib
        sys.path.insert(0, PROJECT_DIR)
        for m in ["rules", "pricing"]:
            sys.modules.pop(m, None)
        return importlib.import_module("pricing")

    def test_rules_public_api_exists(self, rules_mod):
        for fn in ["calculate_usage_tier", "apply_exception",
                   "apply_grandfathering", "determine_expected_plan"]:
            assert hasattr(rules_mod, fn)

    def test_pricing_public_api_exists(self, pricing_mod):
        for fn in ["calculate_price_floor", "calculate_expected_price"]:
            assert hasattr(pricing_mod, fn)

    def test_calculate_usage_tier_uses_trailing_window(self, rules_mod):
        events = pd.DataFrame([
            {"account_id": "t01", "event_date": pd.Timestamp("2026-01-15"),
             "api_calls": 80000, "active_users": 10},
            {"account_id": "t01", "event_date": pd.Timestamp("2026-04-10"),
             "api_calls": 650000, "active_users": 10},
        ])
        result = rules_mod.calculate_usage_tier(events, "t01", "2026-04-01")
        assert result == "Low"

    def test_apply_grandfathering_does_not_change_plan(self, rules_mod):
        contracts = pd.DataFrame([{
            "account_id": "t07",
            "grandfathered_until": "2026-06-30",
            "price_floor_discount_pct": 0.15,
        }])
        result = rules_mod.apply_grandfathering("t07", "Scale Plus", contracts, "2026-04-01")
        assert result == "Scale Plus"

    def test_calculate_price_floor_discount_on_seat_rate(self, pricing_mod):
        contract = {"grandfathered_until": "2026-06-30", "price_floor_discount_pct": 0.15}
        floor = pricing_mod.calculate_price_floor("Scale Plus", 35, contract, "2026-04-01")
        assert abs(floor - 63.75) < 0.02

    def test_calculate_expected_price_scale_seat_floor(self, pricing_mod):
        price = pricing_mod.calculate_expected_price("Scale", 25, None, "2026-04-01")
        assert abs(price - 1500.00) < 0.01
