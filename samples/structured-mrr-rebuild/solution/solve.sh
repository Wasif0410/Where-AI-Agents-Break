#!/bin/bash
# Reference solution for structured-mrr-rebuild.
# Handles all business rules including:
#   - string normalisation: line_type lowercased, currency stripped+uppercased,
#     billing_interval lowercased (raw export may use "Annual", "Subscription", " CAD", etc.)
#   - service-month FX rate (not invoice-month)
#   - annual ÷12 and quarterly ÷3 normalisation across USD, EUR, CAD, GBP
#   - revenue placed in service_start month only (handles catchup billing, late invoices)
#   - negative subscription adjustments (downgrade credits count at face value)
#   - non-adjacent duplicate invoice_line_id deduplication
#   - multi-subscription aggregation (one MRR row per account per month)
#   - multi-month account continuity with prorations
#   - max_mrr_account_id: account with highest TOTAL MRR across all months
#   - max_mrr_month: month with highest AGGREGATE MRR across all accounts
#   - monthly_summary.csv: month-over-month aggregate with MoM change metrics

python3 - << 'PYEOF'
import json
import pandas as pd
from pathlib import Path

Path("/root/out").mkdir(parents=True, exist_ok=True)

# ── Load input files ──────────────────────────────────────────────────────────

customers     = pd.read_csv("/root/data/customers.csv")
subscriptions = pd.read_json("/root/data/subscriptions.jsonl", lines=True)
invoice_lines = pd.read_csv("/root/data/invoice_lines.csv", dtype={"subscription_id": str})
fx_rates      = pd.read_csv("/root/data/fx_rates.csv")

# ── Normalise raw export fields ───────────────────────────────────────────────
# Raw billing exports may ship with incidental whitespace, mixed casing,
# currency-formatted amount strings (e.g. "$319.00"), or non-standard
# capitalisation (e.g. " CAD", "Subscription", "Annual").

def parse_amount(val):
    if pd.isna(val):
        return float("nan")
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace("$", "").replace(",", "")
    return float(s)

invoice_lines["amount"]     = invoice_lines["amount"].apply(parse_amount)
invoice_lines["tax_amount"] = invoice_lines["tax_amount"].apply(parse_amount)
invoice_lines["currency"]   = invoice_lines["currency"].str.strip().str.upper()
invoice_lines["line_type"]  = invoice_lines["line_type"].str.strip().str.lower()
subscriptions["billing_interval"] = subscriptions["billing_interval"].str.strip().str.lower()

# ── Deduplicate invoice lines ─────────────────────────────────────────────────
# Some rows are exported more than once with the same invoice_line_id.
# Drop duplicates across the full dataset so non-adjacent copies are removed too.

invoice_lines = invoice_lines.drop_duplicates(subset=["invoice_line_id"])

# ── Derive revenue month from service_start, not invoice_date ────────────────

invoice_lines["service_start"] = pd.to_datetime(invoice_lines["service_start"])
invoice_lines["month"] = invoice_lines["service_start"].dt.strftime("%Y-%m")

# ── Compute excluded non-recurring totals (setup_fee, professional_services, usage)

non_recurring = invoice_lines[
    invoice_lines["line_type"].isin(["setup_fee", "professional_services", "usage"])
].copy()
non_recurring = non_recurring.merge(fx_rates, on=["month", "currency"], how="left")
non_recurring["usd_rate"] = non_recurring["usd_rate"].fillna(1.0)
non_recurring["amount_usd"] = non_recurring["amount"] * non_recurring["usd_rate"]
excluded_non_recurring_total = round(float(non_recurring["amount_usd"].sum()), 2)

# ── Compute tax excluded from subscription lines ──────────────────────────────

all_sub = invoice_lines[invoice_lines["line_type"] == "subscription"].copy()
all_sub = all_sub.merge(fx_rates, on=["month", "currency"], how="left")
all_sub["usd_rate"] = all_sub["usd_rate"].fillna(1.0)
all_sub["tax_usd"] = all_sub["tax_amount"] * all_sub["usd_rate"]
tax_excluded_total = round(float(all_sub["tax_usd"].sum()), 2)

# ── Filter to subscription lines only ────────────────────────────────────────

sub_lines = invoice_lines[invoice_lines["line_type"] == "subscription"].copy()

# ── Join billing_interval from subscriptions ──────────────────────────────────

