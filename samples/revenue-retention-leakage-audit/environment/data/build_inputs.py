"""
Generate deterministic input files for the revenue-retention-leakage-audit task.

35 SaaS accounts, data period Oct 2025 – May 2026.
Prediction months: Nov 2025 – Mar 2026 (training labels), Apr 2026 (holdout, no labels).

Leakage traps baked into feature_pipeline.py (obfuscated column names):
  1. billing_amt_fwd1      — joins invoice for prediction_month+1 (future billing cycle)
  2. mrr_chg_eval          — MRR change over label window (direct outcome leakage)
  3. snap_mrr_trend        — decoy evaluation-period snapshot delta (same family as #2)
  4. ticket_res_mode       — support disposition aggregate (NEVER per feature_availability.pdf)
  5. cycle0_paid_flag      — paid status of CURRENT month invoice (not due until month+15d)
  6. usage_evt_30d         — uses event_date <= label_end instead of < prediction_date
  7. cust_health_idx       — uses score_date <= prediction_date instead of last day of prev_month
  8. ticket_vol_30d        — counts tickets with ticket_created_at <= label_end (too permissive)
  9. inv_prev_paid_flag    — prior-cycle paid_status without due_date + 3 days < prediction_date

Data/build cache: 2026-06-08-hardened-v5

Bug in train_model.py:
  6. train_test_split(shuffle=True) — random split ignores temporal order
"""

import os
import sqlite3
import calendar
import json
from pathlib import Path
from datetime import date, timedelta

import numpy as np
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas

# ── Paths ──────────────────────────────────────────────────────────────────────

DATA_DIR    = Path('/root/data')
PROJECT_DIR = Path('/root/project')
DATA_DIR.mkdir(parents=True, exist_ok=True)
PROJECT_DIR.mkdir(parents=True, exist_ok=True)

# ── Deterministic RNG ──────────────────────────────────────────────────────────

RNG = np.random.default_rng(42)

# ── Account definitions ────────────────────────────────────────────────────────

# (account_id, company_name, segment, base_mrr_usd, signup_date)
ACCOUNTS = [
    ('acc_001', 'Meridian Analytics',  'Enterprise',  6000, '2022-03-15'),
    ('acc_002', 'BlueShift Systems',   'Enterprise',  5000, '2021-06-20'),
    ('acc_003', 'Nexus Cloud Co',      'Enterprise',  8000, '2020-11-01'),
    ('acc_004', 'Vertex Group',        'Enterprise',  7000, '2022-08-10'),
    ('acc_005', 'Pinnacle SaaS',       'Enterprise',  4500, '2023-01-05'),
    ('acc_006', 'Crestline Labs',      'Enterprise',  3500, '2023-05-22'),
    ('acc_007', 'Harbor Data Inc',     'Enterprise',  4000, '2022-12-01'),
    ('acc_008', 'Alpine Tech Group',   'Enterprise',  3200, '2023-07-18'),
    ('acc_009', 'Redwood Analytics',   'Mid-Market',  2400, '2022-09-30'),
    ('acc_010', 'Sunbridge Co',        'Mid-Market',  2000, '2023-02-14'),
    ('acc_011', 'IronGate Solutions',  'Mid-Market',  1800, '2022-04-07'),
    ('acc_012', 'CoralPath Inc',       'Mid-Market',  1500, '2023-06-25'),
    ('acc_013', 'Stillwater SaaS',     'Mid-Market',  2200, '2021-11-30'),
    ('acc_014', 'Lakeview Digital',    'Mid-Market',  1100, '2022-07-12'),
    ('acc_015', 'Oakridge Systems',    'Mid-Market',  1600, '2023-03-08'),
    ('acc_016', 'Fairbanks Cloud',     'Mid-Market',  1300, '2022-10-19'),
    ('acc_017', 'Thornton Tech',       'Mid-Market',  1700, '2023-01-24'),
    ('acc_018', 'Cascade Digital',     'Mid-Market',  1400, '2022-05-30'),
    ('acc_019', 'Summit Analytics',    'Mid-Market',  1900, '2023-08-05'),
    ('acc_020', 'Valley Cloud',        'Mid-Market',  2100, '2022-02-17'),
    ('acc_021', 'Briar Tech',          'Mid-Market',   900, '2023-04-11'),
    ('acc_022', 'Driftwood SaaS',      'Mid-Market',  1200, '2022-11-23'),
    ('acc_023', 'Pebble Labs',         'SMB',          580, '2024-01-10'),
    ('acc_024', 'Elm Street Tech',     'SMB',          450, '2023-09-15'),  # MRR<500 never fires
    ('acc_025', 'Cedar Analytics',     'SMB',          550, '2024-02-20'),
    ('acc_026', 'Maple Data Co',       'SMB',          520, '2023-10-05'),
    ('acc_027', 'Birch Systems',       'SMB',          600, '2024-03-28'),
    ('acc_028', 'Fern Cloud',          'SMB',          480, '2023-11-12'),  # MRR<500 never fires
    ('acc_029', 'Willow Tech',         'SMB',          530, '2024-04-15'),
    ('acc_030', 'Aspen Analytics',     'SMB',          560, '2024-01-22'),
    ('acc_031', 'Hazel SaaS',          'SMB',          490, '2023-12-10'),  # MRR<500 never fires
    ('acc_032', 'Spruce Data',         'SMB',          610, '2023-12-01'),
    ('acc_033', 'Juniper Cloud',       'SMB',          570, '2024-02-14'),
    ('acc_034', 'Larch Systems',       'SMB',          540, '2023-09-28'),
    ('acc_035', 'Sequoia Tech',        'SMB',          590, '2024-03-10'),
]

