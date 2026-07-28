---
name: sqlite-query
description: Query a SQLite database with Python. Use when reading from a warehouse database to build features, inspect schemas, or verify data availability constraints.
---

# SQLite Query Patterns

## Connect and Inspect

Use the bundled `inspect_warehouse.py` script (if present) or query `sqlite_master` and `PRAGMA table_info` to discover schemas and temporal columns before auditing features.

## Parameterized Queries

Always bind parameters — never interpolate user-controlled strings into SQL.

## Date Filtering

ISO date strings compare correctly lexicographically. Read the availability document for each feature family to determine whether the cutoff is strictly before period open, on or before a prior period end, or another rule. Different families use different boundaries.

## Aggregation Before Join

Aggregate one-to-many sources to account grain before merging into the account-month matrix.

## Checking Availability

For each pipeline column, identify the controlling timestamp column in the warehouse and verify it against the PDF rule for the mapped feature family.
