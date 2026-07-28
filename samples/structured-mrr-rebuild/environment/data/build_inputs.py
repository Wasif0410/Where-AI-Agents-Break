"""
Generate deterministic synthetic input files for the structured-mrr-rebuild task.

Dataset: 25 accounts, 60 invoice lines, 3 reporting months (2026-01 to 2026-03),
4 currencies (USD, EUR, CAD, GBP).

Trap accounts (acct_001–acct_011): all original rules preserved with non-round amounts.
New traps (acct_012–acct_016): multi-month continuity, multi-subscription aggregation,
    lowercase currency code, line_type capitalisation variant, GBP annual + FX.
Noise accounts (acct_017–acct_025): realistic filler that prevents manual eyeballing.

Two non-adjacent duplicate invoice_line_ids (il_014 and il_041) test that agents
drop duplicates regardless of row position. No randomness — fully deterministic.
"""

import json
import os

OUTPUT_DIR = "/root/data"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ── customers.csv ─────────────────────────────────────────────────────────────

customers_rows = [
    "account_id,customer_name,region,created_at",
    "acct_001,Northwind Analytics,NA,2025-01-15",
    "acct_002,Bluebird Retail,NA,2025-02-20",
    "acct_003,Alpine Cloud Systems,EU,2025-03-12",
    "acct_004,Redwood Security,NA,2025-04-01",
    "acct_005,MetroHealth SaaS,NA,2025-05-10",
    "acct_006,Horizon Education,CA,2025-06-15",
    "acct_007,Quantum Finance,NA,2025-07-20",
    "acct_008,Atlas Manufacturing,EU,2025-08-05",
    "acct_009,PixelWorks Studio,NA,2025-09-12",
    "acct_010,Maple Logistics,CA,2025-10-01",
    "acct_011,Birchwood Capital,NA,2025-11-15",
    "acct_012,Streamline Operations,NA,2025-11-20",
    "acct_013,Fusion Analytics,NA,2025-12-01",
    "acct_014,Cedar Mountain Retail,CA,2025-12-05",
    "acct_015,Summit Cloud Services,NA,2025-12-10",
    "acct_016,Sterling Financial,GB,2025-12-15",
    "acct_017,Riverside Media,NA,2026-01-02",
    "acct_018,Europa Systems,EU,2026-01-03",
    "acct_019,TerraData Inc,NA,2026-01-04",
    "acct_020,Pacific Ventures,CA,2026-01-05",
    "acct_021,Clearwater Tech,NA,2026-01-06",
    "acct_022,Iron Bridge Software,NA,2026-01-07",
    "acct_023,Volare Design,EU,2026-01-08",
    "acct_024,Baseline Corp,NA,2026-01-09",
    "acct_025,Caledonian Networks,GB,2026-01-10",
]

with open(os.path.join(OUTPUT_DIR, "customers.csv"), "w") as f:
    f.write("\n".join(customers_rows) + "\n")


# ── subscriptions.jsonl ───────────────────────────────────────────────────────
#
# billing_interval drives annual÷12 normalisation.
# Currency here is informational; the invoice_lines column is what gets joined.

