"""
Verifier for the revenue-retention-leakage-audit task.

All tests are fully deterministic and do not use LLM-as-judge.

Cascade design:
  Verifier clears /root/out, reruns train_model.py, then checks outputs.
  If pipeline is unrepaired → train_model.py fails or outputs are invalid
"""

from __future__ import annotations

import json
import sqlite3
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest
import yaml

# ── Paths ──────────────────────────────────────────────────────────────────────

OUT_DIR              = Path('/root/out')
LEAKAGE_AUDIT_PATH   = OUT_DIR / 'leakage_audit.json'
BACKTEST_PATH        = OUT_DIR / 'backtest_results.csv'
HOLDOUT_PATH         = OUT_DIR / 'holdout_predictions.parquet'
FEATURES_PATH        = OUT_DIR / 'selected_features.txt'
CONFIG_PATH          = Path('/root/project/config.yaml')
DB_PATH              = Path('/root/data/revenue_warehouse.sqlite')
BACKTEST_WINDOWS_CSV = Path('/root/data/backtest_windows.csv')

# Starter columns from DROP-only PDF families (PROHIBITED / NOT available).
DROP_ONLY_FEATURE_NAMES = {
    'f04', 'f06', 'f07', 'f09', 'f10',
}

# Supplementary aggregates — must not remain in final model alongside repaired primaries.
ALT_AGGREGATE_FEATURES = {'f12', 'f13'}

USAGE_FEATURE_CANDIDATES = {'f02', 'f12'}
TICKET_COUNT_CANDIDATES = {'f03', 'f13'}
HEALTH_CANDIDATES = {'f08'}
PRIOR_INVOICE_CANDIDATES = {'f05'}
LEDGER_CANDIDATES = {'f01'}

ENGAGEMENT_REPAIR_NAMES = {'f02', 'f12'}
CASE_VOLUME_REPAIR_NAMES = {'f03', 'f13'}
VITALITY_REPAIR_NAMES = {'f08'}
PRIOR_SETTLEMENT_REPAIR_NAMES = {'f05'}

# Expected backtest validate months (from backtest_windows.csv)
EXPECTED_VALIDATE_MONTHS = {'2025-12', '2026-01', '2026-02', '2026-03'}

# Holdout month
HOLDOUT_MONTH = '2026-04'

# Total accounts in the warehouse (all 35 are active in April)
EXPECTED_HOLDOUT_ROWS = 35

# Exact temporal backtest row counts (35 accounts × N train months).
EXPECTED_BACKTEST_COUNTS = {
    '2025-12': {'n_train': 35, 'n_val': 35},
    '2026-01': {'n_train': 70, 'n_val': 35},
    '2026-02': {'n_train': 105, 'n_val': 35},
    '2026-03': {'n_train': 140, 'n_val': 35},
}

# All churn account-months — value checks run on every row with a distinguishable trap.
ALL_CHURN_CASES = [
    ('acc_002', '2025-11'), ('acc_004', '2025-11'), ('acc_012', '2025-11'),
    ('acc_016', '2025-11'), ('acc_025', '2025-11'), ('acc_029', '2025-11'),
    ('acc_033', '2025-11'),
    ('acc_001', '2025-12'), ('acc_006', '2025-12'), ('acc_011', '2025-12'),
    ('acc_018', '2025-12'), ('acc_026', '2025-12'), ('acc_030', '2025-12'),
    ('acc_034', '2025-12'),
    ('acc_003', '2026-01'), ('acc_007', '2026-01'), ('acc_014', '2026-01'),
    ('acc_019', '2026-01'), ('acc_027', '2026-01'), ('acc_032', '2026-01'),
    ('acc_005', '2026-02'), ('acc_008', '2026-02'), ('acc_013', '2026-02'),
    ('acc_021', '2026-02'), ('acc_023', '2026-02'), ('acc_035', '2026-02'),
    ('acc_009', '2026-03'), ('acc_015', '2026-03'), ('acc_020', '2026-03'),
    ('acc_022', '2026-03'),
]

# AUC bounds for an honest model
# NOTE: On this 35-account dataset the honest signals (health_score, usage_events)
# are strong enough that a clean logistic regression achieves mean AUC ≈ 0.99.
# An upper-bound AUC check cannot distinguish honest from leaky here — leakage is
# detected by the feature-name and pipeline-rerun tests above, not by AUC values.
HONEST_AUC_LOW  = 0.50


def _load_config():
    with CONFIG_PATH.open() as fh:
        return yaml.safe_load(fh)


def _import_pipeline():
    sys.path.insert(0, '/root/project')
    import feature_pipeline as fp  # noqa: WPS433
    return fp


def _prev_month(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:])
    return f'{y - 1}-12' if m == 1 else f'{y}-{m - 1:02d}'


def _last_day_prev_month(pred_month: str) -> str:
    prev_m = _prev_month(pred_month)
    y, m = int(prev_m[:4]), int(prev_m[5:])
    import calendar
    last_day = calendar.monthrange(y, m)[1]
    return f'{prev_m}-{last_day:02d}'


def _window_start_str(pred_month: str) -> str:
    y, m = int(pred_month[:4]), int(pred_month[5:])
    d = date(y, m, 1) - timedelta(days=30)
    return d.strftime('%Y-%m-%d')


