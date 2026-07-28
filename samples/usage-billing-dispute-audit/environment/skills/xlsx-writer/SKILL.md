---
name: xlsx-writer
description: Write multi-sheet Excel workbooks with openpyxl. Use when producing the required output workbook with correct sheet names, typed cells, and deterministic row order.
---

# Excel Workbook Output

Use `openpyxl` to create the output workbook. Sheets must appear in the exact order specified by the task.

## Core Rules

- Use exact sheet names required by the task.
- Write computed numeric literals — not Excel formulas — in numeric cells.
- Keep row order deterministic.
- Headers explicit and stable.

## Build Pattern

1. Create workbook, remove the default sheet.
2. Create each required sheet by exact name in the required order.
3. Write one header row per sheet.
4. Append typed rows with literal values.
5. Save once to the final path.

## Numeric Guidance

- Store monetary values rounded to 2 decimal places.
- Store boolean fields as Python `True` / `False`.
- Store integer counts as `int`.
- Do not write formatted display text in numeric columns.

## Output Directory

```python
from pathlib import Path
Path("/root/out").mkdir(parents=True, exist_ok=True)
```
