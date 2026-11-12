"""Kentucky certified salary schedules, from the KDE "Certified Salary Schedule" workbook.

One sheet per fiscal year ("2026 Certified Salary Schedule" = 2025-26). Each district block
starts with a header row ``Fiscal Year | <NNN District> | Rank | Years | | I | II | III`` and has
one row per rank (I-V) and years of experience (0-40). Ranks are the education lanes (KDE: Rank I
master's + 30 hours, II master's, III bachelor's, IV and V below a bachelor's). The columns
I/II/III under "Step" are the rank codes x1/x2/x3 of the KDE salary table: x1 is the base
schedule, x2 and x3 are optional extra schedules whose meaning differs by district, so only x1 is
imported (D-017). A rank whose amounts are all 0.00 is not offered and is left out; a single 0.00
inside an offered rank becomes a blank cell with a note.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import openpyxl

from pay_pipeline.schedules.model import Cell, Lane, ScheduleDraft, Step, dollars_to_cents

STATE = "KY"
SHEET_RE = re.compile(r"^(\d{4}) Certified Salary Schedule$")
FISCAL_RE = re.compile(r"^(\d{4})\s*-\s*(\d{4})$")
DISTRICT_RE = re.compile(r"^(\d{3}) (.+)$")
RANKS = ("V", "IV", "III", "II", "I")  # lowest qualification first
RANK_LANES = {"III": "BA", "II": "MA", "I": "MA+30"}
ZERO_NOTE = "Source shows 0.00 for this rank and years of experience"


@dataclass(frozen=True)
class KySheet:
    name: str
    school_year: str


def list_sheets(path: Path) -> list[KySheet]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        out = []
        for name in wb.sheetnames:
            match = SHEET_RE.match(name)
            if match:
                end = int(match.group(1))
                out.append(KySheet(name, f"{end - 1}-{end % 100:02d}"))
        return sorted(out, key=lambda s: s.school_year)
    finally:
        wb.close()


def _amount(value: object) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(str(value).replace(",", "").strip())


def read_sheet(path: Path, sheet: KySheet) -> list[ScheduleDraft]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[sheet.name]
        # district label -> rank -> years -> amount (column x1)
        grid: dict[str, dict[str, dict[int, float | None]]] = defaultdict(lambda: defaultdict(dict))
        years_seen: dict[str, set[str]] = defaultdict(set)
        for row in ws.iter_rows(values_only=True):
            if len(row) < 6:
                continue
            fiscal, district, rank, years, _, base = row[:6]
            fy = FISCAL_RE.match(str(fiscal or "").strip())
            label = str(district or "").strip()
            if not fy or not DISTRICT_RE.match(label) or str(rank) not in RANKS:
                continue
            if not str(years).strip().isdigit():
                raise ValueError(f"{sheet.name}: số năm kinh nghiệm lạ {years!r} ở {label}")
            years_seen[label].add(f"{fy.group(1)}-{int(fy.group(2)) % 100:02d}")
            grid[label][str(rank)][int(str(years).strip())] = _amount(base)
    finally:
        wb.close()

    out = []
    for label, ranks in grid.items():
        if years_seen[label] != {sheet.school_year}:
            raise ValueError(f"{sheet.name}: năm tài chính {years_seen[label]} ở {label}")
        code, name = label.split(" ", 1)
        all_years = sorted({y for by_year in ranks.values() for y in by_year})
        offered = [r for r in RANKS if any((v or 0) > 0 for v in ranks.get(r, {}).values())]
        cells: dict[tuple[int, int | None], Cell] = {}
        for i, y in enumerate(all_years):
            for j, r in enumerate(offered):
                value = ranks[r].get(y)
                cells[(i, j)] = (
                    Cell(dollars_to_cents(value)) if value and value > 0 else Cell(None, ZERO_NOTE)
                )
        out.append(
            ScheduleDraft(
                state=STATE,
                state_district_id=code,
                district_name=name,
                school_year=sheet.school_year,
                lanes=[Lane(f"Rank {r}", RANK_LANES.get(r)) for r in offered],
                steps=[Step(str(y), y) for y in all_years],
                cells=cells,
                source_sheet=sheet.name,
            )
        )
    return sorted(out, key=lambda s: s.state_district_id)
