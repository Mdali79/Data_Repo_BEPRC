"""
Parser for Power Grid Bangladesh PLC / NLDC "Daily Report" workbooks.

Design note: this module is deliberately Django-free. It takes an openpyxl
worksheet (or workbook) and a report_date, and returns plain lists of dicts
in canonical field names. The Django management command
(`import_nldc_report.py`) is a thin wrapper that takes this output and
writes it into the ORM models. Keeping parsing logic separate from the ORM
means you can unit-test it (as this file's __main__ block does) without a
database, and reuse it from a Celery task, a script, or a notebook.

Covers: Forecast, GenLog, P1 (system summary), P4 (hourly), Voltage,
En-Curve. P2, P3, L-Curve and EWIC follow the same patterns (see README)
and are intentionally left as the next extension, not because they're
harder — this subset already demonstrates every parsing pattern in the
workbook (single daily record, per-plant table, wide hourly matrix,
paired side-by-side table, 30-min curve).
"""

from __future__ import annotations
import re
from datetime import date, datetime, time as dtime
from typing import Any

import openpyxl


def load_workbook(path: str):
    return openpyxl.load_workbook(path, data_only=True)


def report_date_from_filename(path: str) -> date:
    """Daily_Report_10-09-2026.xlsx -> date(2026, 9, 10)."""
    m = re.search(r"(\d{2})-(\d{2})-(\d{4})", path)
    if not m:
        raise ValueError(f"Could not find a DD-MM-YYYY date in filename: {path}")
    d, mo, y = m.groups()
    return date(int(y), int(mo), int(d))


def _num(v: Any) -> float | None:
    if v is None or v == "" or v == "-":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _time(v: Any) -> str | None:
    """Normalize either a datetime.time or a 'HH:MM' string to 'HH:MM'."""
    if v is None:
        return None
    if isinstance(v, dtime):
        return v.strftime("%H:%M")
    if isinstance(v, str):
        m = re.match(r"^\s*(\d{1,2}):(\d{2})", v)
        if m:
            return f"{int(m.group(1)):02d}:{m.group(2)}"
    return None


# ---------------------------------------------------------------------------
# Forecast sheet -> generating_units (dimension) + unit_generation (facts)
# ---------------------------------------------------------------------------

def parse_forecast(ws, report_date: date) -> list[dict]:
    """
    Header spans rows 7-10 (merged cells for capacity/generation groups).
    Data starts row 11. Columns (0-indexed after trimming col A which is
    just an index the workbook itself often leaves blank for sub-rows):
      B: Sl.  C: Name of Power Station  D: Fuel  E: Producer
      F: Unit No. x Capacity (text)  G: Installed Capacity (MW)
      H: Present Capacity (MW)
      I: Actual Gen Day Peak (prev day)  J: Actual Gen Evening Peak (prev day)
      K: Forecast Gen Day Peak  L: Forecast Gen Evening Peak
      M: Effective Available Gen Day Peak  N: Effective Available Gen Evening Peak
      O: Remarks
    """
    rows = []
    for row in ws.iter_rows(min_row=11, max_col=14, values_only=True):
        sl, name, fuel, producer, unit_cap, installed_cap, present_cap, \
            act_day, act_eve, fcst_day, fcst_eve, eff_day, eff_eve, remarks = (
                list(row) + [None] * (14 - len(row))
            )[:14]
        if not name:
            continue
        rows.append({
            "report_date": report_date,
            "unit_name": str(name).strip(),
            "fuel_type": fuel,
            "producer_type": producer,
            "unit_capacity_spec": unit_cap,
            "installed_capacity_mw": _num(installed_cap),
            "present_capacity_mw": _num(present_cap),
            "actual_gen_day_peak_mw": _num(act_day),
            "actual_gen_evening_peak_mw": _num(act_eve),
            "forecast_gen_day_peak_mw": _num(fcst_day),
            "forecast_gen_evening_peak_mw": _num(fcst_eve),
            "effective_gen_day_peak_mw": _num(eff_day),
            "effective_gen_evening_peak_mw": _num(eff_eve),
            "remarks": remarks,
        })
    return rows


