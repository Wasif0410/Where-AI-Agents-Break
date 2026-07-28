---
name: billing-analytics
description: SaaS usage billing concepts for overage calculation, tiered pricing, discount application, and tax separation. Use when computing expected charges from usage logs and pricing rules.
---

# Usage Billing Analytics

## Overage Calculation

Overage is the API call count above the included monthly allocation. Only billable overage is subject to pricing tiers.

When pricing applies a rounding policy, apply it to the total billable overage before computing the charge, not after.

## Tiered Pricing

Different usage volumes may be billed at different per-call rates. Read the exact tier boundaries and rates from the pricing document — do not assume standard values.

Apply tiers in sequence: the first tier covers usage up to its ceiling, then the next tier covers the remainder, and so on.

## Discounts

Account-level discounts may apply to total overage charges. Check each account's eligibility in the customer registry and verify the discount criteria in the pricing document.

Apply the discount to the pre-tax total overage charge.

## Tax Separation

Tax is not part of the usage charge. When an invoice line appears to include tax in the overage amount, separate the tax component and classify it with its own `line_type` in the extracted invoice lines. Expected overage excludes tax; reconciliation still reflects what the invoice actually billed.

## Multi-Currency Billing

Some accounts are invoiced in non-USD currency. Read the pricing addendum for currency policy and use `fx_rates.csv` when reconciling in USD.

## Rounding

Apply rounding as specified in the pricing document before applying per-call rates.

## Legacy Adjustments

When a supplemental workbook provides authoritative call-count overrides, evaluate those cells using standard Excel formula semantics before computing expected charges.

## Source References

When computing expected charges, record which part of which document provided the pricing rule used. This is required in the output.