def _label_end_str(pred_month: str) -> str:
    y, m = int(pred_month[:4]), int(pred_month[5:])
    d = date(y, m, 1) + timedelta(days=30)
    return d.strftime('%Y-%m-%d')


def _column_from_candidates(df: pd.DataFrame, candidates: set[str]) -> str | None:
    found = [c for c in df.columns if c in candidates]
    return found[0] if len(found) == 1 else None


def _selected_column(
    df: pd.DataFrame, selected: set[str], candidates: set[str],
) -> str | None:
    found = [c for c in df.columns if c in candidates and c.lower() in selected]
    return found[0] if len(found) == 1 else None


def _selected_from_family(selected: set[str], candidates: set[str]) -> list[str]:
    return sorted(f for f in selected if f in candidates)


def _repaired_entry_names(repaired: list) -> set[str]:
    return {
        str(entry.get('name', '')).strip().lower()
        for entry in repaired
        if isinstance(entry, dict) and str(entry.get('name', '')).strip()
    }


def _repair_family_documented(
    repaired: list,
    *,
    names: set[str],
    keywords: tuple[str, ...],
) -> bool:
    entry_names = _repaired_entry_names(repaired)
    if entry_names & names:
        return True
    text = json.dumps(repaired).lower()
    return any(k in text for k in keywords)


def _feature_assembly_sources() -> str:
    parts = []
    for name in (
        'feature_blocks.py', 'alt_aggregates.py', 'warehouse_ops.py',
        'feature_pipeline.py', 'period_utils.py',
    ):
        path = Path('/root/project') / name
        if path.exists():
            parts.append(path.read_text())
    return '\n'.join(parts)


def _expected_prior_cycle_paid(conn, account_id: str, pred_month: str) -> int:
    """Honest prior-cycle payment flag per feature_availability.pdf."""
    prev_m = _prev_month(pred_month)
    pred_date = date.fromisoformat(f'{pred_month}-01')
    row = conn.execute(
        """SELECT due_date, paid_date, paid_status FROM invoices
           WHERE account_id=? AND invoice_month=?""",
        (account_id, prev_m),
    ).fetchone()
    if not row or not row[0]:
        return 0
    due_plus_3 = date.fromisoformat(row[0]) + timedelta(days=3)
    if due_plus_3 >= pred_date:
        return 0
    if row[2] != 'paid' or not row[1]:
        return 0
    if date.fromisoformat(row[1]) >= pred_date:
        return 0
    return 1


def _buggy_prior_cycle_paid(conn, account_id: str, pred_month: str) -> int:
    """Starter pipeline: paid_status only, ignoring due_date + 3 days rule."""
    prev_m = _prev_month(pred_month)
    row = conn.execute(
        "SELECT paid_status FROM invoices WHERE account_id=? AND invoice_month=?",
        (account_id, prev_m),
    ).fetchone()
    return 1 if row and row[0] == 'paid' else 0


def _selected_features() -> set[str]:
    assert FEATURES_PATH.exists(), 'selected_features.txt not found'
    return {
        line.strip().lower()
        for line in FEATURES_PATH.read_text().splitlines()
        if line.strip()
    }


@pytest.fixture(scope='session', autouse=True)
def _clean_output_dir():
    """Remove stale agent artifacts before the verifier run."""
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    yield


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: PIPELINE RUNS SUCCESSFULLY (patched files must be executable)
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineRuns:
    def test_train_model_runs_without_error(self):
        """The repaired train_model.py must execute successfully end-to-end."""
        result = subprocess.run(
            [sys.executable, '/root/project/train_model.py',
             '--config', str(CONFIG_PATH)],
            capture_output=True, text=True, timeout=180
        )
        assert result.returncode == 0, (
            f"train_model.py exited with code {result.returncode}.\n"
            f"STDOUT:\n{result.stdout[-2000:]}\n"
            f"STDERR:\n{result.stderr[-2000:]}"
        )

    def test_output_files_written_by_pipeline(self):
        """After pipeline run, all four output files must exist."""
        for p in [LEAKAGE_AUDIT_PATH, BACKTEST_PATH, HOLDOUT_PATH, FEATURES_PATH]:
            assert p.exists(), (
                f"train_model.py ran successfully but did not write {p}. "
                "The repaired script must write all four output files."
            )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: NO LEAKY FEATURES IN SELECTED_FEATURES.TXT
# ─────────────────────────────────────────────────────────────────────────────