ACCOUNT_MAP = {a[0]: a for a in ACCOUNTS}

# ── Churn events: (account_id, prediction_month) → label=1 ────────────────────

CHURN_EVENTS = {
    # 2025-11 (7 events, 20%)
    ('acc_002', '2025-11'), ('acc_004', '2025-11'), ('acc_012', '2025-11'),
    ('acc_016', '2025-11'), ('acc_025', '2025-11'), ('acc_029', '2025-11'),
    ('acc_033', '2025-11'),
    # 2025-12 (7 events, 20%)
    ('acc_001', '2025-12'), ('acc_006', '2025-12'), ('acc_011', '2025-12'),
    ('acc_018', '2025-12'), ('acc_026', '2025-12'), ('acc_030', '2025-12'),
    ('acc_034', '2025-12'),
    # 2026-01 (6 events, 17%)
    ('acc_003', '2026-01'), ('acc_007', '2026-01'), ('acc_014', '2026-01'),
    ('acc_019', '2026-01'), ('acc_027', '2026-01'), ('acc_032', '2026-01'),
    # 2026-02 (6 events, 17%)
    ('acc_005', '2026-02'), ('acc_008', '2026-02'), ('acc_013', '2026-02'),
    ('acc_021', '2026-02'), ('acc_023', '2026-02'), ('acc_035', '2026-02'),
    # 2026-03 (4 events, 11%)
    ('acc_009', '2026-03'), ('acc_015', '2026-03'), ('acc_020', '2026-03'),
    ('acc_022', '2026-03'),
}

# Base daily event rates per account
BASE_EVENT_RATES = {
    'acc_001': 950, 'acc_002': 800, 'acc_003': 1500, 'acc_004': 1100,
    'acc_005': 700, 'acc_006': 600, 'acc_007': 850, 'acc_008': 550,
    'acc_009': 380, 'acc_010': 320, 'acc_011': 290, 'acc_012': 250,
    'acc_013': 360, 'acc_014': 200, 'acc_015': 270, 'acc_016': 220,
    'acc_017': 280, 'acc_018': 240, 'acc_019': 310, 'acc_020': 340,
    'acc_021': 170, 'acc_022': 230,
    'acc_023':  90, 'acc_024':  65, 'acc_025':  80, 'acc_026':  75,
    'acc_027':  95, 'acc_028':  60, 'acc_029':  85, 'acc_030':  88,
    'acc_031':  62, 'acc_032': 100, 'acc_033':  82, 'acc_034':  78,
    'acc_035':  92,
}

# ── Date helpers ───────────────────────────────────────────────────────────────

def month_first(ym: str) -> date:
    y, m = int(ym[:4]), int(ym[5:])
    return date(y, m, 1)

def month_last(ym: str) -> date:
    y, m = int(ym[:4]), int(ym[5:])
    return date(y, m, calendar.monthrange(y, m)[1])

def next_month(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:])
    if m == 12:
        return f'{y+1}-01'
    return f'{y}-{m+1:02d}'

