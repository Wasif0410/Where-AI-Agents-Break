"""
Generate deterministic input files for the usage-billing-dispute-audit task.

Three accounts, Q1 2026 (Jan–Mar), 4 PDFs (3 different invoice layouts + pricing addendum).

Pricing (from pricing_addendum.pdf — must be read by agent, not hardcoded):
  Included:  100,000 API calls/month
  Tier 1:    $0.002/call for calls 100,001 – 200,000
  Tier 2:    $0.0015/call for calls 200,001+
  Rounding:  Round billable calls UP to nearest 1,000
  Discount:  Enterprise Legacy accounts get 8% off total overage
  Tax:       Sales tax excluded from usage overage in audit

Expected charges:
  acct_001 (Mid-Market, no discount, USD):
    Jan: 85,000 calls → $0.00
    Feb: 145,000 metered calls; legacy workbook billable_calls = 46,000 → $92.00
    Mar: 92,000 calls → $0.00

  acct_002 (Enterprise Legacy, 8% discount, EMEA/EUR invoice):
    Jan: 175,000 calls → 75,000 billable → $150.00 → ×0.92 = $138.00 expected USD
         Invoice EUR 150.00 → USD 162.75 @ 1.0850 → delta $24.75
    Feb: 88,000 calls → $0.00
    Mar: 350,000 calls → 250,000 billable; legacy tier2_calls = 150,000
         → T1:100K×$0.002=$200 + T2:150K×$0.0015=$225 = $425 → ×0.92 = $391.00 expected USD
         Invoice EUR 425.00 → USD 458.58 @ 1.0790 → delta $67.58

  acct_003 (SMB, no discount, USD):
    Jan: 76,000 calls → $0.00
    Feb: 132,000 calls → 32,000 billable → $64.00
    Mar: 220,000 calls → 120,000 billable → T1 $200 + T2 $30 = $230.00 expected
         Invoice bills 120,000 @ $0.002 = $240.00 → WRONG_TIER, delta $10.00

Invoice discrepancies (intentional errors baked into PDFs):
  acct_002 Jan/Mar: EUR overage without legacy discount; FX conversion required for USD delta
  acct_003 Feb: invoice shows $74.24 overage (includes $10.24 tax) — TAX_INCLUDED, delta $10.24
  acct_003 Mar: invoice flat-rates all calls at Tier 1 — WRONG_TIER, delta $10.00

Input traps:
  legacy_call_adjustments.xlsx — formula cells; naive pd.read_excel() yields NaN
  invoice PDFs — three different layouts
  fx_rates.csv — required for EMEA EUR invoices
"""

import os

from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUTPUT_DIR = "/root/data"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(os.path.join(OUTPUT_DIR, "invoices"), exist_ok=True)


# ── PDF 1: pricing_addendum.pdf — prose/structured rules ─────────────────────