class TestNoLeakyFeatures:
    def _get_selected_features(self):
        assert FEATURES_PATH.exists(), "selected_features.txt not found"
        return {line.strip().lower() for line in FEATURES_PATH.read_text().splitlines()
                if line.strip()}

    def test_selected_features_match_pipeline_columns(self):
        """selected_features.txt must reflect the patched pipeline, not a static list."""
        selected = self._get_selected_features()
        fp = _import_pipeline()
        config = _load_config()
        train_cols = {
            c.lower()
            for c in fp.build_features(config).columns
            if c not in ('account_id', 'prediction_month', 'churned_500')
        }
        holdout_cols = {
            c.lower()
            for c in fp.build_holdout_features(config).columns
            if c not in ('account_id', 'prediction_month')
        }
        assert train_cols == holdout_cols, (
            "Training and holdout feature pipelines must expose the same model columns. "
            f"train_only={sorted(train_cols - holdout_cols)}, "
            f"holdout_only={sorted(holdout_cols - train_cols)}"
        )
        assert selected == train_cols, (
            "selected_features.txt must exactly match the model columns built by the "
            f"patched pipeline. expected={sorted(train_cols)}, got={sorted(selected)}"
        )

    def test_prohibited_closure_classification_not_selected(self):
        feats = self._get_selected_features()
        assert 'f04' not in feats, (
            "f04 (case closure classification) must not be in selected_features.txt. "
            "Per feature_availability.pdf this family is PROHIBITED."
        )

    def test_prohibited_advance_charge_not_selected(self):
        feats = self._get_selected_features()
        assert 'f07' not in feats, (
            "f07 (advance billing-cycle charge) must not be selected. "
            "Per feature_availability.pdf this family is PROHIBITED."
        )

    def test_prohibited_post_period_drift_not_selected(self):
        feats = self._get_selected_features()
        bad = feats & {'f09', 'f10'}
        assert not bad, (
            f"Post-period ledger features must not be selected: {bad}. "
            "Per feature_availability.pdf these families are PROHIBITED."
        )

    def test_in_period_settlement_not_selected(self):
        feats = self._get_selected_features()
        assert 'f06' not in feats, (
            "f06 (in-period billing settlement) must not be selected. "
            "Per feature_availability.pdf this family is NOT available at period open."
        )

    def test_drop_only_starter_columns_not_selected(self):
        feats = self._get_selected_features()
        remaining_bad = feats & DROP_ONLY_FEATURE_NAMES
        assert not remaining_bad, (
            f"PROHIBITED starter columns still in selected_features.txt: {remaining_bad}. "
            "Map each pipeline column to feature_availability.pdf and remove every "
            "PROHIBITED / NOT-available family."
        )

    def test_supplementary_aggregates_not_selected_with_primary(self):
        """At most one column per rolling family; do not keep alt-module duplicates."""
        feats = self._get_selected_features()
        usage = _selected_from_family(feats, USAGE_FEATURE_CANDIDATES)
        tickets = _selected_from_family(feats, TICKET_COUNT_CANDIDATES)
        assert len(usage) == 1, (
            f"Keep exactly one rolling engagement column (f02 or f12). Found: {usage or 'none'}."
        )
        assert len(tickets) == 1, (
            f"Keep exactly one case-volume column (f03 or f13). Found: {tickets or 'none'}."
        )
        assert not (feats & {'f02', 'f12'} == {'f02', 'f12'}), (
            "Do not keep both f02 and f12 — pick one honest engagement implementation."
        )
        assert not (feats & {'f03', 'f13'} == {'f03', 'f13'}), (
            "Do not keep both f03 and f13 — pick one honest case-volume implementation."
        )

    def test_rolling_engagement_aggregate_selected(self):
        feats = self._get_selected_features()
        usage_feats = _selected_from_family(feats, USAGE_FEATURE_CANDIDATES)
        assert len(usage_feats) == 1, (
            "selected_features.txt must include exactly one rolling engagement column (f02 or f12)."
        )

    def test_case_volume_selected(self):
        feats = self._get_selected_features()
        ticket_feats = _selected_from_family(feats, TICKET_COUNT_CANDIDATES)
        assert len(ticket_feats) == 1, (
            "selected_features.txt must include exactly one case-volume column (f03 or f13)."
        )

    def test_at_least_one_feature_kept(self):
        feats = self._get_selected_features()
        assert len(feats) >= 1, (
            "selected_features.txt is empty. At least one honest feature must be kept."
        )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: VALUE-LEVEL FEATURE INTEGRITY
# ─────────────────────────────────────────────────────────────────────────────

