---
name: data-reconciliation
description: Reconcile billed amounts against expected amounts across multiple sources. Use when comparing invoice data to computed expected charges to identify discrepancies and classify exceptions.
---

# Data Reconciliation

## Reconciliation Workflow

1. For each account and service month, compute the expected charge from authoritative sources (usage logs, legacy adjustment workbook, and pricing rules).
2. Extract the billed charge from the invoice.
3. Compute the delta: `billed - expected`. Positive = overbilled, negative = underbilled.
4. Identify the cause of each non-zero delta.
5. Classify each discrepancy with an exact exception type and severity from the pricing addendum framework.

## Exception Classification

Use only the exact exception type strings specified in the task instruction. Do not invent new types.

Apply the Dispute Severity Framework from `pricing_addendum.pdf` when assigning severity.

## Source References

Every exception must cite which source files and specific fields confirmed the finding. Reference both the invoice PDF and the relevant authoritative source (pricing addendum, usage logs, legacy workbook, customer registry, or support ticket).

## Support Tickets

Review `support_tickets.csv` for context on disputed charges. Ticket notes may clarify the cause of a delta or confirm the correct interpretation of an exception type.