def prev_month(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:])
    if m == 1:
        return f'{y-1}-12'
    return f'{y}-{m-1:02d}'

def label_end_date(pred_month: str) -> date:
    return month_first(pred_month) + timedelta(days=30)

def label_end_month(pred_month: str) -> str:
    return label_end_date(pred_month).strftime('%Y-%m')

# Prediction and data periods
TRAIN_MONTHS   = ['2025-11', '2025-12', '2026-01', '2026-02', '2026-03']
HOLDOUT_MONTH  = '2026-04'
ALL_PRED_MONTHS = TRAIN_MONTHS + [HOLDOUT_MONTH]

# Snapshot months: prev month before first prediction through label_end of last prediction
SNAP_MONTHS = ['2025-10', '2025-11', '2025-12', '2026-01', '2026-02', '2026-03', '2026-04', '2026-05']

# ── Build SQLite database ──────────────────────────────────────────────────────

db_path = DATA_DIR / 'revenue_warehouse.sqlite'
if db_path.exists():
    db_path.unlink()
conn = sqlite3.connect(str(db_path))

conn.executescript("""
CREATE TABLE accounts (
    account_id   TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    segment      TEXT NOT NULL,
    base_mrr_usd REAL NOT NULL,
    signup_date  TEXT NOT NULL
);

CREATE TABLE subscription_snapshots (
    snapshot_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id     TEXT NOT NULL,
    snapshot_month TEXT NOT NULL,
    mrr_usd        REAL NOT NULL,
    snapshot_date  TEXT NOT NULL
);

CREATE TABLE invoices (
    invoice_id   TEXT PRIMARY KEY,
    account_id   TEXT NOT NULL,
    invoice_month TEXT NOT NULL,
    amount_usd   REAL NOT NULL,
    due_date     TEXT NOT NULL,
    paid_date    TEXT,
    paid_status  TEXT NOT NULL,
    finalized_at TEXT NOT NULL
);

CREATE TABLE product_events (
    event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    event_date  TEXT NOT NULL,
    event_count INTEGER NOT NULL
);

CREATE TABLE support_tickets (
    ticket_id        TEXT PRIMARY KEY,
    account_id       TEXT NOT NULL,
    ticket_created_at TEXT NOT NULL,
    ticket_closed_at  TEXT,
    resolution_code   TEXT,
    priority          TEXT NOT NULL
);

CREATE TABLE customer_health_scores (
    score_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id   TEXT NOT NULL,
    score_date   TEXT NOT NULL,
    health_score REAL NOT NULL
);

CREATE TABLE labels (
    label_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id        TEXT NOT NULL,
    prediction_month  TEXT NOT NULL,
    prediction_date   TEXT NOT NULL,
    label_window_start TEXT NOT NULL,
    label_window_end   TEXT NOT NULL,
    mrr_loss_usd      REAL NOT NULL,
    churned_500       INTEGER NOT NULL
);
""")

# ── accounts ──────────────────────────────────────────────────────────────────

for acc in ACCOUNTS:
    conn.execute(
        "INSERT INTO accounts VALUES (?,?,?,?,?)",
        (acc[0], acc[1], acc[2], acc[3], acc[4])
    )

# ── subscription_snapshots ────────────────────────────────────────────────────
# One row per (account, month). mrr=0 for the month AFTER a churn event.

for snap_month in SNAP_MONTHS:
    snap_date = month_first(snap_month).strftime('%Y-%m-%d')
    for acc in ACCOUNTS:
        aid, _, _, base_mrr, _ = acc
        # Which training month does this snapshot correspond to as "next month"?
        prev_m = prev_month(snap_month)
        if (aid, prev_m) in CHURN_EVENTS:
            # This account churned in prev_m, so snap for snap_month = 0
            mrr = 0.0
        else:
            mrr = float(base_mrr)
        conn.execute(
            "INSERT INTO subscription_snapshots (account_id,snapshot_month,mrr_usd,snapshot_date) VALUES (?,?,?,?)",
            (aid, snap_month, mrr, snap_date)
        )

# ── invoices ──────────────────────────────────────────────────────────────────
# Monthly invoices for 2025-10 through 2026-05.
# Leakage trap: invoice for prediction_month+1 has amount=0 for churned accounts.
# paid_status for prediction_month is 'overdue' for churning accounts (not 'paid').

