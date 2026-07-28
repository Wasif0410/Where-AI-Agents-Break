#!/bin/bash
# Reference solution for usage-billing-dispute-audit.
#
# Pipeline:
#   1. Extract pricing rules from pricing_addendum.pdf (tiers, discount, tax policy)
#   2. Extract invoice lines from 3 PDFs with different formats
#   3. Load usage logs, customers, support tickets
#   4. Compute expected overage per account/month using pricing rules
#   5. Reconcile billed vs expected
#   6. Classify exceptions with exact type strings
#   7. Build 5-sheet Excel workbook

python3 - << 'PYEOF'
import re
from math import ceil
from pathlib import Path

import pandas as pd
import pdfplumber
from openpyxl import Workbook, load_workbook

Path("/root/out").mkdir(parents=True, exist_ok=True)

TOLERANCE = 0.01

# ── 1. Extract pricing rules from pricing_addendum.pdf ────────────────────────

pricing = {
    "included_calls": None,
    "tier1_rate":     None,
    "tier1_ceiling":  None,
    "tier2_rate":     None,
    "rounding":       None,
    "legacy_discount": None,
}

text_full = ""
with pdfplumber.open("/root/data/pricing_addendum.pdf") as pdf:
    for page in pdf.pages:
        text_full += (page.extract_text() or "") + "\n"

# Parse included calls
m = re.search(r"includes?\s+([\d,]+)\s+API calls? per", text_full, re.I)
if m:
    pricing["included_calls"] = int(m.group(1).replace(",", ""))

# Parse Tier 1: "calls 100,001 through 200,000 are billed at USD 0.002 per call"
m1 = re.search(r"Tier 1.*?calls ([\d,]+) through ([\d,]+).*?USD ([\d.]+) per call", text_full, re.I | re.S)
if m1:
    pricing["tier1_rate"]    = float(m1.group(3))
    pricing["tier1_ceiling"] = int(m1.group(2).replace(",", "")) - pricing["included_calls"]

# Parse Tier 2: "calls above 200,000 are billed at USD 0.0015 per call"
m2 = re.search(r"Tier 2.*?USD ([\d.]+) per call", text_full, re.I | re.S)
if m2:
    pricing["tier2_rate"] = float(m2.group(1))

# Parse rounding: "rounded UP to the nearest 1,000 calls"
m3 = re.search(r"rounded UP to the nearest ([\d,]+) calls", text_full, re.I)
if m3:
    pricing["rounding"] = int(m3.group(1).replace(",", ""))

# Parse legacy discount: "8% discount applied to total overage"
m4 = re.search(r"(\d+)%\s+discount applied", text_full, re.I)
if m4:
    pricing["legacy_discount"] = float(m4.group(1)) / 100.0

assert all(v is not None for v in pricing.values()), f"Pricing parse incomplete: {pricing}"
print("Pricing from addendum:", pricing)

INCLUDED    = pricing["included_calls"]       # 100000
T1_RATE     = pricing["tier1_rate"]           # 0.002
T1_CEILING  = pricing["tier1_ceiling"]        # 100000 (calls 100K–200K)
T2_RATE     = pricing["tier2_rate"]           # 0.0015
ROUNDING    = pricing["rounding"]             # 1000
DISCOUNT    = pricing["legacy_discount"]      # 0.08


def eval_excel_formula(formula):
    """Evaluate simple legacy workbook formulas."""
    if formula is None:
        return None
    if isinstance(formula, (int, float)):
        return float(formula)

    def parse_number(token):
        return float(str(token).strip().replace(",", ""))

    text = str(formula).strip()
    if not text.startswith("="):
        return parse_number(text)
    expr = text[1:].strip().upper()
    if expr.startswith("MAX(") and expr.endswith(")"):
        inner = expr[4:-1]
        parts = [parse_number(p) for p in inner.split(",")]
        return float(max(parts))
    if expr.startswith("SUM(") and expr.endswith(")"):
        inner = expr[4:-1]
        parts = [parse_number(p) for p in inner.split(",")]
        return float(sum(parts))
    if "+" in expr:
        return float(sum(parse_number(p) for p in expr.split("+")))
    raise ValueError(f"Unsupported formula: {formula}")


