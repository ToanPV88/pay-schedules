"""California Form J-90 (Certificated Salaries & Benefits), published by the CDE each year.

Reading and mapping are separate (PLAN Công đoạn 4): from 2025-26 the state moves to the C-90
system, so only :func:`read_j90` should need replacing when the file format changes.

The CDE file ``j90YYZZ.exe`` is a self-extracting ZIP. It is opened with :mod:`zipfile`, never
run; the Access database inside is read with ``mdb-export`` (mdbtools). Tables, from the readme:

* ``TSAL1ZZ``: one row per district: name, type, service days, effective date, bonuses;
* ``TSAL2ZZ``: column headings of the salary schedule;
* ``TSAL3ZZ``: one salary per column and step (``TS3_Col``, ``TS3_Step``, ``TS3_Salary``).

Not read on purpose (PLAN nguyên tắc 3, D-017): the superintendent salary (``TS1_Supt``),
average principal salaries, FTE counts per cell, and the benefit tables TSAL4-6.
"""

from __future__ import annotations

import csv
import io
import re
import shutil
import subprocess
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pay_pipeline.schedules.model import (
    Cell,
    Lane,
    ScheduleDraft,
    Step,
    Stipend,
    dollars_to_cents,
    normalize_lane,
    school_year_from_start,
)

STATE = "CA"
TABLE_RE = re.compile(r"^tsal([1-3])(\d{2})$", re.IGNORECASE)
MISSING_CELL_NOTE = "Not in J-90: no salary reported for this column and step"
MIN_STIPEND_DOLLARS = 100
UNCLEAR_UNIT = "Figure as reported on the J-90; the unit is not stated"

# (amount field, description field or None, stipend name). Annual amounts paid over the schedule.
STIPEND_FIELDS: tuple[tuple[str, str | None, str], ...] = (
    ("TS1_MBONAM", None, "Master's degree"),
    ("TS1_DBONAM", None, "Doctorate"),
    ("TS1_SEBONA", None, "Special education assignment"),
    ("TS1_BBONAM", None, "Bilingual assignment"),
    ("TS1_CBONAM", None, "CLAD certificate"),
    ("TS1_BCBONA", None, "BCLAD certificate"),
    ("TS1_NBONAM", None, "National Board certification"),
    ("TS1_O1BONA", "TS1_O1DESC", "Other"),
    ("TS1_O2BONA", "TS1_O2DESC", "Other"),
    ("TS1_O3BONA", "TS1_O3DESC", "Other"),
    ("TS1_O4BONA", "TS1_O4DESC", "Other"),
)

Runner = Callable[[Sequence[str]], str]


@dataclass(frozen=True)
class J90District:
    cds: str
    name: str
    county: str
    lea_type: str
    service_days: int | None
    effective_date: str
    stipends: tuple[Stipend, ...]


@dataclass
class J90Data:
    school_year: str
    tables: dict[int, str]
    """1, 2, 3 -> actual table name in the database (e.g. 3 -> 'tsal325')."""
    districts: dict[str, J90District] = field(default_factory=dict)
    headings: dict[str, dict[int, str]] = field(default_factory=dict)
    salaries: dict[str, dict[tuple[int, int], float]] = field(default_factory=dict)
    """CDS -> (step, column) -> annual salary in dollars."""


def extract_accdb(archive: Path, dest: Path) -> Path:
    """Copy the single ``.accdb`` out of the self-extracting ZIP without running it."""
    with zipfile.ZipFile(archive) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".accdb")]
        if len(names) != 1:
            raise ValueError(f"{archive.name}: cần đúng một tệp .accdb, thấy {names}")
        member = names[0]
        base = Path(member).name
        if not base or base.startswith(".") or base != member.rsplit("/", 1)[-1]:
            raise ValueError(f"{archive.name}: tên tệp lạ {member!r}")
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / base
        with zf.open(member) as src, target.open("wb") as out:
            shutil.copyfileobj(src, out)
    return target


def mdb_runner(args: Sequence[str]) -> str:
    result = subprocess.run(list(args), capture_output=True, check=True)  # noqa: S603
    return result.stdout.decode("utf-8", errors="replace")


def _rows(runner: Runner, accdb: Path, table: str) -> list[dict[str, str]]:
    text = runner(["mdb-export", str(accdb), table])
    reader = csv.DictReader(io.StringIO(text))
    return [{k.upper(): (v or "").strip() for k, v in row.items() if k} for row in reader]