subscriptions = [
    # acct_001: simple monthly USD baseline
    {"subscription_id": "sub_001", "account_id": "acct_001", "plan_name": "Growth",
     "billing_interval": "monthly", "currency": "USD",
     "start_date": "2026-01-01", "end_date": None, "status": "active"},

    # acct_002: annual USD — ÷12 normalisation trap
    # billing_interval uses capital-A "Annual" — agents must normalise case before divisor lookup.
    # Without str.lower(), "Annual" misses the {"annual": 12} mapping → divisor = 1 → MRR = 13476
    {"subscription_id": "sub_002", "account_id": "acct_002", "plan_name": "Enterprise Annual",
     "billing_interval": "Annual", "currency": "USD",
     "start_date": "2026-01-01", "end_date": "2026-12-31", "status": "active"},

    # acct_003: annual EUR, service Feb — compound: ÷12 + service-month FX trap
    {"subscription_id": "sub_003", "account_id": "acct_003", "plan_name": "Pro Annual EU",
     "billing_interval": "annual", "currency": "EUR",
     "start_date": "2026-02-01", "end_date": "2027-01-31", "status": "active"},

    # acct_004: monthly USD — tax exclusion trap
    {"subscription_id": "sub_004", "account_id": "acct_004", "plan_name": "Standard",
     "billing_interval": "monthly", "currency": "USD",
     "start_date": "2026-01-01", "end_date": None, "status": "active"},

    # acct_005: monthly USD — compound non-recurring (setup_fee + professional_services)
    {"subscription_id": "sub_005", "account_id": "acct_005", "plan_name": "Starter",
     "billing_interval": "monthly", "currency": "USD",
     "start_date": "2026-01-01", "end_date": None, "status": "active"},

    # acct_006: monthly CAD — currency whitespace trap: invoice_lines has " CAD"
    {"subscription_id": "sub_006", "account_id": "acct_006", "plan_name": "Business CAD",
     "billing_interval": "monthly", "currency": "CAD",
     "start_date": "2026-01-01", "end_date": None, "status": "active"},

    # acct_007: monthly USD — non-adjacent duplicate invoice line dedup trap
    {"subscription_id": "sub_007", "account_id": "acct_007", "plan_name": "Basic",
     "billing_interval": "monthly", "currency": "USD",
     "start_date": "2026-01-01", "end_date": None, "status": "active"},

    # acct_008: monthly USD — service month alignment trap
    #   invoice_date Jan, service_start Feb → revenue belongs in Feb
    {"subscription_id": "sub_008", "account_id": "acct_008", "plan_name": "Premium",
     "billing_interval": "monthly", "currency": "USD",
     "start_date": "2026-02-01", "end_date": None, "status": "active"},

    # acct_009: monthly USD — compound: base + proration + professional_services
    {"subscription_id": "sub_009", "account_id": "acct_009", "plan_name": "Enterprise",
     "billing_interval": "monthly", "currency": "USD",
     "start_date": "2026-01-01", "end_date": None, "status": "active"},

    # acct_010: annual CAD, service Feb — compound: ÷12 + FX
    {"subscription_id": "sub_010", "account_id": "acct_010", "plan_name": "Annual Enterprise CAD",
     "billing_interval": "annual", "currency": "CAD",
     "start_date": "2026-02-01", "end_date": "2027-01-31", "status": "active"},

    # acct_011: monthly USD — negative downgrade credit trap
    {"subscription_id": "sub_011", "account_id": "acct_011", "plan_name": "Growth",
     "billing_interval": "monthly", "currency": "USD",
     "start_date": "2026-01-01", "end_date": None, "status": "active"},

    # acct_012: monthly USD — multi-month continuity trap
    #   Jan: base; Feb: base + upgrade proration; Mar: post-upgrade base + downgrade credit
    {"subscription_id": "sub_012", "account_id": "acct_012", "plan_name": "Scale",
     "billing_interval": "monthly", "currency": "USD",
     "start_date": "2026-01-01", "end_date": None, "status": "active"},

    # acct_013: three monthly USD subscriptions — multi-subscription aggregation trap
    #   All three combine into one account-month MRR row; only sub_013a renews past Jan
    {"subscription_id": "sub_013a", "account_id": "acct_013", "plan_name": "Core Platform",
     "billing_interval": "monthly", "currency": "USD",
     "start_date": "2026-01-01", "end_date": None, "status": "active"},
    {"subscription_id": "sub_013b", "account_id": "acct_013", "plan_name": "Analytics Add-on",
     "billing_interval": "monthly", "currency": "USD",
     "start_date": "2026-01-01", "end_date": "2026-01-31", "status": "cancelled"},
    {"subscription_id": "sub_013c", "account_id": "acct_013", "plan_name": "Support Package",
     "billing_interval": "monthly", "currency": "USD",
     "start_date": "2026-01-01", "end_date": "2026-01-31", "status": "cancelled"},

    # acct_014: quarterly USD — quarterly normalisation trap
    #   The amount covers 3 months; MRR = amount ÷ 3 (service_start month only).
    #   Quarterly billing is common in enterprise SaaS (HubSpot, Salesforce, etc.).
    #   Wrong: 1392.00 (no quarterly normalisation).
    #   Wrong: 464.00 in Jan + Feb + Mar (amount spread across service_end period).
    #   Correct: 1392 ÷ 3 = 464.00 in 2026-01 only.
    {"subscription_id": "sub_014", "account_id": "acct_014", "plan_name": "Essentials Quarterly",
     "billing_interval": "quarterly", "currency": "USD",
     "start_date": "2026-01-01", "end_date": "2026-03-31", "status": "active"},

    # acct_015: monthly USD — catchup billing trap
    #   Three invoice lines all share invoice_date 2026-03-01 (single catchup invoice),
    #   but have service_start values in Jan, Feb, and Mar respectively.
    #   This happens when a customer converts from trial to paid and is invoiced retroactively,
    #   or when a billing system processes arrears payments in batch.
    #   Wrong: all revenue placed in 2026-03 because invoice_date = March (1275.00 in one row).
    #   Correct: 425.00 in each of 2026-01, 2026-02, 2026-03 (use service_start).
    {"subscription_id": "sub_015", "account_id": "acct_015", "plan_name": "Professional",
     "billing_interval": "monthly", "currency": "USD",
     "start_date": "2026-01-01", "end_date": None, "status": "active"},

    # acct_016: annual GBP, invoice Feb service Mar — compound: ÷12 + GBP service-month FX
    #   Wrong (invoice-month FX Feb): 9600/12 × 1.2710 = 1016.80
    #   Correct (service-month FX Mar): 9600/12 × 1.2580 = 1006.40
    {"subscription_id": "sub_016", "account_id": "acct_016", "plan_name": "Global Annual GBP",
     "billing_interval": "annual", "currency": "GBP",
     "start_date": "2026-03-01", "end_date": "2027-02-28", "status": "active"},

    # noise accounts — realistic monthly/annual subscriptions
    {"subscription_id": "sub_017", "account_id": "acct_017", "plan_name": "Starter",
     "billing_interval": "monthly", "currency": "USD",
     "start_date": "2026-01-01", "end_date": None, "status": "active"},
    {"subscription_id": "sub_018", "account_id": "acct_018", "plan_name": "Pro EU",
     "billing_interval": "monthly", "currency": "EUR",
     "start_date": "2026-02-01", "end_date": None, "status": "active"},
    {"subscription_id": "sub_019", "account_id": "acct_019", "plan_name": "Enterprise Annual",
     "billing_interval": "annual", "currency": "USD",
     "start_date": "2026-01-01", "end_date": "2026-12-31", "status": "active"},
    {"subscription_id": "sub_020", "account_id": "acct_020", "plan_name": "Growth CAD",
     "billing_interval": "monthly", "currency": "CAD",
     "start_date": "2026-01-01", "end_date": None, "status": "active"},
    {"subscription_id": "sub_021", "account_id": "acct_021", "plan_name": "Core",
     "billing_interval": "monthly", "currency": "USD",
     "start_date": "2026-01-01", "end_date": None, "status": "active"},
    {"subscription_id": "sub_022", "account_id": "acct_022", "plan_name": "Business",
     "billing_interval": "monthly", "currency": "USD",
     "start_date": "2026-01-01", "end_date": None, "status": "active"},
    {"subscription_id": "sub_023", "account_id": "acct_023", "plan_name": "Design Pro EU",
     "billing_interval": "monthly", "currency": "EUR",
     "start_date": "2026-03-01", "end_date": None, "status": "active"},
    {"subscription_id": "sub_024", "account_id": "acct_024", "plan_name": "Base",
     "billing_interval": "monthly", "currency": "USD",
     "start_date": "2026-01-01", "end_date": None, "status": "active"},
    {"subscription_id": "sub_025", "account_id": "acct_025", "plan_name": "Network Annual GBP",
     "billing_interval": "annual", "currency": "GBP",
     "start_date": "2026-01-01", "end_date": "2026-12-31", "status": "active"},
]