def load_legacy_adjustments(path):
    """Read legacy_call_adjustments.xlsx and evaluate formula cells."""
    wb = load_workbook(path, data_only=False)
    ws = wb.active
    headers = [c.value for c in ws[1]]
    idx = {h: i for i, h in enumerate(headers)}
    overrides = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[idx["account_id"]] is None:
            continue
        key = (str(row[idx["account_id"]]).strip(), str(row[idx["service_month"]]).strip())
        entry = {}
        if "billable_calls" in idx and row[idx["billable_calls"]] is not None:
            entry["billable_calls"] = int(eval_excel_formula(row[idx["billable_calls"]]))
        if "tier2_calls" in idx and row[idx["tier2_calls"]] is not None:
            entry["tier2_calls"] = int(eval_excel_formula(row[idx["tier2_calls"]]))
        overrides[key] = entry
    return overrides


def compute_overage(actual_calls, is_legacy, billable_override=None, tier2_override=None):
    raw = actual_calls - INCLUDED
    if raw <= 0 and billable_override is None:
        return 0.0, 0, 0, 0, False
    billable = billable_override if billable_override is not None else ceil(raw / ROUNDING) * ROUNDING
    if billable <= 0:
        return 0.0, 0, 0, 0, False
    t2 = tier2_override if tier2_override is not None else max(billable - T1_CEILING, 0)
    t1 = billable - t2
    charge = t1 * T1_RATE + t2 * T2_RATE
    if is_legacy:
        charge = round(charge * (1 - DISCOUNT), 2)
    discount_applied = is_legacy
    return round(charge, 2), billable, t1, t2, discount_applied


# ── 2. Load source data ───────────────────────────────────────────────────────

customers = pd.read_csv("/root/data/customers.csv")
usage_df  = pd.read_csv("/root/data/usage_logs.csv")
tickets   = pd.read_csv("/root/data/support_tickets.csv")
fx_df     = pd.read_csv("/root/data/fx_rates.csv")
legacy_overrides = load_legacy_adjustments("/root/data/legacy_call_adjustments.xlsx")

fx_rates = {
    (str(row["month"]), str(row["currency"])): float(row["usd_rate"])
    for _, row in fx_df.iterrows()
}

legacy_accts = set(customers[customers["is_enterprise_legacy"].astype(str).str.lower() == "true"]["account_id"])
eur_accts = set(customers[customers["region"].astype(str).str.upper() == "EMEA"]["account_id"])
print("Legacy accounts:", legacy_accts)
print("EUR invoice accounts:", eur_accts)
print("Legacy overrides:", legacy_overrides)


def to_usd(acct, month, amount):
    if acct in eur_accts:
        rate = fx_rates.get((month, "EUR"), 1.0)
        return round(amount * rate, 2)
    return round(amount, 2)


def is_wrong_tier_invoice(er, billed_amount):
    if er["tier2_calls"] <= 0:
        return False
    flat_t1 = round(er["billable_calls"] * T1_RATE, 2)
    return abs(billed_amount - flat_t1) <= TOLERANCE


# ── 3. Extract invoice lines from 3 PDFs (different formats) ─────────────────

invoice_lines = []  # list of dicts


def parse_invoice_001(path):
    """Pipe-delimited table format."""
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                if "|" not in line:
                    continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 8:
                    continue
                try:
                    source, acct, month, desc, qty, uprice, amount, ltype = parts[:8]
                    if not acct.startswith("acct_"):
                        continue
                    rows.append({
                        "source_file":    source.strip(),
                        "account_id":     acct.strip(),
                        "invoice_month":  month.strip(),
                        "line_description": desc.strip(),
                        "quantity":       float(qty) if qty.strip() else 0,
                        "unit_price":     float(uprice) if uprice.strip() else 0,
                        "line_amount":    float(amount),
                        "line_type":      ltype.strip(),
                    })
                except (ValueError, IndexError):
                    pass
    return rows


