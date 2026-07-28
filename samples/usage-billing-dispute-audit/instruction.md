# Usage Billing Dispute Audit

Our finance team has received billing disputes from three enterprise customers for Q1 2026 (January through March). Vendor invoices, usage logs, and pricing terms do not fully align. Your task is to extract invoice line items from each account's PDF invoice, compute the correct charges using the authoritative pricing rules, reconcile billed vs expected amounts, classify any discrepancies, and produce a structured audit workbook.

All input files are under `/root/data`:

- `invoices/invoice_acct_001.pdf` — Q1 2026 invoice for account acct_001
- `invoices/invoice_acct_002.pdf` — Q1 2026 invoice for account acct_002
- `invoices/invoice_acct_003.pdf` — Q1 2026 invoice for account acct_003
- `pricing_addendum.pdf` — authoritative pricing rules including tier rates, rounding policy, discount eligibility, tax policy, and dispute severity framework. Pricing parameters must come from this document, not from assumptions.
- `legacy_call_adjustments.xlsx` — authoritative call-count overrides from the prior billing system for specific account-months
- `customers.csv` — account registry including segment and legacy status
- `usage_logs.csv` — metered API call counts per account per month
- `fx_rates.csv` — monthly exchange rates for multi-currency billing
- `support_tickets.csv` — customer-submitted dispute notes providing context

**Note:** Each invoice PDF uses a different layout. You must handle each format independently. Authoritative pricing, currency, and adjustment policies are in `pricing_addendum.pdf`.

Produce a single Excel workbook at `/root/out/billing_dispute_audit.xlsx`. Create `/root/out` if it does not exist.

The workbook must have exactly five sheets in this order:

1. **Extracted Invoice Lines**
2. **Expected Usage Charges**
3. **Billing Reconciliation**
4. **Dispute Exceptions**
5. **Executive Summary**

Write computed numeric literals (int/float) in all numeric cells. Do not write Excel formulas in the output workbook.

---

## Sheet 1: Extracted Invoice Lines

One row per line item extracted from each invoice PDF. Capture what is actually on the invoice — do not adjust values here.

Header row (row 1):

`source_file, account_id, invoice_month, line_description, quantity, unit_price, line_amount, line_type`

- `source_file`: filename (e.g. `invoice_acct_001.pdf`)
- `invoice_month`: `YYYY-MM` format
- `line_type`: `base_plan`, `overage`, or `tax`
- `quantity`: numeric (0 if not applicable)
- `unit_price`: numeric (0 if not applicable)
- `line_amount`: the amount exactly as billed on the invoice

Sort by `account_id` then `invoice_month` then `line_type`.

---

## Sheet 2: Expected Usage Charges

One row per account per service month showing what the charge **should** be based on authoritative pricing rules and metered usage.

Header row (row 1):

`account_id, service_month, actual_calls, included_calls, billable_calls, tier1_calls, tier2_calls, expected_overage_usd, discount_applied, pricing_rule_source`

- `included_calls`: the base allocation per month (from pricing addendum)
- `billable_calls`: actual_calls minus included_calls, rounded up per addendum rounding policy (0 if negative); use legacy workbook override when present
- `tier1_calls`, `tier2_calls`: calls in each pricing tier; use legacy workbook `tier2_calls` override when present
- `expected_overage_usd`: computed charge after applying tier rates, rounding, and any applicable discount
- `discount_applied`: boolean — whether a discount was applied to this account
- `pricing_rule_source`: citation like `pricing_addendum.pdf: Tier 1` or `pricing_addendum.pdf: Enterprise Legacy Discount`

Sort by `account_id` then `service_month`.

---

## Sheet 3: Billing Reconciliation

One row per account per service month comparing billed to expected overage.

Header row (row 1):

`account_id, service_month, expected_overage_usd, billed_overage_usd, delta_usd, tax_excluded_usd, discount_delta_usd`

- `delta_usd`: `billed_overage_usd - expected_overage_usd` (positive = overbilled, negative = underbilled)
- `tax_excluded_usd`: amount of tax identified in the invoice that was excluded from the expected charge
- `discount_delta_usd`: overage discount not applied to the invoice (0 if discount was correctly applied)

Where invoice overage includes tax, expected charges follow the pricing addendum tax policy; reconciliation compares billed invoice amounts to those expected charges. Reconciliation amounts are expressed in USD per the pricing addendum.

Sort by `account_id` then `service_month`.

---

## Sheet 4: Dispute Exceptions

One row per account per service month where the delta is non-zero, plus one row per support ticket context finding. OK months may be omitted.

Header row (row 1):

`exception_id, account_id, service_month, exception_type, severity, delta_usd, source_reference`

- `exception_id`: sequential, starting from `EXC-001`
- `exception_type`: exactly one of: `OVERBILLED`, `UNDERBILLED`, `WRONG_TIER`, `TAX_INCLUDED`
- `severity`: exactly `High`, `Medium`, or `Low` — apply the Dispute Severity Framework from `pricing_addendum.pdf`
- `source_reference`: which file(s) and field(s) confirm the finding (e.g. `invoices/invoice_acct_002.pdf: Jan overage; pricing_addendum.pdf: Enterprise Legacy Discount`)

---

## Sheet 5: Executive Summary

Exact cell layout starting at row 1 with header `metric, value`:

| Row | metric | value |
|---|---|---|
| 2 | `total_accounts_reviewed` | integer count |
| 3 | `total_overbilled_usd` | sum of positive deltas, rounded to 2 dp |
| 4 | `total_underbilled_usd` | sum of absolute negative deltas, rounded to 2 dp |
| 5 | `highest_risk_account` | account_id with the largest total absolute delta |
| 6 | `recommended_action` | see rule below |

`recommended_action` rule:
- `Immediate Action` if any exception has `severity = High` OR `total_overbilled_usd > 500`
- `Issue Credit` if `total_overbilled_usd > 100`
- `Investigate` if any non-zero delta exists
- `No Action` otherwise

All numeric values must be stored as numbers, not strings.