INV_MONTHS = SNAP_MONTHS  # same range

for inv_month in INV_MONTHS:
    first = month_first(inv_month)
    finalized = (first + timedelta(days=1)).strftime('%Y-%m-%d')

    for acc in ACCOUNTS:
        aid, _, _, base_mrr, _ = acc
        prev_m = prev_month(inv_month)
        pred_m_for_inv = next_month(inv_month)
        # Prior-cycle invoice trap: for accounts churning in pred_m_for_inv, the
        # prev-month invoice has due_date + 3 >= prediction_date while the warehouse
        # export shows paid_status='paid' (finalized after prediction_date).
        is_prior_trap = (
            pred_m_for_inv in TRAIN_MONTHS
            and (aid, pred_m_for_inv) in CHURN_EVENTS
        )

        if (aid, prev_m) in CHURN_EVENTS:
            amount = 0.0
            paid_date = None
            paid_status = 'cancelled'
            due = (first + timedelta(days=15)).strftime('%Y-%m-%d')
        elif is_prior_trap:
            amount = float(base_mrr)
            last_d = month_last(inv_month)
            due = (last_d - timedelta(days=1)).strftime('%Y-%m-%d')
            pred_d = month_first(pred_m_for_inv)
            paid_date = (pred_d + timedelta(days=5)).strftime('%Y-%m-%d')
            paid_status = 'paid'
        else:
            amount = float(base_mrr)
            due = (first + timedelta(days=15)).strftime('%Y-%m-%d')
            if inv_month in TRAIN_MONTHS and (aid, inv_month) in CHURN_EVENTS:
                paid_date = None
                paid_status = 'overdue'
            else:
                paid_date = (first + timedelta(days=18)).strftime('%Y-%m-%d')
                paid_status = 'paid'

        inv_id = f"INV-{aid}-{inv_month}"
        conn.execute(
            "INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?)",
            (inv_id, aid, inv_month, amount, due, paid_date, paid_status, finalized)
        )

# ── product_events ────────────────────────────────────────────────────────────
# One row per (account, date) for 2025-10-01 through 2026-05-01.
# Event counts decrease before/during the label window for churning accounts.
# This creates two kinds of signal:
#   - Honest: events in [prediction_date-30d, prediction_date) are lower for churners
#   - Leaky:  events in [prediction_date, label_end] are near-zero for churners

start_date = date(2025, 10, 1)
end_date   = date(2026, 5, 1)

# Pre-compute which (account, date) falls in which leakage/honest zone
def get_event_multiplier(aid, d):
    """Return (prior_multiplier, label_multiplier) for a given account and date."""
    for pm in ALL_PRED_MONTHS:
        pred_date = month_first(pm)
        window_start = pred_date - timedelta(days=30)
        lbl_end      = label_end_date(pm)
        if (aid, pm) in CHURN_EVENTS:
            if window_start <= d < pred_date:
                return 0.42   # declining engagement — honest signal
            if pred_date <= d <= lbl_end:
                return 0.04   # near-zero during label window — leaky signal
    return 1.0

event_rows = []
cur = start_date
while cur <= end_date:
    ds = cur.strftime('%Y-%m-%d')
    for acc in ACCOUNTS:
        aid = acc[0]
        base = BASE_EVENT_RATES[aid]
        mult = get_event_multiplier(aid, cur)
        # lognormal noise (sigma=0.4)
        count = max(0, int(round(base * mult * float(np.exp(RNG.normal(0, 0.40))))))
        event_rows.append((aid, 'platform_usage', ds, count))
    cur += timedelta(days=1)

conn.executemany(
    "INSERT INTO product_events (account_id,event_type,event_date,event_count) VALUES (?,?,?,?)",
    event_rows
)

# ── support_tickets ───────────────────────────────────────────────────────────
# Leakage trap: churning accounts have tickets with resolution_code='CLOSED_CHURN'
# where ticket_closed_at falls INSIDE the label window (after prediction_date).
# The buggy pipeline aggregates resolution_code from closed tickets without
# respecting the PDF ban, so it sees post-outcome codes such as CLOSED_CHURN.
# The correct pipeline omits ticket_resolution_code entirely.

ticket_id_counter = 1
ticket_rows = []