def _number(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def _require(rows: list[dict[str, str]], columns: tuple[str, ...], table: str) -> None:
    if rows:
        missing = [c for c in columns if c not in rows[0]]
        if missing:
            raise ValueError(f"Bảng {table} thiếu cột {missing}; có {sorted(rows[0])}")


def read_j90(accdb: Path, runner: Runner = mdb_runner) -> J90Data:
    tables: dict[int, str] = {}
    years: set[int] = set()
    for name in runner(["mdb-tables", "-1", str(accdb)]).split():
        match = TABLE_RE.match(name)
        if match:
            tables[int(match.group(1))] = name
            years.add(int(match.group(2)))
    if sorted(tables) != [1, 2, 3] or len(years) != 1:
        raise ValueError(f"{accdb.name}: không thấy đủ bảng TSAL1/2/3 cùng một năm: {tables}")
    end = 2000 + years.pop()
    data = J90Data(school_year=school_year_from_start(end - 1), tables=tables)

    t1 = _rows(runner, accdb, tables[1])
    _require(t1, ("CDS", "TS1_DNAME", "TS1_TYPE", "TS1_RDAYS", "TS1_EFFDAT"), tables[1])
    for r in t1:
        stipends = []
        for amount_field, desc_field, label in STIPEND_FIELDS:
            amount = _number(r.get(amount_field, ""))
            if not amount or amount <= 0:
                continue
            desc = r.get(desc_field, "") if desc_field else ""
            if amount < MIN_STIPEND_DOLLARS:
                # e.g. 14 for "SLP yr 1-5": not a dollar amount; keep the figure, not a guess.
                stipends.append(Stipend(desc or label, None, f"{amount:g}", UNCLEAR_UNIT))
            else:
                stipends.append(Stipend(desc or label, dollars_to_cents(amount)))
        days = _number(r["TS1_RDAYS"])
        data.districts[r["CDS"]] = J90District(
            cds=r["CDS"],
            name=r["TS1_DNAME"],
            county=r.get("TS1_COUNTY", ""),
            lea_type=r["TS1_TYPE"],
            service_days=int(days) if days and 1 <= days <= 366 else None,
            effective_date=r["TS1_EFFDAT"],
            stipends=tuple(stipends),
        )

    t2 = _rows(runner, accdb, tables[2])
    _require(t2, ("CDS", "TS2_COL", "TS2_COL1"), tables[2])
    for r in t2:
        col = _number(r["TS2_COL"])
        if col is None:
            continue
        parts = (
            r.get(k, "") for k in ("TS2_COL1", "TS2_COL1A", "TS2_COL2", "TS2_COL3", "TS2_COL3A")
        )
        label = " ".join(" ".join(p.split()) for p in parts if p.strip())
        data.headings.setdefault(r["CDS"], {})[int(col)] = label

    t3 = _rows(runner, accdb, tables[3])
    _require(t3, ("CDS", "TS3_COL", "TS3_STEP", "TS3_SALARY"), tables[3])
    for r in t3:
        col, step, salary = (_number(r[k]) for k in ("TS3_COL", "TS3_STEP", "TS3_SALARY"))
        if col is None or step is None or salary is None:
            continue
        data.salaries.setdefault(r["CDS"], {})[(int(step), int(col))] = salary
    return data


def j90_schedules(data: J90Data) -> list[ScheduleDraft]:
    """One teacher schedule per district that reported salaries."""
    out = []
    for cds, district in sorted(data.districts.items()):
        salaries = data.salaries.get(cds)
        if not salaries:
            continue
        steps = sorted({s for s, _ in salaries})
        cols = sorted({c for _, c in salaries})
        headings = data.headings.get(cds, {})
        lanes = []
        for c in cols:
            label = headings.get(c) or f"Column {c}"
            lanes.append(Lane(label, normalize_lane(label)))
        cells: dict[tuple[int, int | None], Cell] = {}
        for i, step in enumerate(steps):
            for j, col in enumerate(cols):
                salary = salaries.get((step, col))
                if salary is None or salary <= 0:
                    cells[(i, j)] = Cell(None, MISSING_CELL_NOTE)
                else:
                    cells[(i, j)] = Cell(dollars_to_cents(salary))
        notes = (
            f"Effective date (J-90): {district.effective_date}" if district.effective_date else None
        )
        out.append(
            ScheduleDraft(
                state=STATE,
                state_district_id=cds,
                district_name=district.name,
                school_year=data.school_year,
                lanes=lanes,
                steps=[Step(str(s)) for s in steps],
                cells=cells,
                contract_days=district.service_days,
                notes=notes,
                source_sheet=data.tables[3].upper(),
                stipends=list(district.stipends),
            )
        )
    return out
