---
name: spreadsheet-input-guidance
description: General guidance for reading business spreadsheets and tabular exports. Use when numeric columns load as strings or NaN, or when workbook structure is unclear.
---

# Spreadsheet Input Guidance

Business data exports often use formatting conventions that cause silent parsing failures in pandas.

## CSV Numeric Columns

If a column that should be numeric loads as `object` dtype, inspect sample raw values before casting. Common business exports may include display formatting such as currency symbols, separators, or whitespace.

Example diagnostic:
```python
print(df["column_name"].head())
print(df["column_name"].dtype)
```

## Repairing Existing Workbooks

When a task asks to repair or update an existing workbook, prefer loading and modifying that workbook rather than recreating it from scratch. Hidden sheets, formulas, styles, and data validations may matter.

## Multi-Sheet Excel Workbooks

Business workbooks often include cover or metadata sheets. Inspect sheet names before loading tabular data:

```python
import openpyxl
wb = openpyxl.load_workbook(path, read_only=True)
print(wb.sheetnames)
```

Then load the sheet that contains the actual data table, not a cover or summary sheet.

## Semi-Structured Records

Semi-structured records may contain inconsistent value representations across rows. Before aggregating a numeric field, inspect a few raw records and confirm the field has been normalized to a numeric type.

## Numeric Type Verification

After loading any business spreadsheet, CSV, or record file:
- Verify numeric columns are numeric dtypes, not `object`.
- Use `pd.to_numeric(..., errors="coerce")` only as a diagnostic — if many values become NaN, the source format was not handled correctly.
- Final numeric outputs should be stored as numbers, not text.

## Reusable Script

Use `scripts/inspect_workbook.py` to list sheet names and preview cell values before loading.

```bash
python3 scripts/inspect_workbook.py <workbook.xlsx>
python3 scripts/inspect_workbook.py <workbook.xlsx> <sheet_name>
```