for acc in ACCOUNTS:
    aid = acc[0]

    # Each account gets 1-3 'normal' tickets in the training period
    n_normal = int(RNG.integers(1, 4))
    for _ in range(n_normal):
        # Create ticket 40-90 days before a random prediction month
        pm_idx = int(RNG.integers(0, len(TRAIN_MONTHS)))
        pm     = TRAIN_MONTHS[pm_idx]
        pred_d = month_first(pm)
        created_days_before = int(RNG.integers(40, 91))
        created = (pred_d - timedelta(days=created_days_before)).strftime('%Y-%m-%d')
        # Closed well before prediction date
        closed_days_after = int(RNG.integers(5, 25))
        closed = (date.fromisoformat(created) + timedelta(days=closed_days_after)).strftime('%Y-%m-%d')
        priority = RNG.choice(['low', 'medium', 'high'], p=[0.5, 0.35, 0.15])
        ticket_rows.append((
            f'TKT-{ticket_id_counter:04d}',
            aid, created, closed, 'RESOLVED', str(priority)
        ))
        ticket_id_counter += 1

    # Churning accounts get 1-2 'churn-signal' tickets
    churn_months_for_acc = [pm for (a, pm) in CHURN_EVENTS if a == aid]
    for pm in churn_months_for_acc:
        pred_d = month_first(pm)
        n_churn_tickets = int(RNG.integers(1, 3))
        for _ in range(n_churn_tickets):
            # Created 5-20 days before prediction date (within honest window)
            created_days = int(RNG.integers(5, 21))
            created = (pred_d - timedelta(days=created_days)).strftime('%Y-%m-%d')
            # Closed AFTER prediction date (inside label window) — LEAKY
            closed_days_after_pred = int(RNG.integers(5, 22))
            closed = (pred_d + timedelta(days=closed_days_after_pred)).strftime('%Y-%m-%d')
            priority = 'high'
            ticket_rows.append((
                f'TKT-{ticket_id_counter:04d}',
                aid, created, closed, 'CLOSED_CHURN', priority
            ))
            ticket_id_counter += 1

        # Label-window tickets created AFTER prediction_date inflate the buggy
        # ticket_vol_30d counter (which uses ticket_created_at <= label_end).
        for pm in churn_months_for_acc:
            pred_d = month_first(pm)
            label_end = label_end_date(pm)
            n_label_tickets = int(RNG.integers(1, 3))
            for _ in range(n_label_tickets):
                created_days = int(RNG.integers(3, 18))
                created = (pred_d + timedelta(days=created_days)).strftime('%Y-%m-%d')
                if date.fromisoformat(created) > label_end:
                    continue
                ticket_rows.append((
                    f'TKT-{ticket_id_counter:04d}',
                    aid, created, None, 'OPEN', 'medium'
                ))
                ticket_id_counter += 1

conn.executemany(
    "INSERT INTO support_tickets VALUES (?,?,?,?,?,?)",
    ticket_rows
)

# ── customer_health_scores ────────────────────────────────────────────────────
# One score per (account, end-of-month) for months 2025-09 through 2026-04.
# Churning accounts have lower health score in the month BEFORE their churn month.
# The honest signal: health at end of P-1 reflects declining engagement before churn in P.

SCORE_MONTHS = ['2025-09', '2025-10', '2025-11', '2025-12',
                '2026-01', '2026-02', '2026-03', '2026-04']

for score_month in SCORE_MONTHS:
    score_date = month_last(score_month).strftime('%Y-%m-%d')
    # For prediction in next_month(score_month), is this account churning?
    pred_m_for_score = next_month(score_month)
    for acc in ACCOUNTS:
        aid = acc[0]
        if (aid, pred_m_for_score) in CHURN_EVENTS:
            # Churning next month: declining health (honest signal)
            raw = float(RNG.normal(53.0, 16.0))
            health = float(np.clip(raw, 24.0, 78.0))
        else:
            # Healthy
            raw = float(RNG.normal(75.0, 13.0))
            health = float(np.clip(raw, 50.0, 94.0))
        conn.execute(
            "INSERT INTO customer_health_scores (account_id,score_date,health_score) VALUES (?,?,?)",
            (aid, score_date, round(health, 1))
        )

