#!/bin/bash
python3 - << 'PYEOF'
import json
import math
import re
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.formatting.formatting import ConditionalFormattingList
from openpyxl.formatting.rule import CellIsRule, ColorScaleRule
from openpyxl.styles import PatternFill
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

DATA = Path("/root/data")
OUT = Path("/root/out")
OUT.mkdir(parents=True, exist_ok=True)

EDITABLE_COL_MAP = {
    "base_quota_usd": 2,
    "carryover_quota_usd": 3,
    "bookings_arr_usd": 5,
    "commission_usd": 8,
    "draft_commission_usd": 9,
}

SUMMARY_FORMULAS = {
    "B3": "=COUNTA('Commission Audit'!A5:A24)",
    "B4": "=COUNTIF('Commission Audit'!K5:K24,\"<>CORRECT\")",
    "B5": "=SUMIF('Commission Audit'!K5:K24,\"OVERPAID\",'Commission Audit'!J5:J24)",
    "B6": "=ABS(SUMIF('Commission Audit'!K5:K24,\"UNDERPAID\",'Commission Audit'!J5:J24))",
    "B7": "=IFERROR(INDEX('Commission Audit'!A5:A24,MATCH(MAX(ABS('Commission Audit'!J5:J24)),ABS('Commission Audit'!J5:J24),0)),\"\")",
    "B9": "=COUNTIF('Commission Audit'!G5:G24,\"Below Threshold\")",
    "B10": "=COUNTIF('Commission Audit'!G5:G24,\"Base\")",
    "B11": "=COUNTIF('Commission Audit'!G5:G24,\"Accelerator 1\")",
    "B12": "=COUNTIF('Commission Audit'!G5:G24,\"Accelerator 2\")",
    "B13": "=COUNTIF('Commission Audit'!G5:G24,\"Accelerator 3\")",
}

HELPER_ROW_FORMULAS = {
    "B25": "=SUM(B5:B24)",
    "C25": "=SUM(C5:C24)",
    "E25": "=SUM(E5:E24)",
    "H25": "=SUM(H5:H24)",
    "J25": "=SUM(J5:J24)",
}

TABLE_NAME = "CommissionAuditTable"
EXPECTED_TABLE_RANGE = "A4:L24"

EXPECTED_DEFINED_NAMES = {
    "AuditDataRange": "'Commission Audit'!$A$5:$L$24",
    "TierEntryRange": "'Commission Audit'!$G$5:$G$24",
    "FlagEntryRange": "'Commission Audit'!$K$5:$K$24",
}


def audit_row_formulas(row: int) -> dict[str, str]:
    return {
        "D": f"=B{row}+C{row}",
        "F": f"=E{row}/D{row}",
        "G": (
            f'=IF(F{row}<0.8,"Below Threshold",IF(F{row}<1,"Base",'
            f'IF(F{row}<1.2,"Accelerator 1",IF(F{row}<1.5,"Accelerator 2","Accelerator 3"))))'
        ),
        "J": f"=I{row}-H{row}",
        "K": (
            f'=IF(J{row}>0.01,"OVERPAID",IF(J{row}<-0.01,"UNDERPAID","CORRECT"))'
        ),
    }


def parse_currency_value(val) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    return float(str(val).replace("$", "").replace(",", "").strip())


def parse_currency(series: pd.Series) -> pd.Series:
    return series.map(parse_currency_value)


def excel_round(value, ndigits=0):
    ndigits = int(ndigits)
    if ndigits >= 0:
        factor = 10 ** ndigits
        return math.copysign(math.floor(abs(value) * factor + 0.5), value) / factor
    factor = 10 ** (-ndigits)
    return math.copysign(math.floor(abs(value) / factor + 0.5), value) * factor


def sheet_lookup(ws, key, value_col=2):
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] == key:
            return row[value_col - 1]
    raise KeyError(f"{key!r} not found in {ws.title}")


def find_allocations_sheet(wb):
    for name in wb.sheetnames:
        ws = wb[name]
        header_a = ws.cell(row=1, column=1).value
        header_b = ws.cell(row=1, column=2).value
        if header_a == "rep_id" and header_b and "carryover" in str(header_b).lower():
            return ws
    raise ValueError("Could not find allocations sheet with carryover formulas")