class TestFeatureValueIntegrity:
    def _feature_matrix(self):
        fp = _import_pipeline()
        return fp.build_features(_load_config())

    def test_no_closed_churn_disposition_in_feature_matrix(self):
        """Post-outcome disposition codes must not appear in any feature column."""
        df = self._feature_matrix()
        for col in df.columns:
            if df[col].dtype == object or df[col].dtype.name == 'string':
                values = df[col].astype(str).str.upper()
                assert not values.str.contains('CLOSED_CHURN', na=False).any(), (
                    f"Column '{col}' contains CLOSED_CHURN disposition codes. "
                    "Support ticket disposition metadata must not enter the feature matrix."
                )

    def test_usage_events_strictly_before_prediction_date(self):
        """Rolling engagement signal must exclude post-open activity."""
        df = self._feature_matrix()
        selected = _selected_features()
        event_col = _selected_column(df, selected, USAGE_FEATURE_CANDIDATES)
        assert event_col is not None, (
            "Selected model must include exactly one rolling engagement column (f02 or f12)."
        )
        selected = _selected_features()
        assert event_col.lower() in selected, (
            f"Usage column '{event_col}' is built in the pipeline but missing from "
            "selected_features.txt."
        )

        conn = sqlite3.connect(str(DB_PATH))
        try:
            for account_id, pred_month in ALL_CHURN_CASES:
                pred_date = f'{pred_month}-01'
                win_start = _window_start_str(pred_month)
                label_end = _label_end_str(pred_month)

                expected = conn.execute(
                    """SELECT COALESCE(SUM(event_count), 0) FROM product_events
                       WHERE account_id=? AND event_date >= ? AND event_date < ?""",
                    (account_id, win_start, pred_date),
                ).fetchone()[0]
                buggy = conn.execute(
                    """SELECT COALESCE(SUM(event_count), 0) FROM product_events
                       WHERE account_id=? AND event_date >= ? AND event_date <= ?""",
                    (account_id, win_start, label_end),
                ).fetchone()[0]
                assert int(expected) != int(buggy), (
                    f"Test data for {account_id}/{pred_month} does not distinguish "
                    "honest vs label-window usage sums."
                )

                row = df[
                    (df['account_id'] == account_id)
                    & (df['prediction_month'].astype(str) == pred_month)
                ]
                assert len(row) == 1, (
                    f"Expected one feature row for {account_id} / {pred_month}."
                )
                actual = int(row.iloc[0][event_col])
                assert actual == int(expected), (
                    f"{event_col} for {account_id}/{pred_month} is {actual}, "
                    f"but warehouse events strictly before {pred_date} sum to {expected}. "
                    "The rolling engagement signal must end strictly before period open."
                )
                assert actual != int(buggy), (
                    f"{event_col} for {account_id}/{pred_month} still matches the "
                    f"horizon-inclusive sum ({buggy}). Repair the activity window boundary."
                )
        finally:
            conn.close()

    def test_health_score_respects_prev_month_boundary(self):
        """Customer vitality score must not use readings from period open onward."""
        df = self._feature_matrix()
        health_col = _column_from_candidates(df, HEALTH_CANDIDATES)
        assert health_col is not None, (
            f"Feature matrix must include exactly one vitality column from {HEALTH_CANDIDATES}."
        )

        conn = sqlite3.connect(str(DB_PATH))
        try:
            for account_id, pred_month in ALL_CHURN_CASES:
                cutoff = _last_day_prev_month(pred_month)
                pred_date = f'{pred_month}-01'

                expected = conn.execute(
                    """SELECT health_score FROM customer_health_scores
                       WHERE account_id=? AND score_date <= ?
                       ORDER BY score_date DESC LIMIT 1""",
                    (account_id, cutoff),
                ).fetchone()
                leaky = conn.execute(
                    """SELECT health_score FROM customer_health_scores
                       WHERE account_id=? AND score_date <= ?
                       ORDER BY score_date DESC LIMIT 1""",
                    (account_id, pred_date),
                ).fetchone()
                assert expected is not None, (
                    f"Reference health score missing for {account_id}/{pred_month}."
                )
                assert leaky is not None and float(leaky[0]) != float(expected[0]), (
                    f"Test data for {account_id}/{pred_month} does not distinguish "
                    "honest vs prediction-day health scores."
                )

                row = df[
                    (df['account_id'] == account_id)
                    & (df['prediction_month'].astype(str) == pred_month)
                ]
                assert len(row) == 1
                actual = float(row.iloc[0][health_col])
                assert abs(actual - float(expected[0])) < 0.01, (
                    f"{health_col} for {account_id}/{pred_month} is {actual}, "
                    f"but the latest score on or before {cutoff} is {expected[0]}. "
                    "Per feature_availability.pdf: vitality scores must use "
                    "score_date <= last day of prior billing period only."
                )
                assert abs(actual - float(leaky[0])) >= 0.01, (
                    f"{health_col} for {account_id}/{pred_month} matches the leaky "
                    f"prediction-day score ({leaky[0]}). Cap scores at prev_month(P)."
                )
        finally:
            conn.close()

    def test_support_ticket_count_respects_prediction_boundary(self):
        """Case file volume must count only cases opened before period open."""
        df = self._feature_matrix()
        selected = _selected_features()
        ticket_col = _selected_column(df, selected, TICKET_COUNT_CANDIDATES)
        assert ticket_col is not None, (
            "Selected model must include exactly one case-volume column (f03 or f13)."
        )
        assert ticket_col.lower() in selected, (
            f"Ticket volume column '{ticket_col}' must appear in selected_features.txt."
        )

        conn = sqlite3.connect(str(DB_PATH))
        try:
            for account_id, pred_month in ALL_CHURN_CASES:
                pred_date = f'{pred_month}-01'
                win_start = _window_start_str(pred_month)
                label_end = _label_end_str(pred_month)

                expected = conn.execute(
                    """SELECT COUNT(*) FROM support_tickets
                       WHERE account_id=? AND ticket_created_at >= ?
                         AND ticket_created_at < ?""",
                    (account_id, win_start, pred_date),
                ).fetchone()[0]
                buggy = conn.execute(
                    """SELECT COUNT(*) FROM support_tickets
                       WHERE account_id=? AND ticket_created_at >= ?
                         AND ticket_created_at <= ?""",
                    (account_id, win_start, label_end),
                ).fetchone()[0]
                assert int(expected) != int(buggy), (
                    f"Test data for {account_id}/{pred_month} does not distinguish "
                    "honest vs label-window ticket counts."
                )

                row = df[
                    (df['account_id'] == account_id)
                    & (df['prediction_month'].astype(str) == pred_month)
                ]
                assert len(row) == 1
                actual = int(row.iloc[0][ticket_col])
                assert actual == int(expected), (
                    f"{ticket_col} for {account_id}/{pred_month} is {actual}, "
                    f"but warehouse counts {expected} tickets with "
                    f"ticket_created_at < {pred_date}."
                )
                assert actual != int(buggy), (
                    f"{ticket_col} for {account_id}/{pred_month} still matches the "
                    f"label-window count ({buggy}). Use ticket_created_at < prediction_date."
                )
        finally:
            conn.close()

    def test_prior_cycle_invoice_respects_due_date_rule(self):
        """Prior billing-cycle settlement must respect grace period and settlement timestamp."""
        df = self._feature_matrix()
        inv_col = _column_from_candidates(df, PRIOR_INVOICE_CANDIDATES)
        if inv_col is None:
            pytest.skip("No prior-cycle settlement column in feature matrix.")

        selected = _selected_features()
        if inv_col.lower() not in selected:
            pytest.skip("Prior-cycle invoice column not used in final model.")

        conn = sqlite3.connect(str(DB_PATH))
        try:
            for account_id, pred_month in ALL_CHURN_CASES:
                expected = _expected_prior_cycle_paid(conn, account_id, pred_month)
                buggy = _buggy_prior_cycle_paid(conn, account_id, pred_month)
                assert expected != buggy, (
                    f"Test data for {account_id}/{pred_month} does not distinguish "
                    "honest vs paid_status-only prior-cycle invoice flags."
                )

                row = df[
                    (df['account_id'] == account_id)
                    & (df['prediction_month'].astype(str) == pred_month)
                ]
                assert len(row) == 1
                actual = int(row.iloc[0][inv_col])
                assert actual == expected, (
                    f"{inv_col} for {account_id}/{pred_month} is {actual}, "
                    f"but the honest prior-cycle rule yields {expected}. "
                    "Per feature_availability.pdf: prior settlement requires grace period "
                    "elapsed and settlement timestamp before period open."
                )
                assert actual != buggy, (
                    f"{inv_col} for {account_id}/{pred_month} matches the leaky "
                    f"paid_status-only value ({buggy})."
                )
        finally:
            conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: LEAKAGE AUDIT JSON STRUCTURE AND CONTENT