def gen_pricing_addendum(path):
    c = canvas.Canvas(path, pagesize=A4)
    _, h = A4
    y = h - 72

    def line(txt, font="Helvetica", size=10, gap=14):
        nonlocal y
        c.setFont(font, size)
        c.drawString(72, y, txt)
        y -= gap

    line("Abundant Cloud Platform — Pricing Addendum", "Helvetica-Bold", 13, 24)
    line("Effective: January 1, 2026", "Helvetica", 10, 20)

    line("Usage Pricing Tiers", "Helvetica-Bold", 11, 16)
    line("Each account includes 100,000 API calls per calendar month at no additional charge.", gap=13)
    line("Tier 1 Overage: calls 100,001 through 200,000 are billed at USD 0.002 per call.", gap=13)
    line("Tier 2 Overage: calls above 200,000 are billed at USD 0.0015 per call.", gap=13)
    line("Billable overage is rounded UP to the nearest 1,000 calls before rate application.", gap=20)

    line("Enterprise Legacy Discount", "Helvetica-Bold", 11, 16)
    line("Accounts designated as Enterprise Legacy in the customer registry receive an 8%", gap=13)
    line("discount applied to total overage charges. The discount is applied after tier rate", gap=13)
    line("calculation and before any tax. Discount applies to all overage tiers.", gap=20)

    line("Tax Policy", "Helvetica-Bold", 11, 16)
    line("Sales tax and VAT are excluded from usage overage charges in billing reconciliation", gap=13)
    line("audits. Where tax appears on an invoice overage line, it must be separated and", gap=13)
    line("classified as line_type='tax' in the extracted invoice lines.", gap=20)

    line("Regional Currency Policy", "Helvetica-Bold", 11, 16)
    line("EMEA accounts are invoiced in EUR. Billing reconciliation is performed in USD", gap=13)
    line("using the monthly usd_rate from fx_rates.csv for the service month.", gap=20)

    line("Legacy Billing Adjustments", "Helvetica-Bold", 11, 16)
    line("Account-months listed in legacy_call_adjustments.xlsx carry authoritative call-count", gap=13)
    line("values from the prior billing system. Interpret those cells using standard Excel", gap=13)
    line("formula semantics.", gap=20)

    line("Dispute Severity Framework", "Helvetica-Bold", 11, 16)
    line("High — sales tax or VAT included in usage overage charges.", gap=13)
    line("Medium — Enterprise Legacy discount not applied to invoice overage, tier", gap=13)
    line("arithmetic errors, or rounding errors.", gap=13)
    line("Low — immaterial per-call rate variance below the audit materiality threshold.", gap=20)

    line("Base Plan", "Helvetica-Bold", 11, 16)
    line("Base plan subscription charges are USD 500.00 per account per month.", gap=13)
    line("Base plan lines are not subject to dispute review in this audit.", gap=13)

    c.save()


gen_pricing_addendum(os.path.join(OUTPUT_DIR, "pricing_addendum.pdf"))


# ── PDF 2: invoice_acct_001.pdf — pipe-delimited table (restaurant-style) ─────
# All amounts correct — no billing errors for acct_001.

def gen_invoice_acct_001(path):
    c = canvas.Canvas(path, pagesize=A4)
    _, h = A4
    y = h - 72

    c.setFont("Helvetica-Bold", 13)
    c.drawString(72, y, "Northwind Analytics — Q1 2026 Invoice")
    y -= 20
    c.setFont("Helvetica", 10)
    c.drawString(72, y, "Account ID: acct_001  |  Billing Period: January – March 2026")
    y -= 20
    c.drawString(72, y, "Currency: USD")
    y -= 26

    c.setFont("Courier", 9)
    header = "source_file              | account_id | month   | line_description         | quantity | unit_price | amount_usd | line_type"
    c.drawString(36, y, header)
    y -= 14

    rows = [
        ("invoice_acct_001.pdf", "acct_001", "2026-01", "Monthly Subscription",         "1",     "500.0000", "500.00", "base_plan"),
        ("invoice_acct_001.pdf", "acct_001", "2026-01", "API Overage Calls",             "0",     "0.0020",   "0.00",  "overage"),
        ("invoice_acct_001.pdf", "acct_001", "2026-02", "Monthly Subscription",         "1",     "500.0000", "500.00", "base_plan"),
        ("invoice_acct_001.pdf", "acct_001", "2026-02", "API Overage (46,000 calls)",   "46000", "0.0020",   "92.00", "overage"),
        ("invoice_acct_001.pdf", "acct_001", "2026-03", "Monthly Subscription",         "1",     "500.0000", "500.00", "base_plan"),
        ("invoice_acct_001.pdf", "acct_001", "2026-03", "API Overage Calls",             "0",     "0.0020",   "0.00",  "overage"),
    ]

    for row in rows:
        txt = f"{row[0]:24s} | {row[1]:10s} | {row[2]:7s} | {row[3]:24s} | {row[4]:8s} | {row[5]:10s} | {row[6]:10s} | {row[7]}"
        c.drawString(36, y, txt)
        y -= 14

    y -= 8
    c.setFont("Helvetica", 10)
    c.drawString(72, y, "Invoice Total: USD 1,592.00")
    c.save()