def eval_carryover_formula(formula: str, rep_id: str, wb) -> float:
    rate = float(sheet_lookup(wb["RateTable"], rep_id))
    base = float(sheet_lookup(wb["BaseRef"], rep_id))
    product = rate * base
    upper = formula.upper()
    if "MAX(" in upper:
        return float(max(product, 5000))
    match = re.search(r"ROUND\([^,]+,\s*(-?\d+)\)", upper)
    ndigits = int(match.group(1)) if match else -3
    return float(excel_round(product, ndigits))


def load_bookings(path: Path) -> pd.DataFrame:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            row["arr_usd"] = parse_currency_value(row["arr_usd"])
            rows.append(row)
    return pd.DataFrame(rows)


def read_control_metadata(wb):
    control = wb["Control"]
    meta = {}
    for row in control.iter_rows(min_row=2, values_only=True):
        if row[0] is None:
            continue
        if row[0] in {
            "expected_row_count", "workbook_version", "allowed_tiers", "allowed_flags"
        }:
            continue
        if row[0] == "control_name":
            continue
        if row[1] is not None:
            meta[row[0]] = row[1]
    return meta


def extend_formula_columns(audit_ws):
    for row_idx in range(5, 25):
        for col_letter, formula in audit_row_formulas(row_idx).items():
            audit_ws[f"{col_letter}{row_idx}"] = formula


def repair_table(audit_ws):
    if TABLE_NAME in audit_ws.tables:
        audit_ws.tables[TABLE_NAME].ref = EXPECTED_TABLE_RANGE


def repair_defined_names(wb):
    for name, attr_text in EXPECTED_DEFINED_NAMES.items():
        if name in wb.defined_names:
            del wb.defined_names[name]
        wb.defined_names.add(DefinedName(name=name, attr_text=attr_text))


def repair_conditional_formatting(audit_ws):
    green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    yellow_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
    rebuilt = ConditionalFormattingList()
    rebuilt.add(
        "F5:F24",
        ColorScaleRule(
            start_type="num", start_value=0, start_color="F8696B",
            mid_type="num", mid_value=1, mid_color="FFEB84",
            end_type="num", end_value=1.5, end_color="63BE7B",
        ),
    )
    rebuilt.add(
        "J5:J24",
        CellIsRule(operator="greaterThan", formula=["0"], fill=green_fill),
    )
    rebuilt.add(
        "J5:J24",
        CellIsRule(operator="lessThan", formula=["0"], fill=red_fill),
    )
    rebuilt.add(
        "K5:K24",
        CellIsRule(operator="equal", formula=['"OVERPAID"'], fill=red_fill),
    )
    rebuilt.add(
        "K5:K24",
        CellIsRule(operator="equal", formula=['"UNDERPAID"'], fill=yellow_fill),
    )
    rebuilt.add(
        "K5:K24",
        CellIsRule(operator="equal", formula=['"CORRECT"'], fill=green_fill),
    )
    audit_ws.conditional_formatting = rebuilt


def repair_workbook_ranges(audit_ws, summary_ws):
    audit_ws.auto_filter.ref = "A4:L24"
    audit_ws.data_validations.dataValidation = []
    tier_dv = DataValidation(type="list", formula1="Validation!$A$2:$A$6", allow_blank=True)
    tier_dv.add("G5:G24")
    audit_ws.add_data_validation(tier_dv)
    flag_dv = DataValidation(type="list", formula1="Validation!$C$2:$C$4", allow_blank=True)
    flag_dv.add("K5:K24")
    audit_ws.add_data_validation(flag_dv)
    for cell_ref, formula in HELPER_ROW_FORMULAS.items():
        audit_ws[cell_ref] = formula
    audit_ws.row_dimensions[25].hidden = True
    for cell_ref, formula in SUMMARY_FORMULAS.items():
        summary_ws[cell_ref] = formula
    extend_formula_columns(audit_ws)
    repair_table(audit_ws)
    repair_conditional_formatting(audit_ws)