with open(os.path.join(OUTPUT_DIR, "subscriptions.jsonl"), "w") as f:
    for sub in subscriptions:
        f.write(json.dumps(sub) + "\n")


# ── invoice_lines.csv ─────────────────────────────────────────────────────────
#
# Schema:
#   invoice_line_id, invoice_id, account_id, subscription_id,
#   invoice_date, service_start, service_end,
#   line_type, description, amount, tax_amount, currency, is_proration
#
# Expected MRR (account, month → USD):
#   acct_001 Jan: 523.75     baseline monthly USD
#   acct_001 Feb: 523.75     same sub recurring
#   acct_001 Mar: 523.75     same sub recurring
#   acct_002 Jan: 1123.00    annual 13476÷12
#   acct_003 Feb: 1299.60    annual EUR 14400÷12 × EUR-Feb 1.0830 (not Jan 1.1050)
#   acct_004 Jan:  731.45    tax 95.09 excluded; use pre-tax amount only
#   acct_004 Feb:  731.45    same rule applies Feb
#   acct_005 Jan:  489.20    setup_fee 2500 + professional_services 1950 excluded
#   acct_006 Jan:  708.48    960 CAD × 0.7380; requires stripping " CAD" → "CAD"
#   acct_006 Feb:  720.96    960 CAD × 0.7510
#   acct_006 Mar:  714.72    960 CAD × 0.7445
#   acct_007 Jan:  617.50    non-adjacent duplicate il_014; must count once not twice
#   acct_008 Feb:  875.00    invoice_date Jan-30, service_start Feb-01 → rev in Feb
#   acct_009 Jan: 1312.50    base 1050 + proration 262.50; professional_services 1800 excluded
#   acct_010 Feb: 1652.20    annual CAD 26400÷12 × CAD-Feb 0.7510
#   acct_011 Jan: 1012.50    base 1350 + downgrade credit -337.50; filtering >0 gives 1350
#   acct_012 Jan:  645.00    multi-month: base only
#   acct_012 Feb:  860.00    multi-month: base 645 + upgrade proration 215
#   acct_012 Mar:  752.50    multi-month: post-upgrade base 860 + downgrade -107.50
#   acct_013 Jan: 1285.00    multi-sub: core 890 + addon 245 + support 150
#   acct_013 Feb:  890.00    multi-sub: only core renews Feb
#   acct_013 Mar:  890.00    multi-sub: only core renews Mar
#   acct_014 Jan:  464.00    quarterly USD 1392÷3; revenue in Jan only (not Feb/Mar despite service_end Mar)
#   acct_015 Jan:  425.00    catchup billing; all 3 lines have invoice_date Mar, service_start Jan/Feb/Mar
#   acct_015 Feb:  425.00    catchup billing; invoice_date Mar, service_start Feb
#   acct_015 Mar:  425.00    catchup billing; invoice_date Mar, service_start Mar
#   acct_016 Mar: 1006.40    annual GBP 9600÷12 × GBP-Mar 1.2580 (invoice Feb, service Mar)
#   acct_017 Jan:  398.00    noise; usage line 125.50 excluded
#   acct_017 Mar:  398.00    noise recurring
#   acct_018 Feb:  586.99    542 EUR × 1.0830
#   acct_018 Mar:  591.86    542 EUR × 1.0920
#   acct_019 Jan:  745.00    annual 8940÷12; non-adjacent duplicate il_041 must be dropped
#   acct_020 Jan:  457.56    620 CAD × 0.7380
#   acct_020 Feb:  465.62    620 CAD × 0.7510
#   acct_020 Mar:  461.59    620 CAD × 0.7445
#   acct_021 Jan:  319.00    noise
#   acct_021 Feb:  319.00    noise
#   acct_021 Mar:  319.00    noise
#   acct_022 Jan: 1125.00    noise; setup_fee 500 excluded
#   acct_022 Feb: 1125.00    noise
#   acct_022 Mar: 1125.00    noise
#   acct_023 Mar:  857.22    785 EUR × 1.0920
#   acct_024 Jan:  275.00    noise
#   acct_024 Feb:  275.00    noise
#   acct_024 Mar:  275.00    noise
#   acct_025 Jan:  802.64    annual GBP 7620÷12 × GBP-Jan 1.2640

