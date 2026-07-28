"""Supplementary aggregates merged after core matrix build."""
import sqlite3

import pandas as pd

from period_utils import ts_open, ts_ws
from warehouse_ops import wq_b, wq_c


def attach(conn: sqlite3.Connection, df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    f12_vals = []
    f13_vals = []

    for _, row in out.iterrows():
        pred_month = str(row["prediction_month"])
        aid = row["account_id"]
        t_open = ts_open(pred_month)
        t_ws = ts_ws(pred_month)
        f12_vals.append(wq_b(conn, aid, t_ws, t_open, inc=False))
        f13_vals.append(wq_c(conn, aid, t_ws, t_open, inc=False))

    out["f12"] = f12_vals
    out["f13"] = f13_vals
    return out