gen_invoice_acct_001(os.path.join(OUTPUT_DIR, "invoices", "invoice_acct_001.pdf"))


# ── PDF 3: invoice_acct_002.pdf — section-based prose (medium difficulty) ─────

def gen_invoice_acct_002(path):
    c = canvas.Canvas(path, pagesize=A4)
    _, h = A4
    y = h - 72

    def line(txt, font="Helvetica", size=10, gap=14, indent=72):
        nonlocal y
        c.setFont(font, size)
        c.drawString(indent, y, txt)
        y -= gap

    line("Alpine Cloud Systems — Q1 2026 Statement of Charges", "Helvetica-Bold", 13, 22)
    line("Account ID: acct_002", gap=12)
    line("Billing Period: January 2026 – March 2026  |  Currency: EUR", gap=20)

    line("January 2026", "Helvetica-Bold", 11, 15)
    line("  Base Plan Subscription ................................ EUR 500.00", "Courier", 9, 13, 72)
    line("  API Overage 75,000 calls .............................. EUR 150.00", "Courier", 9, 13, 72)
    line("  January Subtotal: EUR 650.00", "Helvetica", 10, 18)

    line("February 2026", "Helvetica-Bold", 11, 15)
    line("  Base Plan Subscription ................................ EUR 500.00", "Courier", 9, 13, 72)
    line("  No API overage charges this month.", "Helvetica", 9, 18)

    line("March 2026", "Helvetica-Bold", 11, 15)
    line("  Base Plan Subscription ................................ EUR 500.00", "Courier", 9, 13, 72)
    line("  API Overage 250,000 calls ............................. EUR 425.00", "Courier", 9, 13, 72)
    line("  March Subtotal: EUR 925.00", "Helvetica", 10, 20)

    line("Grand Total: EUR 2,075.00", "Helvetica-Bold", 11, 12)
    line("Payment terms: Net 30 from invoice date.", "Helvetica", 9, 12)

    c.save()


gen_invoice_acct_002(os.path.join(OUTPUT_DIR, "invoices", "invoice_acct_002.pdf"))


# ── PDF 4: invoice_acct_003.pdf — compact inline prose (hardest to parse) ─────

def gen_invoice_acct_003(path):
    c = canvas.Canvas(path, pagesize=A4)
    _, h = A4
    y = h - 72

    c.setFont("Helvetica-Bold", 13)
    c.drawString(72, y, "PixelWorks Studio — Quarterly Invoice Q1 2026")
    y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(72, y, "Account ID: acct_003  |  Period: Jan–Mar 2026  |  Currency: USD")
    y -= 26

    c.setFont("Helvetica-Bold", 10)
    c.drawString(72, y, "Monthly Charges:")
    y -= 16

    c.setFont("Helvetica", 10)
    lines = [
        "Jan 2026:  Base $500.00  |  No API overage charges.",
        "Feb 2026:  Base $500.00  |  API Overage: 32,000 calls at $0.002/call = $64.00 (incl. tax $10.24)  |  Line total $74.24",
        "Mar 2026:  Base $500.00  |  API Overage: 120,000 calls at $0.002/call = $240.00",
    ]
    for ln in lines:
        c.drawString(72, y, ln)
        y -= 14

    y -= 10
    c.setFont("Helvetica-Bold", 10)
    c.drawString(72, y, "Grand Total: USD 2,314.24")
    y -= 16
    c.setFont("Helvetica", 9)
    c.drawString(72, y, "Note: Tax charges on usage lines subject to customer dispute (see ticket TKT-002).")
    c.save()


gen_invoice_acct_003(os.path.join(OUTPUT_DIR, "invoices", "invoice_acct_003.pdf"))