invoice_lines_header = (
    "invoice_line_id,invoice_id,account_id,subscription_id,"
    "invoice_date,service_start,service_end,line_type,description,"
    "amount,tax_amount,currency,is_proration"
)

invoice_lines_rows = [

    # ── acct_001: monthly USD, baseline — appears all 3 months ───────────────
    "il_001,inv_001,acct_001,sub_001,"
    "2026-01-05,2026-01-01,2026-01-31,"
    "subscription,Growth Monthly,"
    "523.75,0.00,USD,false",

    "il_002,inv_002,acct_001,sub_001,"
    "2026-02-05,2026-02-01,2026-02-28,"
    "subscription,Growth Monthly,"
    "523.75,0.00,USD,false",

    "il_003,inv_003,acct_001,sub_001,"
    "2026-03-05,2026-03-01,2026-03-31,"
    "subscription,Growth Monthly,"
    "523.75,0.00,USD,false",

    # ── acct_002: annual USD 13476 (÷12 trap) ────────────────────────────────
    "il_004,inv_004,acct_002,sub_002,"
    "2026-01-05,2026-01-01,2026-12-31,"
    "subscription,Enterprise Annual,"
    "13476.00,0.00,USD,false",

    # ── acct_003: annual EUR 14400, invoice Jan, service Feb ─────────────────
    #   Compound trap: annual÷12 AND must use EUR Feb FX (1.0830), not Jan (1.1050)
    #   Wrong (Jan FX):  14400/12 × 1.1050 = 1326.00
    #   Correct (Feb FX): 14400/12 × 1.0830 = 1299.60 in 2026-02
    "il_005,inv_005,acct_003,sub_003,"
    "2026-01-29,2026-02-01,2026-02-28,"
    "subscription,Pro Annual EU,"
    "14400.00,0.00,EUR,false",

    # ── acct_004: subscription with tax — tax exclusion trap ─────────────────
    #   tax_amount 95.09 must NOT be added to MRR; use pre-tax amount 731.45 only
    "il_006,inv_006,acct_004,sub_004,"
    "2026-01-05,2026-01-01,2026-01-31,"
    "subscription,Standard Monthly,"
    "731.45,95.09,USD,false",

    "il_007,inv_007,acct_004,sub_004,"
    "2026-02-05,2026-02-01,2026-02-28,"
    "subscription,Standard Monthly,"
    "731.45,95.09,USD,false",

    # ── acct_005: compound non-recurring — setup_fee + professional_services ─
    #   Both fee types excluded; subscription 489.20 is the only MRR line
    "il_008,inv_008,acct_005,sub_005,"
    "2026-01-05,2026-01-01,2026-01-31,"
    "subscription,Starter Monthly,"
    "489.20,0.00,USD,false",

    "il_009,inv_008,acct_005,,"
    "2026-01-05,2026-01-01,2026-01-31,"
    "setup_fee,One-time Setup Fee,"
    "2500.00,0.00,USD,false",

    "il_010,inv_008,acct_005,,"
    "2026-01-05,2026-01-01,2026-01-31,"
    "professional_services,Onboarding Services,"
    "1950.00,0.00,USD,false",

    # ── acct_006: monthly CAD with leading whitespace in currency field ───────
    #   currency = " CAD" (note the leading space) — same trap, now spans 3 months
    #   FX join fails or returns NaN without str.strip()
    #   Jan: 960 × 0.7380 = 708.48; Feb: 960 × 0.7510 = 720.96; Mar: 960 × 0.7445 = 714.72
    "il_011,inv_009,acct_006,sub_006,"
    "2026-01-05,2026-01-01,2026-01-31,"
    "subscription,Business Monthly,"
    "960.00,0.00, CAD,false",

    "il_012,inv_010,acct_006,sub_006,"
    "2026-02-05,2026-02-01,2026-02-28,"
    "subscription,Business Monthly,"
    "960.00,0.00, CAD,false",

    "il_013,inv_011,acct_006,sub_006,"
    "2026-03-05,2026-03-01,2026-03-31,"
    "subscription,Business Monthly,"
    "960.00,0.00, CAD,false",

    # ── acct_007: non-adjacent duplicate (FIRST occurrence — row 14) ─────────
    #   il_014 appears again near row 59 with identical data.
    #   Without dedup: MRR = 617.50 × 2 = 1235.00. Correct: 617.50.
    "il_014,inv_012,acct_007,sub_007,"
    "2026-01-05,2026-01-01,2026-01-31,"
    "subscription,Basic Monthly,"
    "617.50,0.00,USD,false",

    # ── acct_008: service month alignment trap ────────────────────────────────
    #   invoice_date = 2026-01-30, service_start = 2026-02-01 → revenue in Feb
    "il_015,inv_013,acct_008,sub_008,"
    "2026-01-30,2026-02-01,2026-02-28,"
    "subscription,Premium Monthly,"
    "875.00,0.00,USD,false",

    # ── acct_009: compound — base + proration + professional_services ─────────
    #   base 1050 + upgrade proration 262.50 both count toward MRR = 1312.50
    #   professional_services 1800 on same invoice must be excluded
    "il_016,inv_014,acct_009,sub_009,"
    "2026-01-05,2026-01-01,2026-01-31,"
    "subscription,Enterprise Monthly,"
    "1050.00,0.00,USD,false",

    "il_017,inv_014,acct_009,sub_009,"
    "2026-01-12,2026-01-01,2026-01-31,"
    "subscription,Upgrade Proration,"
    "262.50,0.00,USD,true",

    "il_018,inv_014,acct_009,,"
    "2026-01-12,2026-01-01,2026-01-31,"
    "professional_services,Implementation Services,"
    "1800.00,0.00,USD,false",

    # ── acct_010: annual CAD 26400, service Feb — compound: ÷12 + FX ─────────
    #   26400 ÷ 12 = 2200 CAD/month × CAD-Feb 0.7510 = 1652.20 USD
    "il_019,inv_015,acct_010,sub_010,"
    "2026-02-01,2026-02-01,2027-01-31,"
    "subscription,Annual Enterprise CAD,"
    "26400.00,0.00,CAD,false",

    # ── acct_011: negative downgrade credit trap ──────────────────────────────
    #   base 1350 + downgrade credit -337.50 = net MRR 1012.50
    #   filtering amount > 0 drops the credit and yields 1350 instead of 1012.50
    "il_020,inv_016,acct_011,sub_011,"
    "2026-01-05,2026-01-01,2026-01-31,"
    "subscription,Growth Monthly,"
    "1350.00,0.00,USD,false",

    "il_021,inv_016,acct_011,sub_011,"
    "2026-01-15,2026-01-01,2026-01-31,"
    "subscription,Downgrade Credit,"
    "-337.50,0.00,USD,true",

    # ── acct_012: multi-month continuity trap ────────────────────────────────
    #   Jan: base only → 645.00
    #   Feb: base 645 + upgrade proration 215 → 860.00
    #   Mar: post-upgrade base 860 + downgrade credit -107.50 → 752.50
    #   Tests that agents group correctly across months and handle mid-cycle credits.
    "il_022,inv_017,acct_012,sub_012,"
    "2026-01-05,2026-01-01,2026-01-31,"
    "subscription,Scale Monthly,"
    "645.00,0.00,USD,false",

    "il_023,inv_018,acct_012,sub_012,"
    "2026-02-05,2026-02-01,2026-02-28,"
    "subscription,Scale Monthly,"
    "645.00,0.00,USD,false",

    "il_024,inv_018,acct_012,sub_012,"
    "2026-02-18,2026-02-01,2026-02-28,"
    "subscription,Upgrade Proration,"
    "215.00,0.00,USD,true",

    # ── acct_013: multi-subscription aggregation trap ─────────────────────────
    #   Three subscriptions; all three combine into ONE account-month MRR row.
    #   Jan: core 890 + addon 245 + support 150 = 1285.00
    #   Feb/Mar: only core sub_013a renews; addon and support cancelled after Jan.
    #   Tests that agents don't double-count or split the grain by subscription_id.
    #
    #   il_025 uses line_type "Subscription" (capital S) — agents must normalise case
    #   before filtering. Without str.lower(), "Subscription" fails the == "subscription"
    #   filter and the 890.00 core line is silently excluded → acct_013 Jan = 395.00
    "il_025,inv_019,acct_013,sub_013a,"
    "2026-01-05,2026-01-01,2026-01-31,"
    "Subscription,Core Platform Monthly,"
    "890.00,0.00,USD,false",

    "il_026,inv_019,acct_013,sub_013b,"
    "2026-01-05,2026-01-01,2026-01-31,"
    "subscription,Analytics Add-on Monthly,"
    "245.00,0.00,USD,false",

    "il_027,inv_019,acct_013,sub_013c,"
    "2026-01-05,2026-01-01,2026-01-31,"
    "subscription,Support Package Monthly,"
    "150.00,0.00,USD,false",

    "il_028,inv_020,acct_013,sub_013a,"
    "2026-02-05,2026-02-01,2026-02-28,"
    "subscription,Core Platform Monthly,"
    "890.00,0.00,USD,false",

    "il_029,inv_021,acct_013,sub_013a,"
    "2026-03-05,2026-03-01,2026-03-31,"
    "subscription,Core Platform Monthly,"
    "890.00,0.00,USD,false",

    # ── acct_014: quarterly billing normalisation trap ────────────────────────
    #   billing_interval = "quarterly" → MRR = amount ÷ 3, placed in service_start month only.
    #   service_end = 2026-03-31 covers 3 months, but revenue belongs in Jan only (service_start).
    #   1392.00 ÷ 3 = 464.00 in 2026-01.
    "il_030,inv_022,acct_014,sub_014,"
    "2026-01-05,2026-01-01,2026-03-31,"
    "subscription,Essentials Quarterly,"
    "1392.00,0.00,USD,false",

    # ── acct_015: catchup billing trap ───────────────────────────────────────
    #   All 3 lines share invoice_date 2026-03-01 (one catchup invoice issued in March).
    #   Each line has a different service_start: Jan, Feb, Mar.
    #   An agent using invoice_date groups all revenue into 2026-03 → 1275.00 in one row.
    #   Correct: service_start determines the revenue month → 425.00 in each of Jan, Feb, Mar.
    "il_032,inv_024,acct_015,sub_015,"
    "2026-03-01,2026-01-01,2026-01-31,"
    "subscription,Professional Monthly,"
    "425.00,0.00,USD,false",

    "il_033,inv_024,acct_015,sub_015,"
    "2026-03-01,2026-02-01,2026-02-28,"
    "subscription,Professional Monthly,"
    "425.00,0.00,USD,false",

    "il_034,inv_024,acct_015,sub_015,"
    "2026-03-01,2026-03-01,2026-03-31,"
    "subscription,Professional Monthly,"
    "425.00,0.00,USD,false",

    # ── acct_016: annual GBP 9600, invoice Feb, service Mar ──────────────────
    #   Compound trap: annual÷12 AND must use GBP Mar FX (1.2580), not Feb (1.2710)
    #   Wrong (Feb FX):  9600/12 × 1.2710 = 1016.80
    #   Correct (Mar FX): 9600/12 × 1.2580 = 1006.40 in 2026-03
    "il_035,inv_027,acct_016,sub_016,"
    "2026-02-28,2026-03-01,2027-02-28,"
    "subscription,Global Annual GBP,"
    "9600.00,0.00,GBP,false",

    # ── acct_017: noise — monthly USD with a usage charge in Mar ─────────────
    "il_036,inv_028,acct_017,sub_017,"
    "2026-01-05,2026-01-01,2026-01-31,"
    "subscription,Starter Monthly,"
    "398.00,0.00,USD,false",

    "il_037,inv_029,acct_017,sub_017,"
    "2026-03-05,2026-03-01,2026-03-31,"
    "subscription,Starter Monthly,"
    "398.00,0.00,USD,false",

    "il_038,inv_029,acct_017,,"
    "2026-03-05,2026-03-01,2026-03-31,"
    "usage,API Overage Mar,"
    "125.50,0.00,USD,false",

    # ── acct_018: noise — monthly EUR, Feb + Mar ──────────────────────────────
    #   Feb: 542 × 1.0830 = 586.99; Mar: 542 × 1.0920 = 591.86
    "il_039,inv_030,acct_018,sub_018,"
    "2026-02-05,2026-02-01,2026-02-28,"
    "subscription,Pro EU Monthly,"
    "542.00,0.00,EUR,false",

    "il_040,inv_031,acct_018,sub_018,"
    "2026-03-05,2026-03-01,2026-03-31,"
    "subscription,Pro EU Monthly,"
    "542.00,0.00,EUR,false",

    # ── acct_019: annual USD — non-adjacent duplicate (FIRST occurrence, row 41)
    #   il_041 appears again at row 60 with identical data.
    #   Without dedup: 8940 × 2 then ÷12 = 1490.00. Correct: 8940÷12 = 745.00.
    "il_041,inv_032,acct_019,sub_019,"
    "2026-01-05,2026-01-01,2026-12-31,"
    "subscription,Enterprise Annual,"
    "8940.00,0.00,USD,false",

    # ── acct_020: noise — monthly CAD, all 3 months ───────────────────────────
    #   Jan: 620 × 0.7380 = 457.56; Feb: 620 × 0.7510 = 465.62; Mar: 620 × 0.7445 = 461.59
    "il_042,inv_033,acct_020,sub_020,"
    "2026-01-05,2026-01-01,2026-01-31,"
    "subscription,Growth CAD Monthly,"
    "620.00,0.00,CAD,false",

    "il_043,inv_034,acct_020,sub_020,"
    "2026-02-05,2026-02-01,2026-02-28,"
    "subscription,Growth CAD Monthly,"
    "620.00,0.00,CAD,false",

    "il_044,inv_035,acct_020,sub_020,"
    "2026-03-05,2026-03-01,2026-03-31,"
    "subscription,Growth CAD Monthly,"
    "620.00,0.00,CAD,false",

    # ── acct_021: noise — monthly USD, all 3 months ──────────────────────────
    #   il_045 amount exported as currency-formatted string "$319.00" — agents must
    #   strip $ and parse to numeric; raw float read fails or yields NaN → missing row
    "il_045,inv_036,acct_021,sub_021,"
    "2026-01-05,2026-01-01,2026-01-31,"
    "subscription,Core Monthly,"
    '"$319.00",0.00,USD,false',

    "il_046,inv_037,acct_021,sub_021,"
    "2026-02-05,2026-02-01,2026-02-28,"
    "subscription,Core Monthly,"
    "319.00,0.00,USD,false",

    "il_047,inv_038,acct_021,sub_021,"
    "2026-03-05,2026-03-01,2026-03-31,"
    "subscription,Core Monthly,"
    "319.00,0.00,USD,false",

    # ── acct_022: noise — monthly USD + setup_fee in Jan ─────────────────────
    #   setup_fee 500 is excluded; subscription 1125 is the only MRR line each month
    "il_048,inv_039,acct_022,sub_022,"
    "2026-01-05,2026-01-01,2026-01-31,"
    "subscription,Business Monthly,"
    "1125.00,0.00,USD,false",

    "il_049,inv_039,acct_022,,"
    "2026-01-05,2026-01-01,2026-01-31,"
    "setup_fee,Onboarding Fee,"
    "500.00,0.00,USD,false",

    "il_050,inv_040,acct_022,sub_022,"
    "2026-02-05,2026-02-01,2026-02-28,"
    "subscription,Business Monthly,"
    "1125.00,0.00,USD,false",

    "il_051,inv_041,acct_022,sub_022,"
    "2026-03-05,2026-03-01,2026-03-31,"
    "subscription,Business Monthly,"
    "1125.00,0.00,USD,false",

    # ── acct_023: noise — monthly EUR, Mar only ───────────────────────────────
    #   785 × 1.0920 = 857.22
    "il_052,inv_042,acct_023,sub_023,"
    "2026-03-05,2026-03-01,2026-03-31,"
    "subscription,Design Pro EU Monthly,"
    "785.00,0.00,EUR,false",

    # ── acct_024: noise — monthly USD, all 3 months ──────────────────────────
    "il_053,inv_043,acct_024,sub_024,"
    "2026-01-05,2026-01-01,2026-01-31,"
    "subscription,Base Monthly,"
    "275.00,0.00,USD,false",

    "il_054,inv_044,acct_024,sub_024,"
    "2026-02-05,2026-02-01,2026-02-28,"
    "subscription,Base Monthly,"
    "275.00,0.00,USD,false",

    "il_055,inv_045,acct_024,sub_024,"
    "2026-03-05,2026-03-01,2026-03-31,"
    "subscription,Base Monthly,"
    "275.00,0.00,USD,false",

    # ── acct_025: annual GBP 7620, Jan ───────────────────────────────────────
    #   7620 ÷ 12 = 635 GBP/month × GBP-Jan 1.2640 = 802.64 USD
    "il_056,inv_046,acct_025,sub_025,"
    "2026-01-05,2026-01-01,2026-12-31,"
    "subscription,Network Annual GBP,"
    "7620.00,0.00,GBP,false",

    # ── acct_012 Mar lines (placed here, far from Jan/Feb, testing grouping) ──
    "il_057,inv_047,acct_012,sub_012,"
    "2026-03-05,2026-03-01,2026-03-31,"
    "subscription,Scale Monthly,"
    "860.00,0.00,USD,false",

    "il_058,inv_047,acct_012,sub_012,"
    "2026-03-20,2026-03-01,2026-03-31,"
    "subscription,Downgrade Credit,"
    "-107.50,0.00,USD,true",

    # ── NON-ADJACENT DUPLICATES ───────────────────────────────────────────────
    # il_014 and il_041 appear again here (rows 59-60), far from their first
    # occurrence at rows 14 and 41. Naive dedup-at-end or first-seen-wins strategies
    # still work; only agents that never dedup produce wrong MRR.

    # acct_007 duplicate (original: row 14)
    "il_014,inv_012,acct_007,sub_007,"
    "2026-01-05,2026-01-01,2026-01-31,"
    "subscription,Basic Monthly,"
    "617.50,0.00,USD,false",

    # acct_019 duplicate (original: row 41)
    "il_041,inv_032,acct_019,sub_019,"
    "2026-01-05,2026-01-01,2026-12-31,"
    "subscription,Enterprise Annual,"
    "8940.00,0.00,USD,false",
]