# ---------------------------------------------------------------------------
# GenLog sheet -> unit_generation (hourly, wide matrix -> long)
# ---------------------------------------------------------------------------

def parse_genlog(ws, report_date: date) -> list[dict]:
    """
    Row 11: header - col A 'Hour', then one column per plant name.
    Row 12: each plant's present capacity, e.g. '260.000 MW'.
    Rows 13+: one row per hour, col A = datetime.time or 'HH:MM', then
    one generation (MW) value per plant column.
    """
    header_row = next(ws.iter_rows(min_row=11, max_row=11, values_only=True))
    cap_row = next(ws.iter_rows(min_row=12, max_row=12, values_only=True))
    plant_names = header_row[1:]
    plant_caps = cap_row[1:]

    readings = []
    for row in ws.iter_rows(min_row=13, values_only=True):
        hour_cell = row[0]
        hour = _time(hour_cell)
        if hour is None:
            continue
        for name, cap, val in zip(plant_names, plant_caps, row[1:]):
            if not name:
                continue
            readings.append({
                "report_date": report_date,
                "unit_name": str(name).strip(),
                "present_capacity_mw": _num(str(cap).replace("MW", "")) if cap else None,
                "hour": hour,
                "generation_mw": _num(val),
            })
    return readings


# ---------------------------------------------------------------------------
# P1 sheet -> system_summary (one record) + zone-wise generation breakdown
# ---------------------------------------------------------------------------

def parse_p1_summary(ws, report_date: date) -> dict:
    def cell(r, c):
        return ws.cell(row=r, column=c).value

    return {
        "report_date": report_date,
        "day_peak_generation_mw": _num(cell(8, 5)),
        "day_peak_generation_time": _time(cell(8, 7)),
        "day_peak_demand_mw": _num(cell(9, 5)),
        "day_peak_demand_time": _time(cell(9, 7)),
        "evening_peak_generation_mw": _num(cell(10, 5)),
        "evening_peak_generation_time": _time(cell(10, 7)),
        "evening_peak_demand_mw": _num(cell(11, 5)),
        "evening_peak_demand_time": _time(cell(11, 7)),
        "min_generation_mw": _num(cell(12, 5)),
        "min_generation_time": _time(cell(12, 7)),
        "max_generation_mw": _num(cell(13, 5)),
        "max_generation_time": _time(cell(13, 7)),
        "energy_generated_mkwh": _num(cell(8, 11)),
        "energy_unserved_mkwh": _num(cell(9, 11)),
        "energy_demand_mkwh": _num(cell(10, 11)),
        "max_temperature_c": _num(cell(11, 11)),
        "total_gas_supplied_mmcfd": _num(cell(12, 11)),
        "production_cost_per_kwh_tk": _num(cell(13, 11)),
    }


def parse_p1_zone_generation(ws, report_date: date) -> list[dict]:
    """
    Row 16: fuel headers starting col E (Gas, Coal, HFO, HSD, Hydro, Solar,
    Import, Wind, Total). Rows 17-26: one per zone incl. 'Total'.
    """
    fuels = [c.value for c in ws[16][4:13]]
    rows = []
    for r in range(17, 27):
        zone = ws.cell(row=r, column=2).value
        if not zone:
            continue
        for i, fuel in enumerate(fuels):
            val = ws.cell(row=r, column=5 + i).value
            rows.append({
                "report_date": report_date,
                "zone": str(zone).strip(),
                "fuel": fuel,
                "energy_mkwh": _num(val),
            })
    return rows


# ---------------------------------------------------------------------------
# P4 sheet -> system_hourly
# ---------------------------------------------------------------------------

def parse_p4(ws, report_date: date) -> list[dict]:
    rows = []
    for row in ws.iter_rows(min_row=9, max_col=8, values_only=True):
        _, hour, generation, _, load_shed, _, demand, *_ = list(row) + [None] * (8 - len(row))
        t = _time(hour)
        if t is None:
            continue
        rows.append({
            "report_date": report_date,
            "hour": t,
            "generation_mw": _num(generation),
            "load_shed_mw": _num(load_shed),
            "demand_mw": _num(demand),
        })
    return rows


