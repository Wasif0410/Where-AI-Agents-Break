"""Period boundary helpers."""
from datetime import date, timedelta
import calendar


def pm_prior(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def pm_next(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:])
    return f"{y + 1}-01" if m == 12 else f"{y}-{m + 1:02d}"


def ts_open(ym: str) -> str:
    return f"{ym}-01"


def ts_he(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:])
    return (date(y, m, 1) + timedelta(days=30)).strftime("%Y-%m-%d")


def ts_he_month(ym: str) -> str:
    return ts_he(ym)[:7]


def ts_ws(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:])
    return (date(y, m, 1) - timedelta(days=30)).strftime("%Y-%m-%d")


def ts_prior_last(ym: str) -> str:
    prev_m = pm_prior(ym)
    y, m = int(prev_m[:4]), int(prev_m[5:])
    last = calendar.monthrange(y, m)[1]
    return f"{prev_m}-{last:02d}"


def months_enrolled(signup_date: str, ym: str) -> int:
    sd = date.fromisoformat(signup_date)
    pd_ = date(int(ym[:4]), int(ym[5:]), 1)
    return max(0, (pd_.year - sd.year) * 12 + (pd_.month - sd.month))
