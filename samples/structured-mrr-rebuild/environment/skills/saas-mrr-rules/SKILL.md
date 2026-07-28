---
name: saas-mrr-rules
description: SaaS revenue concepts for MRR analytics. Use when reasoning about what counts as recurring revenue, how to handle billing intervals, currency normalization, and service-period alignment.
---

# SaaS MRR Concepts

Monthly Recurring Revenue (MRR) is the normalized monthly value of recurring subscription contracts.

## What counts as MRR

Only subscription charges count. One-time fees, implementation services, usage overages, and tax lines are not recurring revenue and must be excluded.

Tax is not MRR. In this task, `amount` already represents the pre-tax charge for the invoice line. `tax_amount` is recorded separately and should only be used for tax reporting fields such as `tax_excluded_total_usd`. Do not subtract `tax_amount` from `amount`.

## Billing interval normalization

The `billing_interval` field in `subscriptions.jsonl` defines the billing period for each contract. When a contract is not billed monthly, the invoice amount covers multiple months of service. That multi-month amount must be converted to a monthly run-rate value before aggregating into MRR.

The normalised amount is placed in the service_start month only — it is not projected or duplicated across the months covered by the invoice. The service_start field on the invoice line determines which output month the revenue belongs to, regardless of when the invoice was issued.

## Service period vs invoice date

The billing system raises invoices before or after the service period. Revenue belongs to the month the service was actually delivered, not the month the invoice was generated.

## Multi-currency

The company operates in multiple currencies. All MRR figures must be expressed in USD using the provided exchange rate table.

## Billing export quality

Raw billing exports from subscription systems commonly contain mixed casing, incidental whitespace, currency-formatted amount strings, and duplicate rows for the same invoice line. Inspect and normalise raw values before computing any aggregates.

## Prorations

When a customer upgrades or downgrades mid-cycle, the system generates prorated subscription lines. These represent genuine recurring revenue for the partial period and should be included.
