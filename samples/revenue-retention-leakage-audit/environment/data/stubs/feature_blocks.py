"""Primary feature assembly (core matrix)."""
import sqlite3

import pandas as pd

from period_utils import (
    months_enrolled,
    pm_next,
    pm_prior,
    ts_he,
    ts_he_month,
    ts_open,
    ts_ws,
)
from warehouse_ops import wq_a, wq_b, wq_c, wq_d, wq_e, wq_f, wq_g


def build_matrix(
    conn: sqlite3.Connection,
    prediction_months: list[str],
    *,
    include_label: bool,
) -> pd.DataFrame:
    accounts = pd.read_sql("SELECT * FROM accounts", conn)
    rows = []

    for pred_month in prediction_months:
        t_open = ts_open(pred_month)
        t_prev = pm_prior(pred_month)
        t_nxt = pm_next(pred_month)
        t_he = ts_he(pred_month)
        t_span = ts_he_month(pred_month)
        t_ws = ts_ws(pred_month)

        for _, acct in accounts.iterrows():
            aid = acct["account_id"]

            row = {
                "account_id": aid,
                "prediction_month": pred_month,
                "f01": wq_a(conn, aid, t_prev),
                "f02": wq_b(conn, aid, t_ws, t_he, inc=True),
                "f08": wq_g(conn, aid, t_open),
                "f03": wq_c(conn, aid, t_ws, t_he, inc=True),
                "f04": wq_d(conn, aid),
                "f07": wq_e(conn, aid, t_nxt),
                "f09": wq_a(conn, aid, pred_month) - wq_a(conn, aid, t_span),
                "f10": wq_a(conn, aid, t_prev) - wq_a(conn, aid, t_span),
                "f06": wq_f(conn, aid, pred_month),
                "f05": wq_f(conn, aid, t_prev),
                "f11": float(months_enrolled(acct["signup_date"], pred_month)),
            }

            if include_label:
                lbl = conn.execute(
                    "SELECT churned_500 FROM labels WHERE account_id=? AND prediction_month=?",
                    (aid, pred_month),
                ).fetchone()
                row["churned_500"] = int(lbl[0]) if lbl else 0

            rows.append(row)

    return pd.DataFrame(rows)