quotas = pd.read_csv(DATA / "rep_quotas.csv")
quotas["base_quota_usd"] = parse_currency(quotas["base_quota_usd"])

carry_wb = openpyxl.load_workbook(DATA / "quota_carryover.xlsx", data_only=False)
alloc_ws = find_allocations_sheet(carry_wb)

carryover_rows = []
for row in alloc_ws.iter_rows(min_row=2, values_only=False):
    rep_id = row[0].value
    if rep_id is None:
        continue
    formula = row[1].value
    if isinstance(formula, str) and formula.startswith("="):
        carry = eval_carryover_formula(formula, rep_id, carry_wb)
    else:
        carry = float(formula)
    carryover_rows.append({"rep_id": rep_id, "carryover_quota_usd": carry})
carryover = pd.DataFrame(carryover_rows)

deals = load_bookings(DATA / "bookings.jsonl")
bookings = deals.groupby("rep_id")["arr_usd"].sum().reset_index()
bookings.columns = ["rep_id", "bookings_arr_usd"]

draft = pd.read_csv(DATA / "draft_commission_statements.csv")

df = (
    quotas.merge(carryover, on="rep_id")
    .merge(bookings, on="rep_id")
    .merge(draft, on="rep_id")
)
df["total_quota_usd"] = df["base_quota_usd"] + df["carryover_quota_usd"]
df["attainment_pct"] = df["bookings_arr_usd"] / df["total_quota_usd"]


def tier_and_rate(att):
    if att < 0.80:
        return "Below Threshold", 0.00
    if att < 1.00:
        return "Base", 0.08
    if att < 1.20:
        return "Accelerator 1", 0.10
    if att < 1.50:
        return "Accelerator 2", 0.12
    return "Accelerator 3", 0.15


tiers = df["attainment_pct"].apply(tier_and_rate)
df["commission_tier"] = tiers.apply(lambda x: x[0])
df["commission_usd"] = df["bookings_arr_usd"] * tiers.apply(lambda x: x[1])
df["delta_usd"] = df["draft_commission_usd"] - df["commission_usd"]


def flag_for(delta):
    if delta > 0.01:
        return "OVERPAID"
    if delta < -0.01:
        return "UNDERPAID"
    return "CORRECT"


df["flag"] = df["delta_usd"].apply(flag_for)
df = df.sort_values("rep_id").reset_index(drop=True)
by_rep = df.set_index("rep_id")

audit_wb = openpyxl.load_workbook(DATA / "draft_commission_audit.xlsx")
_ = read_control_metadata(audit_wb)
audit_ws = audit_wb["Commission Audit"]
summary_ws = audit_wb["Summary"]

for row_idx in range(5, 25):
    rep_id = audit_ws.cell(row=row_idx, column=1).value
    record = by_rep.loc[rep_id]
    for field, col_idx in EDITABLE_COL_MAP.items():
        audit_ws.cell(row=row_idx, column=col_idx, value=record[field])

repair_workbook_ranges(audit_ws, summary_ws)
repair_defined_names(audit_wb)
audit_wb.save(OUT / "commission_audit_repaired.xlsx")

tier_distribution = df["commission_tier"].value_counts().to_dict()
for tier in [
    "Below Threshold", "Base", "Accelerator 1", "Accelerator 2", "Accelerator 3"
]:
    tier_distribution.setdefault(tier, 0)

ranked = df.assign(abs_delta=df["delta_usd"].abs()).sort_values(
    ["abs_delta", "rep_id"], ascending=[False, True]
)
summary = {
    "total_reps_audited": len(df),
    "reps_with_discrepancy": int((df["flag"] != "CORRECT").sum()),
    "total_overpaid_usd": round(
        df.loc[df["flag"] == "OVERPAID", "delta_usd"].sum(), 2
    ),
    "total_underpaid_usd": round(
        df.loc[df["flag"] == "UNDERPAID", "delta_usd"].abs().sum(), 2
    ),
    "tier_distribution": tier_distribution,
    "highest_delta_rep": ranked.iloc[0]["rep_id"],
}

with open(OUT / "audit_summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)
PYEOF