def parse_invoice_002(path):
    """Section-based prose format: each month has a heading + indented lines."""
    rows = []
    with pdfplumber.open(path) as pdf:
        text = ""
        for page in pdf.pages:
            text += (page.extract_text() or "") + "\n"

    current_month = None
    base_re   = re.compile(r"Base Plan Subscription\s*\.+\s*EUR\s*([\d.]+)", re.I)
    over_re   = re.compile(r"API Overage\s+([\d,]+)\s+calls\s*\.+\s*EUR\s*([\d.]+)", re.I)
    month_re  = re.compile(r"^(January|February|March|April|May|June|July|August|"
                            r"September|October|November|December)\s+(\d{4})", re.I)

    month_map = {"january":"01","february":"02","march":"03","april":"04",
                 "may":"05","june":"06","july":"07","august":"08",
                 "september":"09","october":"10","november":"11","december":"12"}

    for line in text.splitlines():
        m = month_re.match(line.strip())
        if m:
            mn = month_map[m.group(1).lower()]
            current_month = f"{m.group(2)}-{mn}"
            continue
        if current_month is None:
            continue
        b = base_re.search(line)
        if b:
            rows.append({"source_file":"invoice_acct_002.pdf","account_id":"acct_002",
                         "invoice_month":current_month,"line_description":"Base Plan Subscription",
                         "quantity":1,"unit_price":float(b.group(1)),"line_amount":float(b.group(1)),
                         "line_type":"base_plan"})
        o = over_re.search(line)
        if o:
            qty = int(o.group(1).replace(",",""))
            amt = float(o.group(2))
            rows.append({"source_file":"invoice_acct_002.pdf","account_id":"acct_002",
                         "invoice_month":current_month,
                         "line_description":f"API Overage {o.group(1)} calls",
                         "quantity":qty,"unit_price":round(amt/qty,6) if qty else 0,
                         "line_amount":amt,"line_type":"overage"})
    return rows


def parse_invoice_003(path):
    """Compact inline prose: 'Base $500 | Overage: 32,000 calls at $0.002/call = $64.00 (incl. tax $10.24) | Line total $74.24'"""
    rows = []
    with pdfplumber.open(path) as pdf:
        text = ""
        for page in pdf.pages:
            text += (page.extract_text() or "") + "\n"

    month_map = {"jan":"01","feb":"02","mar":"03","apr":"04",
                 "may":"05","jun":"06","jul":"07","aug":"08",
                 "sep":"09","oct":"10","nov":"11","dec":"12"}

    for line in text.splitlines():
        # Match "Jan 2026:" or "Feb 2026:" etc.
        m_month = re.match(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4}):", line.strip(), re.I)
        if not m_month:
            continue
        mn = month_map[m_month.group(1).lower()]
        month_str = f"{m_month.group(2)}-{mn}"

        # Base plan
        base_m = re.search(r"Base\s+\$?([\d.]+)", line, re.I)
        if base_m:
            rows.append({"source_file":"invoice_acct_003.pdf","account_id":"acct_003",
                         "invoice_month":month_str,"line_description":"Base Plan",
                         "quantity":1,"unit_price":float(base_m.group(1)),
                         "line_amount":float(base_m.group(1)),"line_type":"base_plan"})

        # Overage with embedded tax: "32,000 calls at $0.002/call = $64.00 (incl. tax $10.24) | Line total $74.24"
        over_m = re.search(r"([\d,]+)\s+calls\s+at\s+\$([\d.]+)/call\s*=\s*\$([\d.]+)\s*\(incl\.\s+tax\s+\$([\d.]+)\)", line, re.I)
        if over_m:
            qty    = int(over_m.group(1).replace(",",""))
            rate   = float(over_m.group(2))
            over_amt = float(over_m.group(3))
            tax_amt  = float(over_m.group(4))
            total_billed = over_amt + tax_amt
            rows.append({"source_file":"invoice_acct_003.pdf","account_id":"acct_003",
                         "invoice_month":month_str,
                         "line_description":f"API Overage {over_m.group(1)} calls",
                         "quantity":qty,"unit_price":rate,"line_amount":total_billed,
                         "line_type":"overage"})
            rows.append({"source_file":"invoice_acct_003.pdf","account_id":"acct_003",
                         "invoice_month":month_str,"line_description":"Sales Tax on Overage",
                         "quantity":0,"unit_price":0,"line_amount":tax_amt,
                         "line_type":"tax"})
        else:
            plain_over = re.search(r"([\d,]+)\s+calls\s+at\s+\$([\d.]+)/call\s*=\s*\$([\d.]+)", line, re.I)
            if plain_over:
                qty = int(plain_over.group(1).replace(",", ""))
                rate = float(plain_over.group(2))
                amt = float(plain_over.group(3))
                rows.append({"source_file":"invoice_acct_003.pdf","account_id":"acct_003",
                             "invoice_month":month_str,
                             "line_description":f"API Overage {plain_over.group(1)} calls",
                             "quantity":qty,"unit_price":rate,"line_amount":amt,
                             "line_type":"overage"})
            elif re.search(r"No API overage", line, re.I):
                pass

    return rows