# Intra-month scores stamped on prediction day for churning accounts.
# These encode outcome-adjacent signal and must NOT be used: the PDF caps health
# scores at the last day of the month before prediction (prev_month(P)).
for pm in TRAIN_MONTHS:
    pred_date_str = month_first(pm).strftime('%Y-%m-%d')
    for aid, churn_pm in CHURN_EVENTS:
        if churn_pm != pm:
            continue
        conn.execute(
            "INSERT INTO customer_health_scores (account_id,score_date,health_score) VALUES (?,?,?)",
            (aid, pred_date_str, 25.0)
        )

# ── labels ────────────────────────────────────────────────────────────────────

for pm in TRAIN_MONTHS:
    pred_d   = month_first(pm)
    lbl_end  = label_end_date(pm)
    for acc in ACCOUNTS:
        aid, _, _, base_mrr, _ = acc
        is_churn = (aid, pm) in CHURN_EVENTS
        mrr_loss = float(base_mrr) if is_churn else 0.0
        churned  = 1 if (is_churn and base_mrr >= 500) else 0
        conn.execute(
            "INSERT INTO labels (account_id,prediction_month,prediction_date,"
            "label_window_start,label_window_end,mrr_loss_usd,churned_500) VALUES (?,?,?,?,?,?,?)",
            (aid, pm, pred_d.strftime('%Y-%m-%d'),
             pred_d.strftime('%Y-%m-%d'), lbl_end.strftime('%Y-%m-%d'),
             mrr_loss, churned)
        )

conn.commit()
conn.close()
print(f"revenue_warehouse.sqlite created: {len(ACCOUNTS)} accounts, "
      f"{len(TRAIN_MONTHS)} training months, {len(CHURN_EVENTS)} churn events")

# ── feature_availability.pdf ──────────────────────────────────────────────────

def gen_feature_availability_pdf(path):
    c = rl_canvas.Canvas(str(path), pagesize=A4)
    W, H = A4
    y = H - 60

    def line(txt, font='Helvetica', size=10, gap=14, x=50):
        nonlocal y
        c.setFont(font, size)
        c.drawString(x, y, txt)
        y -= gap

    def hline():
        nonlocal y
        c.setLineWidth(0.5)
        c.line(50, y + 4, W - 50, y + 4)
        y -= 6

    line("Feature Availability Reference — Abundant Revenue Platform", 'Helvetica-Bold', 13, 22)
    line("Version 2.1 · Effective October 2025", size=9, gap=20)
    line("PURPOSE", 'Helvetica-Bold', 11, 14)
    line("This document defines the exact availability timing for each feature family used in", gap=12)
    line("the MRR-loss churn prediction pipeline. A feature is available for a prediction made", gap=12)
    line("on date D only when the availability condition is satisfied strictly before D.", gap=18)

    line("FEATURE AVAILABILITY TABLE", 'Helvetica-Bold', 11, 14)
    line("Column headers: Feature Family | Available When", 'Helvetica-Oblique', 9, 14)
    hline()
    y -= 4

    rows = [
        ("Ledger balance at period open",
         "Use the recurring-revenue ledger reading from the billing period immediately "
         "before the prediction period begins."),
        ("Rolling engagement signal (30-day)",
         "Sum activity records whose timestamps fall strictly before the period open date. "
         "The window spans the 30 days ending at period open."),
        ("Case file volume (30-day rolling)",
         "Count case records opened in the 30-day window ending at period open. Only cases "
         "with open timestamps strictly before period open may be included."),
        ("Case closure classification",
         "PROHIBITED. Closure categories are assigned only after a case closes; for accounts "
         "entering the outcome window, closure typically occurs after period open and the "
         "category encodes outcome information."),
        ("Prior billing-cycle settlement indicator",
         "Available for the billing cycle before prediction only when (a) the stated due date "
         "plus a three-day grace period is strictly before period open, and (b) the settlement "
         "timestamp recorded in the warehouse is also strictly before period open."),
        ("In-period billing settlement indicator",
         "NOT available at period open. The current-period invoice is not due until mid-period."),
        ("Advance billing-cycle charge",
         "PROHIBITED. Charges for the billing cycle after the prediction period are not "
         "finalized at period open."),
        ("Customer vitality score",
         "Use the latest vitality reading whose date is on or before the last day of the "
         "billing period before prediction. Readings stamped on or after period open must "
         "not be used."),
        ("Post-period ledger drift",
         "PROHIBITED. Any ledger delta computed using readings taken after the outcome "
         "observation horizon has begun."),
        ("Period-span ledger comparison",
         "PROHIBITED when the comparison uses a ledger reading taken after period open, "
         "even if the earlier leg uses an otherwise valid prior-period reading."),
        ("Relationship tenure",
         "Always available from enrollment date and period open."),
    ]

    for feat, timing in rows:
        c.setFont('Helvetica-Bold', 9)
        c.drawString(52, y, feat)
        y -= 12
        c.setFont('Helvetica-Oblique', 8)
        words = timing.split()
        line_buf = ""
        for w in words:
            trial = (line_buf + " " + w).strip()
            if len(trial) > 88:
                c.drawString(60, y, line_buf)
                y -= 11
                line_buf = w
            else:
                line_buf = trial
        if line_buf:
            c.drawString(60, y, line_buf)
            y -= 14
        if y < 100:
            c.showPage()
            y = H - 60

    hline()
    y -= 8
    line("FOOTNOTE", 'Helvetica-Bold', 10, 14)
    line("Families marked PROHIBITED or NOT available must not appear in the model, even when", gap=12)
    line("the warehouse export contains values that were finalized after period open.", gap=12)
    line("Map each engineered column in the pipeline to one family above by inspecting which", gap=12)
    line("warehouse fields and date boundaries the column uses — column names are not reliable.", gap=18)
    line("Rolling windows end at period open (strictly before, not on or after).", gap=12)

    c.save()

