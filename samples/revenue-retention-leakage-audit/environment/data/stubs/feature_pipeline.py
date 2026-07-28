"""Feature matrix entrypoint."""
import sqlite3

import pandas as pd

from alt_aggregates import attach
from feature_blocks import build_matrix


def _build(conn: sqlite3.Connection, months: list[str], *, include_label: bool) -> pd.DataFrame:
    df = build_matrix(conn, months, include_label=include_label)
    return attach(conn, df)


def build_features(config: dict) -> pd.DataFrame:
    db_path = config["database"]
    holdout_month = config.get("holdout_month", "2026-04")
    all_months = config.get("feature_pipeline", {}).get("prediction_months", [])
    train_months = [m for m in all_months if m != holdout_month]

    conn = sqlite3.connect(db_path)
    df = _build(conn, train_months, include_label=True)
    conn.close()
    return df


def build_holdout_features(config: dict) -> pd.DataFrame:
    db_path = config["database"]
    holdout_month = config.get("holdout_month", "2026-04")

    conn = sqlite3.connect(db_path)
    df = _build(conn, [holdout_month], include_label=False)
    conn.close()
    return df