invoice_lines += parse_invoice_001("/root/data/invoices/invoice_acct_001.pdf")
invoice_lines += parse_invoice_002("/root/data/invoices/invoice_acct_002.pdf")
invoice_lines += parse_invoice_003("/root/data/invoices/invoice_acct_003.pdf")

print(f"Extracted {len(invoice_lines)} invoice lines total")

# Build billed overage lookup from extracted lines (invoice currency)
billed_overage_raw = {}
for il in invoice_lines:
    if il["line_type"] == "overage":
        key = (il["account_id"], il["invoice_month"])
        billed_overage_raw[key] = billed_overage_raw.get(key, 0) + il["line_amount"]

# Tax lookup (tax lines in invoice)
billed_tax = {}
for il in invoice_lines:
    if il["line_type"] == "tax":
        key = (il["account_id"], il["invoice_month"])
        billed_tax[key] = billed_tax.get(key, 0) + il["line_amount"]


# ── 4. Compute expected overage ───────────────────────────────────────────────

expected_rows = []
for _, urow in usage_df.iterrows():
    acct   = urow["account_id"]
    month  = urow["service_month"]
    calls  = int(urow["api_calls"])
    legacy = acct in legacy_accts
    adj = legacy_overrides.get((acct, month), {})

    charge, billable, t1, t2, disc_applied = compute_overage(
        calls,
        legacy,
        billable_override=adj.get("billable_calls"),
        tier2_override=adj.get("tier2_calls"),
    )
    src = "pricing_addendum.pdf: Tier 1" if t2 == 0 else "pricing_addendum.pdf: Tier 1 + Tier 2"
    if disc_applied:
        src += "; pricing_addendum.pdf: Enterprise Legacy Discount"

    expected_rows.append({
        "account_id":          acct,
        "service_month":       month,
        "actual_calls":        calls,
        "included_calls":      INCLUDED,
        "billable_calls":      billable,
        "tier1_calls":         t1,
        "tier2_calls":         t2,
        "expected_overage_usd": charge,
        "discount_applied":    disc_applied,
        "pricing_rule_source": src,
    })

expected_rows.sort(key=lambda r: (r["account_id"], r["service_month"]))


# ── 5. Reconciliation ─────────────────────────────────────────────────────────

expected_by_key = {(er["account_id"], er["service_month"]): er for er in expected_rows}

