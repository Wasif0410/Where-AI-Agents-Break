"""Warehouse read primitives — inspect SQL to determine semantics."""
from collections import Counter


def wq_a(conn, account_id: str, period_month: str) -> float:
    row = conn.execute(
        "SELECT mrr_usd FROM subscription_snapshots WHERE account_id=? AND snapshot_month=?",
        (account_id, period_month),
    ).fetchone()
    return float(row[0]) if row else 0.0


def wq_b(conn, account_id: str, t0: str, t1: str, *, inc: bool) -> int:
    if inc:
        sql = (
            "SELECT COALESCE(SUM(event_count), 0) FROM product_events "
            "WHERE account_id=? AND event_date >= ? AND event_date <= ?"
        )
    else:
        sql = (
            "SELECT COALESCE(SUM(event_count), 0) FROM product_events "
            "WHERE account_id=? AND event_date >= ? AND event_date < ?"
        )
    return int(conn.execute(sql, (account_id, t0, t1)).fetchone()[0])


def wq_c(conn, account_id: str, t0: str, t1: str, *, inc: bool) -> int:
    if inc:
        sql = (
            "SELECT COUNT(*) FROM support_tickets "
            "WHERE account_id=? AND ticket_created_at >= ? AND ticket_created_at <= ?"
        )
    else:
        sql = (
            "SELECT COUNT(*) FROM support_tickets "
            "WHERE account_id=? AND ticket_created_at >= ? AND ticket_created_at < ?"
        )
    return int(conn.execute(sql, (account_id, t0, t1)).fetchone()[0])


def wq_d(conn, account_id: str) -> str:
    rows = conn.execute(
        "SELECT resolution_code FROM support_tickets "
        "WHERE account_id=? AND ticket_closed_at IS NOT NULL",
        (account_id,),
    ).fetchall()
    codes = [r[0] for r in rows if r[0]]
    return Counter(codes).most_common(1)[0][0] if codes else "NONE"


def wq_e(conn, account_id: str, period_month: str) -> float:
    row = conn.execute(
        "SELECT amount_usd FROM invoices WHERE account_id=? AND invoice_month=?",
        (account_id, period_month),
    ).fetchone()
    return float(row[0]) if row else 0.0


def wq_f(conn, account_id: str, period_month: str) -> int:
    row = conn.execute(
        "SELECT paid_status FROM invoices WHERE account_id=? AND invoice_month=?",
        (account_id, period_month),
    ).fetchone()
    status = row[0] if row else "unknown"
    return 1 if status == "paid" else 0


def wq_g(conn, account_id: str, cutoff_date: str) -> float:
    row = conn.execute(
        "SELECT health_score FROM customer_health_scores "
        "WHERE account_id=? AND score_date <= ? ORDER BY score_date DESC LIMIT 1",
        (account_id, cutoff_date),
    ).fetchone()
    return float(row[0]) if row else 70.0