# ---------------------------------------------------------------------------
# Voltage sheet -> voltage_readings (two side-by-side blocks per row)
# ---------------------------------------------------------------------------

def parse_voltage(ws, report_date: date) -> list[dict]:
    """
    Row 6: 'Substation | Max Voltage | Time | Min Voltage | Time' repeated
    twice (cols A-E, then F-J). Row 7 holds the voltage level ('400 kV').
    Data from row 8 down, both blocks populated per row until a block runs
    out (blocks are not always the same length).
    """
    rows = []
    for block_start in (1, 6):  # column A=1, column F=6
        level = ws.cell(row=7, column=block_start).value
        for r in range(8, ws.max_row + 1):
            name = ws.cell(row=r, column=block_start).value
            if not name:
                continue
            rows.append({
                "report_date": report_date,
                "substation_name": str(name).strip(),
                "voltage_level": level,
                "max_voltage_kv": _num(ws.cell(row=r, column=block_start + 1).value),
                "max_voltage_time": _time(ws.cell(row=r, column=block_start + 2).value),
                "min_voltage_kv": _num(ws.cell(row=r, column=block_start + 3).value),
                "min_voltage_time": _time(ws.cell(row=r, column=block_start + 4).value),
            })
    return rows


# ---------------------------------------------------------------------------
# En-Curve sheet -> fuel_source_reading (30-min, wide -> long)
# ---------------------------------------------------------------------------

DOMESTIC_FUELS = {
    "Gas-Public", "Gas-Pvt", "Hydro", "Coal", "Solar",
    "HFO-Public", "HFO-Pvt", "HSD-Public", "HSD-Pvt", "Wind",
}
IMPORTED_SOURCES = {"HVDC", "Nepal", "Tripura", "Adani"}


def parse_en_curve(ws, report_date: date) -> list[dict]:
    header = [c.value for c in ws[3][1:16]]  # B..P: 15 source columns
    rows = []
    for row in ws.iter_rows(min_row=4, max_col=16, values_only=True):
        t = row[0]
        if not isinstance(t, str) or ":" not in str(t):
            continue
        for source, val in zip(header, row[1:16]):
            if not source:
                continue
            category = (
                "shortage" if source == "Shortage"
                else "imported_power" if source in IMPORTED_SOURCES
                else "domestic_generation"
            )
            rows.append({
                "report_date": report_date,
                "time": t,
                "source": source,
                "category": category,
                "value_mw": _num(val),
            })
    return rows


# ---------------------------------------------------------------------------
# Whole-report convenience wrapper
# ---------------------------------------------------------------------------

def parse_report(path: str, source_name: str | None = None) -> dict[str, list[dict] | dict]:
    """
    path: file to read from disk.
    source_name: the file's ORIGINAL name (e.g. "Daily Report 11-09-2026.xlsx").
    Pass this whenever `path` is a temp file, e.g. from the web upload view —
    the report date is read from the original name, not the temp path.
    """
    d = report_date_from_filename(source_name or path)
    wb = load_workbook(path)
    return {
        "report_date": d,
        "forecast": parse_forecast(wb["Forecast"], d),
        "genlog": parse_genlog(wb["GenLog"], d),
        "system_summary": parse_p1_summary(wb["P1"], d),
        "zone_generation": parse_p1_zone_generation(wb["P1"], d),
        "system_hourly": parse_p4(wb["P4"], d),
        "voltage": parse_voltage(wb["Voltage"], d),
        "fuel_source": parse_en_curve(wb["En-Curve"], d),
    }


if __name__ == "__main__":
    import sys
    import json

    path = sys.argv[1]
    result = parse_report(path)
    for key, val in result.items():
        if isinstance(val, list):
            print(f"{key}: {len(val)} rows — sample: {val[0] if val else None}")
        else:
            print(f"{key}: {val}")