gen_feature_availability_pdf(DATA_DIR / 'feature_availability.pdf')
print("feature_availability.pdf written")

# ── backtest_windows.csv ──────────────────────────────────────────────────────

bw_content = (
    "validate_month,train_end_month\n"
    "2025-12,2025-11\n"
    "2026-01,2025-12\n"
    "2026-02,2026-01\n"
    "2026-03,2026-02\n"
)
(DATA_DIR / 'backtest_windows.csv').write_text(bw_content)
print("backtest_windows.csv written")

# ── model_readme.md ───────────────────────────────────────────────────────────

readme = """\
# MRR-Loss Churn Prediction Model

## Overview

This model predicts which accounts will lose at least $500 MRR in the 30 days
following the prediction date. It was originally trained on account-month data
from November 2025 through March 2026 and deployed for April 2026 predictions.

## Background

Stakeholders flagged the model as suspiciously accurate relative to the customer
signals available at prediction time. An internal audit was recommended before
any further production use. The feature pipeline and training script have not
been formally reviewed for temporal leakage.

## Data Sources

- revenue_warehouse.sqlite
- feature_availability.pdf
- backtest_windows.csv
"""
(DATA_DIR / 'model_readme.md').write_text(readme)
print("model_readme.md written")

# ── config.yaml ───────────────────────────────────────────────────────────────

config_content = """\
database: /root/data/revenue_warehouse.sqlite
feature_availability_doc: /root/data/feature_availability.pdf
backtest_windows: /root/data/backtest_windows.csv
holdout_month: "2026-04"
output_dir: /root/out

model:
  type: gradient_boosting
  n_estimators: 100
  max_depth: 3
  random_state: 42
  learning_rate: 0.1

feature_pipeline:
  prediction_months:
    - "2025-11"
    - "2025-12"
    - "2026-01"
    - "2026-02"
    - "2026-03"
    - "2026-04"
"""
(PROJECT_DIR / 'config.yaml').write_text(config_content)
print("config.yaml written")

# ── Starter project code (split pipeline modules) ─────────────────────────────

STUBS_DIR = Path(__file__).resolve().parent / 'stubs'
for stub_name in (
    'period_utils.py',
    'warehouse_ops.py',
    'feature_blocks.py',
    'alt_aggregates.py',
    'feature_pipeline.py',
    'train_model.py',
):
    src = STUBS_DIR / stub_name
    (PROJECT_DIR / stub_name).write_text(src.read_text())
    print(f"{stub_name} written")

print("\n=== build_inputs.py complete ===")
print(f"  /root/data/revenue_warehouse.sqlite")
print(f"  /root/data/feature_availability.pdf")
print(f"  /root/data/backtest_windows.csv")
print(f"  /root/data/model_readme.md")
print(f"  /root/project/feature_pipeline.py")
print(f"  /root/project/train_model.py")
print(f"  /root/project/config.yaml")