with open(os.path.join(OUTPUT_DIR, "invoice_lines.csv"), "w") as f:
    f.write(invoice_lines_header + "\n")
    f.write("\n".join(invoice_lines_rows) + "\n")


# ── fx_rates.csv ──────────────────────────────────────────────────────────────
#
# 4 currencies × 3 months = 12 rows.
#
# EUR and CAD rates vary month-to-month — this is the mechanism behind:
#   acct_003: annual EUR, service Feb → EUR-Feb 1.0830 (not Jan 1.1050)
#   acct_006: monthly " CAD" whitespace trap (also exercises all 3 CAD rates)
#   acct_010: annual CAD, service Feb → CAD-Feb 0.7510
#   acct_016: annual GBP, service Mar → GBP-Mar 1.2580 (not Feb 1.2710)
#
# Correct (service-month) vs Wrong (invoice-month) FX comparisons:
#   acct_003:  1200 × 1.0830 = 1299.60 (correct) vs 1200 × 1.1050 = 1326.00 (wrong)
#   acct_016:   800 × 1.2580 = 1006.40 (correct) vs  800 × 1.2710 = 1016.80 (wrong)

fx_rates_rows = [
    "month,currency,usd_rate",
    "2026-01,USD,1.0000",
    "2026-01,EUR,1.1050",
    "2026-01,CAD,0.7380",
    "2026-01,GBP,1.2640",
    "2026-02,USD,1.0000",
    "2026-02,EUR,1.0830",
    "2026-02,CAD,0.7510",
    "2026-02,GBP,1.2710",
    "2026-03,USD,1.0000",
    "2026-03,EUR,1.0920",
    "2026-03,CAD,0.7445",
    "2026-03,GBP,1.2580",
]

