# Output Schema Reference

## mrr_by_account.parquet

```
account_id        string
customer_name     string
month             string  YYYY-MM
mrr_usd           float64 rounded to 2 decimals
source_line_count int64
```

Grain: one row per (account_id, month).
Sort: month ASC, account_id ASC.

## mrr_summary.json

```json
{
  "total_mrr_usd":                    <float, 2dp>,
  "account_count":                    <int>,
  "month_count":                      <int>,
  "max_mrr_account_id":               <string>,
  "max_mrr_month":                    <string, YYYY-MM>,
  "excluded_non_recurring_total_usd": <float, 2dp>,
  "tax_excluded_total_usd":           <float, 2dp>
}
```

No extra keys. No missing keys.

## monthly_summary.csv

```
month            string  YYYY-MM
total_mrr_usd    float   2dp
account_count    int
mrr_change_usd   float   2dp or blank for first month
mrr_change_pct   float   4dp or blank for first month
```

One row per reporting month, sorted chronologically.
