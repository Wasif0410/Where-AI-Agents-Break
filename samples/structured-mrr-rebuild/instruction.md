# MRR Rebuild — SaaS Billing Cleanup

Our finance team needs a clean Monthly Recurring Revenue (MRR) view from the billing system. The raw export is noisy — it mixes recurring subscription charges with one-time fees, includes tax on some lines, and occasionally ships duplicate rows. Some invoices are also issued before the service period starts, so the invoice date doesn't always reflect when the revenue was earned.

All input files are under `/root/data`:

- `customers.csv` — account registry
- `subscriptions.jsonl` — subscription contracts, including billing frequency and currency
- `invoice_lines.csv` — raw billing export from the billing system
- `fx_rates.csv` — monthly exchange rates to USD

Create `/root/out` if it does not exist, then produce:

1. `/root/out/mrr_by_account.parquet`
2. `/root/out/mrr_summary.json`
3. `/root/out/monthly_summary.csv`

MRR is the normalized monthly value of recurring subscription revenue. Revenue belongs to the month the service was delivered — each invoice line contributes only to the month identified by its service_start date, regardless of when the invoice was issued. Contracts may be billed monthly, quarterly, or annually; any non-monthly billing interval must be expressed as a monthly run rate and placed in the service_start month only. Do not project or expand invoice amounts across future months. Everything should be in USD. Non-subscription charges are not MRR: `setup_fee`, `professional_services` (including implementation/onboarding work), and `usage` line types in the export. Tax is also not MRR. The `amount` column is the pre-tax line amount. The `tax_amount` column is a separate tax charge recorded for audit purposes. Do not add `tax_amount` to MRR and do not subtract it from `amount`; use `amount` directly for recurring revenue calculations. Some invoice rows appear more than once in the export; each unique invoice line should be counted only once. The export has been pulled directly from the operational billing system and may contain formatting inconsistencies — mixed casing (e.g. `Annual`, `Subscription`), incidental whitespace in categorical fields, or currency-formatted amount strings (e.g. `$319.00`) — that require normalisation before filtering or joining. Mid-cycle subscription adjustments reflect real contracted changes and should be included at their actual amounts, including negative credit lines.

The parquet file must have exactly these columns, one row per account per month, sorted by month then account ID:

- `account_id`
- `customer_name`
- `month` (formatted as `YYYY-MM`)
- `mrr_usd` (float, rounded to 2 decimal places)
- `source_line_count` (integer)

The JSON summary must have exactly these keys:

- `total_mrr_usd`
- `account_count`
- `month_count`
- `max_mrr_account_id` — the account with the highest total MRR summed across all months
- `max_mrr_month` — the calendar month with the highest aggregate MRR across all accounts
- `excluded_non_recurring_total_usd` — USD total of one-time charges excluded from MRR (`setup_fee`, `professional_services`, and `usage` lines), converted at each line's service-month FX rate
- `tax_excluded_total_usd` — USD total of tax recorded on subscription lines that contributed to MRR (at service-month FX); this is what would have been included if tax were not kept separate from the pre-tax `amount`

The monthly summary CSV must have exactly these columns, one row per reporting month sorted chronologically:

- `month` (formatted as `YYYY-MM`)
- `total_mrr_usd` — total MRR across all accounts for that month, rounded to 2 decimal places
- `account_count` — number of distinct accounts with MRR in that month
- `mrr_change_usd` — difference vs the prior month's total MRR, rounded to 2 decimal places (blank for the first month)
- `mrr_change_pct` — `mrr_change_usd / prior_month_total_mrr_usd`, rounded to 4 decimal places (blank for the first month)

Do not include explanatory text in the output files. Only create the three required files.