with open(os.path.join(OUTPUT_DIR, "fx_rates.csv"), "w") as f:
    f.write("\n".join(fx_rates_rows) + "\n")


# ── Summary of expected output values ─────────────────────────────────────────
#
# total_mrr_usd    = 32549.19
# account_count    = 25
# month_count      = 3
#
# max_mrr_account_id = "acct_022"  (total across all months: 1125 × 3 = 3375.00)
#   Trap: acct_010 has the highest SINGLE-MONTH row (1652.20 in Feb).
#   The correct definition is highest TOTAL MRR across all months → acct_022.
#
# max_mrr_month = "2026-01"  (aggregate: 13459.58 across 19 accounts)
#   Trap: acct_010's peak is in Feb, but Jan's aggregate total is highest.
#   The correct definition is month with highest AGGREGATE MRR → 2026-01.
#
# excluded_non_recurring_total_usd = 6875.50
# tax_excluded_total_usd           = 190.18
#
# ── monthly_summary.csv ───────────────────────────────────────────────────────
# month    | total_mrr_usd | account_count | mrr_change_usd | mrr_change_pct
# 2026-01  |  13459.58     |  19           |                |
# 2026-02  |  10749.57     |  14           |    -2710.01    |   -0.2013
# 2026-03  |   8340.04     |  13           |    -2409.53    |   -0.2242

print("Input files written to", OUTPUT_DIR)
print("  customers.csv       —", 25, "accounts")
print("  subscriptions.jsonl —", 27, "subscriptions")
print("  invoice_lines.csv   —", len(invoice_lines_rows), "raw rows (includes 2 non-adjacent duplicates)")
print("  fx_rates.csv        — 12 rows (USD/EUR/CAD/GBP × Jan/Feb/Mar)")