# ── customers.csv ─────────────────────────────────────────────────────────────

customers = [
    "account_id,company_name,segment,region,is_enterprise_legacy",
    "acct_001,Northwind Analytics,Mid-Market,NA,false",
    "acct_002,Alpine Cloud Systems,Enterprise,EMEA,true",
    "acct_003,PixelWorks Studio,SMB,NA,false",
]
with open(os.path.join(OUTPUT_DIR, "customers.csv"), "w") as f:
    f.write("\n".join(customers) + "\n")


# ── usage_logs.csv ────────────────────────────────────────────────────────────
# acct_001 Feb metered at 145,000 — billable must come from legacy workbook (46,000).

usage = [
    "account_id,service_month,api_calls",
    "acct_001,2026-01,85000",
    "acct_001,2026-02,145000",
    "acct_001,2026-03,92000",
    "acct_002,2026-01,175000",
    "acct_002,2026-02,88000",
    "acct_002,2026-03,350000",
    "acct_003,2026-01,76000",
    "acct_003,2026-02,132000",
    "acct_003,2026-03,220000",
]
with open(os.path.join(OUTPUT_DIR, "usage_logs.csv"), "w") as f:
    f.write("\n".join(usage) + "\n")


# ── legacy_call_adjustments.xlsx — formula input trap ─────────────────────────

def build_legacy_call_adjustments(path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Adjustments"
    ws.append(["account_id", "service_month", "billable_calls", "tier2_calls"])
    ws.append(["acct_001", "2026-02", "=SUM(40000,5000,1000)", None])
    ws.append(["acct_002", "2026-03", None, "=MAX(100000,150000)"])
    wb.save(path)


build_legacy_call_adjustments(os.path.join(OUTPUT_DIR, "legacy_call_adjustments.xlsx"))


# ── fx_rates.csv ──────────────────────────────────────────────────────────────

fx = [
    "month,currency,usd_rate",
    "2026-01,USD,1.0000",
    "2026-01,EUR,1.0850",
    "2026-02,USD,1.0000",
    "2026-02,EUR,1.0920",
    "2026-03,USD,1.0000",
    "2026-03,EUR,1.0790",
]
with open(os.path.join(OUTPUT_DIR, "fx_rates.csv"), "w") as f:
    f.write("\n".join(fx) + "\n")


# ── support_tickets.csv ───────────────────────────────────────────────────────

tickets = [
    "ticket_id,account_id,created_date,subject,notes",
    "TKT-001,acct_002,2026-04-03,Overage Discount Not Applied,"
    "\"Enterprise Legacy account per contract addendum section 4. "
    "Verify 8% discount applied to all Q1 2026 overage charges.\"",
    "TKT-002,acct_003,2026-04-07,Tax Charged on API Overage,"
    "\"February invoice includes USD 10.24 sales tax on overage line. "
    "Per contract clause 7.2 and pricing addendum tax policy sales tax "
    "is excluded from usage billing. Credit requested.\"",
]
with open(os.path.join(OUTPUT_DIR, "support_tickets.csv"), "w") as f:
    f.write("\n".join(tickets) + "\n")


print("Input files written to", OUTPUT_DIR)
print("  pricing_addendum.pdf            — tiers, discount, tax, severity, legacy policy")
print("  legacy_call_adjustments.xlsx    — formula cells (billable_calls / tier2_calls)")
print("  invoices/invoice_acct_001.pdf   — pipe-delimited table (correct)")
print("  invoices/invoice_acct_002.pdf   — section-based prose EUR (OVERBILLED + FX)")
print("  invoices/invoice_acct_003.pdf   — inline prose (TAX_INCLUDED + WRONG_TIER)")
print("  customers.csv                   — 3 accounts (acct_002 is Enterprise Legacy)")
print("  usage_logs.csv                  — 9 rows (3 accounts × 3 months)")
print("  fx_rates.csv                    — 6 rows")
print("  support_tickets.csv             — 2 dispute tickets")