recon_rows = []
for er in expected_rows:
    key    = (er["account_id"], er["service_month"])
    raw_billed = billed_overage_raw.get(key, 0.0)
    billed = to_usd(er["account_id"], er["service_month"], raw_billed)
    tax    = round(billed_tax.get(key, 0.0), 2)
    expect = er["expected_overage_usd"]

    delta = round(billed - expect, 2)
    disc_delta = round(delta, 2) if (delta > TOLERANCE and er["discount_applied"]) else 0.0

    recon_rows.append({
        "account_id":          er["account_id"],
        "service_month":       er["service_month"],
        "expected_overage_usd": expect,
        "billed_overage_usd":  billed,
        "delta_usd":           delta,
        "tax_excluded_usd":    tax,
        "discount_delta_usd":  disc_delta,
    })

recon_rows.sort(key=lambda r: (r["account_id"], r["service_month"]))


# ── 6. Classify exceptions ────────────────────────────────────────────────────

# Build support ticket context
ticket_context = {}
for _, t in tickets.iterrows():
    ticket_context[t["account_id"]] = t["notes"]

exceptions = []
exc_counter = 0

for rr in recon_rows:
    delta = rr["delta_usd"]
    tax   = rr["tax_excluded_usd"]
    if abs(delta) < TOLERANCE and abs(tax) < TOLERANCE:
        continue

    exc_counter += 1
    exc_id = f"EXC-{exc_counter:03d}"
    acct   = rr["account_id"]
    month  = rr["service_month"]
    er     = expected_by_key[(acct, month)]
    raw_billed = billed_overage_raw.get((acct, month), 0.0)

    if abs(tax) > TOLERANCE:
        exc_type = "TAX_INCLUDED"
        severity = "High"
        src_ref  = (f"invoices/invoice_acct_003.pdf: {month} overage line (incl. tax); "
                    f"pricing_addendum.pdf: Tax Policy; pricing_addendum.pdf: Dispute Severity Framework")
    elif delta > TOLERANCE and is_wrong_tier_invoice(er, raw_billed):
        exc_type = "WRONG_TIER"
        severity = "Medium"
        src_ref  = (f"invoices/invoice_acct_003.pdf: {month} overage; "
                    f"usage_logs.csv; pricing_addendum.pdf: Dispute Severity Framework")
    elif delta > TOLERANCE and er["discount_applied"]:
        exc_type = "OVERBILLED"
        severity = "Medium"
        src_ref  = (f"invoices/invoice_acct_002.pdf: {month} overage; "
                    f"pricing_addendum.pdf: Enterprise Legacy Discount; "
                    f"pricing_addendum.pdf: Dispute Severity Framework")
    elif delta > TOLERANCE:
        exc_type = "OVERBILLED"
        severity = "Medium"
        src_ref  = f"invoices/{acct}: {month}; usage_logs.csv"
    else:
        exc_type = "UNDERBILLED"
        severity = "Medium"
        src_ref  = f"invoices/{acct}: {month}; usage_logs.csv"

    exceptions.append({
        "exception_id":     exc_id,
        "account_id":       acct,
        "service_month":    month,
        "exception_type":   exc_type,
        "severity":         severity,
        "delta_usd":        round(abs(delta), 2),
        "source_reference": src_ref,
    })


# ── 7. Executive Summary ──────────────────────────────────────────────────────

total_overbilled = round(sum(
    rr["delta_usd"]
    for rr in recon_rows
    if rr["delta_usd"] > TOLERANCE
), 2)
total_underbilled = round(sum(
    abs(rr["delta_usd"])
    for rr in recon_rows
    if rr["delta_usd"] < -TOLERANCE
), 2)

# Highest risk = account with largest total absolute delta
acct_deltas = {}
for rr in recon_rows:
    total = abs(rr["delta_usd"]) + abs(rr["tax_excluded_usd"])
    acct_deltas[rr["account_id"]] = acct_deltas.get(rr["account_id"], 0) + total
highest_risk = max(acct_deltas, key=acct_deltas.get) if acct_deltas else "N/A"