# ─────────────────────────────────────────────────────────────────────────────

class TestLeakageAuditJson:
    def _get_audit(self):
        assert LEAKAGE_AUDIT_PATH.exists(), "leakage_audit.json not found"
        return json.loads(LEAKAGE_AUDIT_PATH.read_text())

    def test_required_keys_present(self):
        audit = self._get_audit()
        required = {
            'dropped_features', 'repaired_features', 'kept_features',
            'backtest_strategy', 'holdout_month', 'leakage_risk_summary',
        }
        missing = required - set(audit.keys())
        assert not missing, (
            f"leakage_audit.json is missing required keys: {missing}. "
            f"Found keys: {set(audit.keys())}"
        )

    def test_holdout_month_correct(self):
        audit = self._get_audit()
        assert str(audit.get('holdout_month', '')).strip() == HOLDOUT_MONTH, (
            f"holdout_month in leakage_audit.json should be '{HOLDOUT_MONTH}', "
            f"got '{audit.get('holdout_month')}'"
        )

    def test_dropped_features_is_list(self):
        audit = self._get_audit()
        assert isinstance(audit.get('dropped_features'), list), (
            "dropped_features in leakage_audit.json must be a list"
        )
        assert len(audit['dropped_features']) >= 1, (
            "dropped_features must contain at least one entry documenting a removed leaky feature"
        )

    def test_dropped_features_documents_forward_billing(self):
        audit = self._get_audit()
        names = [
            str(f.get('name', '') if isinstance(f, dict) else f).lower()
            for f in audit.get('dropped_features', [])
        ]
        text = json.dumps(audit.get('dropped_features', [])).lower()
        assert any(
            k in n or k in text for n in names
            for k in ('f07', 'advance', 'forward', 'billing-cycle charge')
        ), (
            "leakage_audit.json must document removal of advance billing-cycle charge. "
            f"Currently documented: {names}"
        )

    def test_dropped_features_documents_evaluation_mrr(self):
        audit = self._get_audit()
        names = [
            str(f.get('name', '') if isinstance(f, dict) else f).lower()
            for f in audit.get('dropped_features', [])
        ]
        text = json.dumps(audit.get('dropped_features', [])).lower()
        assert any(
            k in n or k in text for n in names
            for k in ('f09', 'f10', 'post-period', 'ledger drift', 'period-span', 'ledger comparison')
        ), (
            "leakage_audit.json must document removal of post-period ledger features. "
            f"Currently documented: {names}"
        )

    def test_dropped_features_documents_ticket_disposition(self):
        audit = self._get_audit()
        names = [
            str(f.get('name', '') if isinstance(f, dict) else f).lower()
            for f in audit.get('dropped_features', [])
        ]
        text = json.dumps(audit.get('dropped_features', [])).lower()
        assert any(
            k in n or k in text for n in names
            for k in ('f04', 'closure', 'classification', 'disposition')
        ), (
            "leakage_audit.json must document removal of case closure classification. "
            f"Currently documented: {names}"
        )

    def test_dropped_features_documents_current_cycle_invoice(self):
        audit = self._get_audit()
        names = [
            str(f.get('name', '') if isinstance(f, dict) else f).lower()
            for f in audit.get('dropped_features', [])
        ]
        text = json.dumps(audit.get('dropped_features', [])).lower()
        assert any(
            k in n or k in text for n in names
            for k in ('f06', 'in-period', 'current', 'settlement')
        ), (
            "leakage_audit.json must document removal of in-period billing settlement. "
            f"Currently documented: {names}"
        )

    def test_dropped_features_documents_usage_window_repair(self):
        audit = self._get_audit()
        text = json.dumps(audit).lower()
        assert any(
            k in text for k in ('f02', 'f12', 'engagement', 'eng_roll', 'activity', 'window')
        ), (
            "leakage_audit.json must document the rolling engagement window repair."
        )

    def test_audit_documents_health_score_boundary_repair(self):
        audit = self._get_audit()
        text = json.dumps(audit).lower()
        assert any(k in text for k in ('f08', 'vitality', 'health', 'prior billing', 'previous')), (
            "leakage_audit.json must document the customer vitality score boundary repair."
        )

    def test_audit_documents_ticket_volume_boundary_repair(self):
        audit = self._get_audit()
        text = json.dumps(audit).lower()
        assert any(k in text for k in ('f03', 'f13', 'case', 'volume', 'case_vol')), (
            "leakage_audit.json must document the case file volume window repair."
        )

    def test_audit_documents_prior_cycle_invoice_repair(self):
        audit = self._get_audit()
        text = json.dumps(audit).lower()
        assert any(
            k in text for k in ('f05', 'prior', 'settlement', 'grace', 'due_date', 'prv_settle')
        ), (
            "leakage_audit.json must document the prior billing-cycle settlement repair."
        )

    def test_audit_lists_repaired_boundary_features(self):
        audit = self._get_audit()
        repaired = audit.get('repaired_features', [])
        assert isinstance(repaired, list) and len(repaired) >= 4, (
            "repaired_features must document every conditional family whose boundary "
            "logic you corrected, with name, pdf_family, reason, and source fields."
        )
        for entry in repaired:
            assert isinstance(entry, dict), "Each repaired_features entry must be an object."
            assert str(entry.get('pdf_family', '')).strip(), (
                "Each repaired feature must cite the PDF family name in pdf_family."
            )
        assert _repair_family_documented(
            repaired,
            names=ENGAGEMENT_REPAIR_NAMES,
            keywords=('engagement', 'activity', 'window'),
        ), "repaired_features must document the rolling engagement boundary fix."
        assert _repair_family_documented(
            repaired,
            names=VITALITY_REPAIR_NAMES,
            keywords=('vitality', 'health', 'prior billing', 'previous'),
        ), "repaired_features must document the customer vitality boundary fix."
        assert _repair_family_documented(
            repaired,
            names=CASE_VOLUME_REPAIR_NAMES,
            keywords=('case', 'volume', 'case_vol'),
        ), "repaired_features must document the case file volume boundary fix."
        assert _repair_family_documented(
            repaired,
            names=PRIOR_SETTLEMENT_REPAIR_NAMES,
            keywords=('prior', 'settlement', 'grace', 'due_date', 'prv_settle'),
        ), "repaired_features must document the prior-cycle settlement boundary fix."

    def test_boundary_fixes_not_only_in_kept_features(self):
        """Alternate honest columns (e.g. f12/f13) count as repairs, not untouched keeps."""
        audit = self._get_audit()
        selected = _selected_features()
        repaired_names = _repaired_entry_names(audit.get('repaired_features', []))
        kept = {str(k).strip().lower() for k in audit.get('kept_features', [])}

        alt_engagement = 'f12' in selected and 'f02' not in selected
        alt_case_volume = 'f13' in selected and 'f03' not in selected

        if alt_engagement:
            assert 'f12' in repaired_names, (
                "f12 implements a repaired rolling engagement family. "
                "Document it in repaired_features with pdf_family — not only in kept_features."
            )
            assert 'f12' not in kept or 'f12' in repaired_names

        if alt_case_volume:
            assert 'f13' in repaired_names, (
                "f13 implements a repaired case file volume family. "
                "Document it in repaired_features with pdf_family — not only in kept_features."
            )
            assert 'f13' not in kept or 'f13' in repaired_names

    def test_dropped_features_documents_next_invoice(self):
        """Backward-compatible alias for forward-cycle billing documentation."""
        self.test_dropped_features_documents_forward_billing()

    def test_dropped_features_documents_label_delta(self):
        """Backward-compatible alias for evaluation-period revenue documentation."""
        self.test_dropped_features_documents_evaluation_mrr()

    def test_kept_features_is_list(self):
        audit = self._get_audit()
        assert isinstance(audit.get('kept_features'), list), (
            "kept_features in leakage_audit.json must be a list"
        )
        assert len(audit['kept_features']) >= 1, (
            "kept_features must contain at least one honest feature"
        )

    def test_dropped_features_cover_prohibited_columns(self):
        audit = self._get_audit()
        dropped = audit.get('dropped_features', [])
        names = {
            str(entry.get('name', '')).strip().lower()
            for entry in dropped
            if isinstance(entry, dict)
        }
        text = json.dumps(dropped).lower()
        missing = sorted(
            col for col in DROP_ONLY_FEATURE_NAMES
            if col not in names and col not in text
        )
        assert not missing, (
            "leakage_audit.json must document removal of every PROHIBITED / "
            f"NOT-available starter column. Missing: {missing}"
        )

    def test_repaired_entries_are_substantive(self):
        audit = self._get_audit()
        repaired = audit.get('repaired_features', [])
        for entry in repaired:
            assert isinstance(entry, dict), "Each repaired_features entry must be an object."
            assert str(entry.get('name', '')).strip(), (
                "Each repaired feature must include a name."
            )
            assert len(str(entry.get('reason', '')).strip()) >= 25, (
                "Each repaired feature needs a substantive reason describing the boundary fix."
            )
            assert str(entry.get('source', '')).strip(), (
                "Each repaired feature must identify the warehouse fields involved."
            )

    def test_repaired_and_kept_features_disjoint(self):
        audit = self._get_audit()
        repaired = _repaired_entry_names(audit.get('repaired_features', []))
        kept = {
            str(name).strip().lower()
            for name in audit.get('kept_features', [])
            if str(name).strip()
        }
        overlap = repaired & kept
        assert not overlap, (
            f"A column cannot be both repaired and kept: {sorted(overlap)}. "
            "Boundary-fixed columns belong in repaired_features only."
        )

    def test_leakage_risk_summary_non_empty(self):
        audit = self._get_audit()
        summary = str(audit.get('leakage_risk_summary', '')).strip()
        assert len(summary) >= 30, (
            "leakage_risk_summary must be a non-trivial description of the leakage found "
            f"(got: '{summary}')"
        )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: BACKTEST USES TEMPORAL WINDOWS (NOT RANDOM SPLIT)