sub_lines = sub_lines.merge(
    subscriptions[["subscription_id", "billing_interval"]],
    on="subscription_id",
    how="left"
)

# ── Join FX rates on (service month, currency) ────────────────────────────────
# Using service month ensures the correct FX rate is applied even when the
# invoice was raised in a prior month with a different rate.

sub_lines = sub_lines.merge(
    fx_rates,
    on=["month", "currency"],
    how="left"
)
sub_lines["usd_rate"] = sub_lines["usd_rate"].fillna(1.0)

# ── Normalise all billing intervals to a monthly run rate ────────────────────
# annual    → ÷12   quarterly → ÷3   monthly → as-is
# Include negative amounts as-is — mid-cycle credits are valid at face value.

_interval_divisors = {"annual": 12.0, "quarterly": 3.0}
sub_lines["base_amount"] = sub_lines.apply(
    lambda row: row["amount"] / _interval_divisors.get(str(row["billing_interval"]), 1.0),
    axis=1
)

# ── Convert to USD ────────────────────────────────────────────────────────────

sub_lines["amount_usd"] = sub_lines["base_amount"] * sub_lines["usd_rate"]

# ── Aggregate MRR by account and month ───────────────────────────────────────

mrr = (
    sub_lines
    .groupby(["account_id", "month"], as_index=False)
    .agg(
        mrr_usd=("amount_usd", "sum"),
        source_line_count=("invoice_line_id", "count"),
    )
)
mrr["mrr_usd"] = mrr["mrr_usd"].round(2)

# ── Join customer names ───────────────────────────────────────────────────────

mrr = mrr.merge(
    customers[["account_id", "customer_name"]],
    on="account_id",
    how="left"
)

mrr = mrr[["account_id", "customer_name", "month", "mrr_usd", "source_line_count"]]
mrr = mrr.sort_values(["month", "account_id"]).reset_index(drop=True)

# ── Write mrr_by_account.parquet ──────────────────────────────────────────────

mrr.to_parquet("/root/out/mrr_by_account.parquet", index=False)
print("Wrote /root/out/mrr_by_account.parquet")

# ── Build summary ─────────────────────────────────────────────────────────────
# max_mrr_account_id: account with the highest TOTAL MRR across all months.
# max_mrr_month:      month with the highest AGGREGATE MRR across all accounts.
# These require group-by aggregation — single-row idxmax gives the wrong answer.

total_mrr     = round(float(mrr["mrr_usd"].sum()), 2)
account_count = int(mrr["account_id"].nunique())
month_count   = int(mrr["month"].nunique())

account_totals  = mrr.groupby("account_id")["mrr_usd"].sum()
max_mrr_account = str(account_totals.idxmax())

month_totals  = mrr.groupby("month")["mrr_usd"].sum()
max_mrr_month = str(month_totals.idxmax())

summary = {
    "total_mrr_usd":                    total_mrr,
    "account_count":                    account_count,
    "month_count":                      month_count,
    "max_mrr_account_id":               max_mrr_account,
    "max_mrr_month":                    max_mrr_month,
    "excluded_non_recurring_total_usd": excluded_non_recurring_total,
    "tax_excluded_total_usd":           tax_excluded_total,
}

with open("/root/out/mrr_summary.json", "w") as f:
    json.dump(summary, f, indent=2)
print("Wrote /root/out/mrr_summary.json")

# ── Write monthly_summary.csv ─────────────────────────────────────────────────
# One row per reporting month. mrr_change_usd and mrr_change_pct are the
# change vs the prior month; blank for the first month (no prior period).

monthly = (
    mrr.groupby("month")
    .agg(total_mrr_usd=("mrr_usd", "sum"), account_count=("account_id", "nunique"))
    .reset_index()
    .sort_values("month")
)
monthly["total_mrr_usd"] = monthly["total_mrr_usd"].round(2)

monthly["mrr_change_usd"] = monthly["total_mrr_usd"].diff().round(2)
monthly["mrr_change_pct"] = (
    monthly["total_mrr_usd"].diff() / monthly["total_mrr_usd"].shift(1)
).round(4)

monthly.to_csv("/root/out/monthly_summary.csv", index=False)
print("Wrote /root/out/monthly_summary.csv")

print("\nMRR by account:")
print(mrr.to_string(index=False))
print("\nSummary:")
for k, v in summary.items():
    print(f"  {k}: {v}")
print("\nMonthly summary:")
print(monthly.to_string(index=False))
PYEOF