has_high   = any(e["severity"] == "High" for e in exceptions)
non_zero   = len(exceptions) > 0

if has_high or total_overbilled > 500:
    rec_action = "Immediate Action"
elif total_overbilled > 100:
    rec_action = "Issue Credit"
elif non_zero:
    rec_action = "Investigate"
else:
    rec_action = "No Action"


# ── 8. Write workbook ─────────────────────────────────────────────────────────

wb = Workbook()
wb.remove(wb.active)

# Sheet 1: Extracted Invoice Lines
ws = wb.create_sheet("Extracted Invoice Lines")
ws.append(["source_file", "account_id", "invoice_month", "line_description",
           "quantity", "unit_price", "line_amount", "line_type"])
il_sorted = sorted(invoice_lines, key=lambda r: (r["account_id"], r["invoice_month"], r["line_type"]))
for il in il_sorted:
    ws.append([il["source_file"], il["account_id"], il["invoice_month"],
               il["line_description"], float(il["quantity"]), float(il["unit_price"]),
               float(il["line_amount"]), il["line_type"]])

# Sheet 2: Expected Usage Charges
ws = wb.create_sheet("Expected Usage Charges")
ws.append(["account_id", "service_month", "actual_calls", "included_calls",
           "billable_calls", "tier1_calls", "tier2_calls",
           "expected_overage_usd", "discount_applied", "pricing_rule_source"])
for er in expected_rows:
    ws.append([er["account_id"], er["service_month"], int(er["actual_calls"]),
               int(er["included_calls"]), int(er["billable_calls"]),
               int(er["tier1_calls"]), int(er["tier2_calls"]),
               float(er["expected_overage_usd"]), bool(er["discount_applied"]),
               er["pricing_rule_source"]])

# Sheet 3: Billing Reconciliation
ws = wb.create_sheet("Billing Reconciliation")
ws.append(["account_id", "service_month", "expected_overage_usd", "billed_overage_usd",
           "delta_usd", "tax_excluded_usd", "discount_delta_usd"])
for rr in recon_rows:
    ws.append([rr["account_id"], rr["service_month"],
               float(rr["expected_overage_usd"]), float(rr["billed_overage_usd"]),
               float(rr["delta_usd"]), float(rr["tax_excluded_usd"]),
               float(rr["discount_delta_usd"])])

# Sheet 4: Dispute Exceptions
ws = wb.create_sheet("Dispute Exceptions")
ws.append(["exception_id", "account_id", "service_month", "exception_type",
           "severity", "delta_usd", "source_reference"])
for e in exceptions:
    ws.append([e["exception_id"], e["account_id"], e["service_month"],
               e["exception_type"], e["severity"], float(e["delta_usd"]),
               e["source_reference"]])

# Sheet 5: Executive Summary
ws = wb.create_sheet("Executive Summary")
ws.append(["metric", "value"])
ws.append(["total_accounts_reviewed", int(customers["account_id"].nunique())])
ws.append(["total_overbilled_usd",    total_overbilled])
ws.append(["total_underbilled_usd",   total_underbilled])
ws.append(["highest_risk_account",    highest_risk])
ws.append(["recommended_action",      rec_action])

wb.save("/root/out/billing_dispute_audit.xlsx")
print("Saved /root/out/billing_dispute_audit.xlsx")
print(f"  Extracted invoice lines: {len(invoice_lines)}")
print(f"  Expected usage rows:     {len(expected_rows)}")
print(f"  Reconciliation rows:     {len(recon_rows)}")
print(f"  Exceptions:              {len(exceptions)}")
print(f"  Total overbilled:        ${total_overbilled}")
print(f"  Highest risk account:    {highest_risk}")
print(f"  Recommended action:      {rec_action}")
for e in exceptions:
    print(f"    {e['exception_id']} [{e['exception_type']}] {e['account_id']} {e['service_month']}: ${e['delta_usd']}")
PYEOF