# ─────────────────────────────────────────────────────────────────────────────

class TestBacktestTemporalSplit:
    def _get_backtest(self):
        assert BACKTEST_PATH.exists(), "backtest_results.csv not found"
        return pd.read_csv(BACKTEST_PATH)

    def test_backtest_has_required_columns(self):
        df = self._get_backtest()
        required = {
            'validate_month', 'n_train', 'n_val', 'n_positive', 'validation_auc',
        }
        missing = required - set(df.columns)
        assert not missing, (
            f"backtest_results.csv is missing columns: {missing}. "
            f"Found: {list(df.columns)}"
        )

    def test_backtest_validate_months_match_windows_csv(self):
        """Backtest rows must correspond to every window in backtest_windows.csv."""
        df       = self._get_backtest()
        bw       = pd.read_csv(BACKTEST_WINDOWS_CSV)
        expected = set(bw['validate_month'].astype(str))
        actual   = set(df['validate_month'].astype(str))
        assert actual == expected, (
            f"backtest_results.csv validate_month values must match backtest_windows.csv. "
            f"Expected {expected}, got {actual}. "
            "Use temporal split: train on all months <= train_end_month, "
            "validate on validate_month from backtest_windows.csv."
        )

    def test_backtest_has_all_windows(self):
        df = self._get_backtest()
        assert len(df) == len(EXPECTED_VALIDATE_MONTHS), (
            f"backtest_results.csv has {len(df)} row(s); "
            f"expected {len(EXPECTED_VALIDATE_MONTHS)} rolling-window rows "
            f"matching backtest_windows.csv."
        )

    def test_holdout_month_not_in_backtest_as_validate(self):
        """April 2026 must not appear as a validate_month in backtest results."""
        df = self._get_backtest()
        validate_months = set(df['validate_month'].astype(str))
        assert HOLDOUT_MONTH not in validate_months, (
            f"holdout month {HOLDOUT_MONTH} must not appear as validate_month in "
            f"backtest_results.csv. The holdout month is for final predictions only."
        )

    def test_backtest_row_counts_exact(self):
        df = self._get_backtest()
        for val_month, expected in EXPECTED_BACKTEST_COUNTS.items():
            row = df[df['validate_month'].astype(str) == val_month]
            assert len(row) == 1, (
                f"Expected exactly one backtest row for validate_month={val_month}."
            )
            assert int(row.iloc[0]['n_train']) == expected['n_train'], (
                f"validate_month={val_month}: n_train should be {expected['n_train']}, "
                f"got {row.iloc[0]['n_train']}."
            )
            assert int(row.iloc[0]['n_val']) == expected['n_val'], (
                f"validate_month={val_month}: n_val should be {expected['n_val']}, "
                f"got {row.iloc[0]['n_val']}."
            )

    def test_backtest_row_counts_positive(self):
        df = self._get_backtest()
        assert (df['n_train'] > 0).all(), (
            "Every backtest row must have n_train > 0."
        )
        assert (df['n_val'] > 0).all(), (
            "Every backtest row must have n_val > 0."
        )
        assert (df['n_positive'] >= 0).all(), (
            "n_positive must be non-negative in every backtest row."
        )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: HOLDOUT PREDICTIONS (APRIL 2026 ONLY, CORRECT ROW COUNT)
