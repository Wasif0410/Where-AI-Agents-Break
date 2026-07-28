#!/usr/bin/env python3
"""
inspect_warehouse.py — schema and temporal-column reporter for revenue_warehouse.sqlite.

Run this first to understand the table structures and the timestamp columns that
control when each piece of data becomes available.

Usage:
    python3 /root/.agents/skills/sqlite-query/scripts/inspect_warehouse.py
"""

import sqlite3
from pathlib import Path

DB_PATH = "/root/data/revenue_warehouse.sqlite"

# Suffixes that indicate a column is temporal (date or timestamp)
TEMPORAL_KEYWORDS = ("date", "_at", "month")


def inspect(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]

    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM '{table}'").fetchone()[0]
        print(f"\n{'─' * 58}")
        print(f"  TABLE: {table}  ({count} rows)")
        print(f"{'─' * 58}")

        col_info = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
        for col in col_info:
            cname, ctype = col[1], col[2]
            print(f"    {cname:<38} {ctype}")

        # Print value range for every temporal column so you can see
        # which dates exist and how they relate to prediction dates.
        temporal_cols = [
            c[1]
            for c in col_info
            if any(k in c[1].lower() for k in TEMPORAL_KEYWORDS)
        ]
        if temporal_cols:
            print()
            for dc in temporal_cols:
                try:
                    row = conn.execute(
                        f"SELECT MIN({dc}), MAX({dc}) FROM '{table}' "
                        f"WHERE {dc} IS NOT NULL"
                    ).fetchone()
                    if row and row[0] is not None:
                        print(f"    {dc} range:  {row[0]}  →  {row[1]}")
                except Exception:
                    pass

    conn.close()
    print()


if __name__ == "__main__":
    inspect(DB_PATH)