# ─────────────────────────────────────────────────────────────────────────────

class TestHoldoutPredictions:
    def _get_holdout(self):
        assert HOLDOUT_PATH.exists(), "holdout_predictions.parquet not found"
        return pq.read_table(str(HOLDOUT_PATH)).to_pandas()

    def test_holdout_has_required_columns(self):
        df = self._get_holdout()
        required = {'account_id', 'prediction_month', 'churn_probability', 'predicted_label'}
        missing = required - set(df.columns)
        assert not missing, (
            f"holdout_predictions.parquet is missing columns: {missing}. "
            f"Found: {list(df.columns)}"
        )

    def test_holdout_prediction_month_is_april_2026(self):
        """Every row in holdout_predictions.parquet must have prediction_month = 2026-04."""
        df = self._get_holdout()
        wrong = df[df['prediction_month'].astype(str) != HOLDOUT_MONTH]
        assert len(wrong) == 0, (
            f"holdout_predictions.parquet contains {len(wrong)} rows with "
            f"prediction_month != '{HOLDOUT_MONTH}'. "
            f"Values found: {df['prediction_month'].unique().tolist()}. "
            "Only April 2026 predictions should be in the holdout file."
        )

    def test_holdout_row_count_matches_accounts(self):
        """All 35 accounts must have exactly one holdout prediction row."""
        df = self._get_holdout()
        assert len(df) == EXPECTED_HOLDOUT_ROWS, (
            f"holdout_predictions.parquet has {len(df)} rows; expected {EXPECTED_HOLDOUT_ROWS}. "
            "Every account in the warehouse must have exactly one April 2026 prediction."
        )

    def test_holdout_no_duplicate_accounts(self):
        df = self._get_holdout()
        dupes = df[df.duplicated('account_id')]
        assert len(dupes) == 0, (
            f"holdout_predictions.parquet has {len(dupes)} duplicate account_id rows: "
            f"{dupes['account_id'].tolist()}. Each account must appear exactly once."
        )

    def test_churn_probability_in_range(self):
        df = self._get_holdout()
        out_of_range = df[(df['churn_probability'] < 0) | (df['churn_probability'] > 1)]
        assert len(out_of_range) == 0, (
            f"{len(out_of_range)} rows have churn_probability outside [0, 1]. "
            "Probabilities must be in [0.0, 1.0]."
        )

    def test_predicted_label_is_binary(self):
        df = self._get_holdout()
        bad = df[~df['predicted_label'].isin([0, 1])]
        assert len(bad) == 0, (
            f"{len(bad)} rows have predicted_label not in {{0, 1}}: "
            f"{df['predicted_label'].unique().tolist()}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7: HONEST AUC RANGE (lower bound only — see note on HONEST_AUC_LOW)
# ─────────────────────────────────────────────────────────────────────────────

class TestHonestAucRange:
    def _get_backtest(self):
        assert BACKTEST_PATH.exists(), "backtest_results.csv not found"
        return pd.read_csv(BACKTEST_PATH)

    def test_validation_auc_better_than_random(self):
        """Validation AUC must be above 0.50 (better than a random classifier)."""
        df  = self._get_backtest()
        bw  = pd.read_csv(BACKTEST_WINDOWS_CSV)
        val_months = set(bw['validate_month'].astype(str))
        rows = df[df['validate_month'].astype(str).isin(val_months)]
        if rows.empty:
            return

        min_auc = float(rows['validation_auc'].min())
        assert min_auc >= HONEST_AUC_LOW, (
            f"Minimum validation_auc is {min_auc:.4f}, which is at or below random chance. "
            f"The model should extract genuine signal from honest features such as f08 and f02."
        )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8: PIPELINE SOURCE INTEGRITY (no prohibited SQL patterns)
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineSourceIntegrity:
    def test_no_resolution_code_in_project_source(self):
        src = _feature_assembly_sources().lower()
        assert 'resolution_code' not in src, (
            "Project source still references resolution_code. "
            "PROHIBITED families must be excised from /root/project source, not only "
            "omitted from the final feature list."
        )

    def test_no_inclusive_horizon_window_in_source(self):
        """Starter wq_b/wq_c expose an inc=True path that leaks past period open."""
        src = _feature_assembly_sources().lower().replace(' ', '')
        assert 'inc=true' not in src, (
            "Feature assembly source still contains an inclusive horizon window "
            "(inc=True). Remove leaky aggregate paths from /root/project, not only "
            "from selected_features.txt."
        )

    def test_no_label_horizon_helpers_in_feature_assembly(self):
        """ts_he / pm_next tie starter features to the outcome observation window."""
        src = _feature_assembly_sources().lower()
        assert 'ts_he(' not in src and 'ts_he_month' not in src, (
            "Feature assembly still references label-horizon helpers (ts_he). "
            "Rolling features must end at period open per feature_availability.pdf."
        )
        assert 'pm_next' not in src, (
            "Feature assembly still references pm_next for engineered columns. "
            "Forward-cycle billing fields are not available at period open."
        )

    def test_no_shuffle_split_in_train_model(self):
        src = Path('/root/project/train_model.py').read_text().lower()
        assert 'shuffle=true' not in src.replace(' ', ''), (
            "train_model.py still uses shuffle=True. "
            "Backtesting must use temporal rolling splits from backtest_windows.csv."
        )

    def test_drop_columns_not_in_feature_matrix(self):
        df = _import_pipeline().build_features(_load_config())
        cols = set(df.columns)
        assert not cols & DROP_ONLY_FEATURE_NAMES, (
            f"Repaired feature matrix still builds PROHIBITED columns: {cols & DROP_ONLY_FEATURE_NAMES}."
        )
        assert not ('f02' in cols and 'f12' in cols), (
            "Feature matrix must not expose both f02 and f12 — keep one engagement implementation."
        )
        assert not ('f03' in cols and 'f13' in cols), (
            "Feature matrix must not expose both f03 and f13 — keep one case-volume implementation."
        )
