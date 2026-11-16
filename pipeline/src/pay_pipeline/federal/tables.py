"""Read federal pay tables into grade × step grids and write the SQL that loads them (D-065).

Sources (declared in ``pipeline/sources/federal-pay-2026.json``, fetched into a Release):

* OPM salary tables, one HTML page per table: ``GS.aspx`` (base General Schedule) and one page per
  locality pay area (``ATL.aspx`` ...). Each page has one table, "Grade | Step 1 .. Step 10"
  (the base table adds a "WGI" column, which is not a salary); a "*" marks a rate limited to
  Executive Schedule level IV and is kept as a cell note.
* VA OCHCO ``Nurse-LPS-<year>.xlsx``: one sheet, one row per grade (and nurse level) of a salary
  plan ("Sal Plan") of a VA station; steps are columns "Step 1" .. "Step 26".

Nothing is inferred: empty cells stay empty, titles and notes are kept as printed.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from itertools import pairwise
from pathlib import Path
from typing import Any

import openpyxl

from pay_pipeline.catalog.d1sql import batched_insert, quote
from pay_pipeline.catalog.slugs import slugify

NURSE_GRADES = {"01": "Nurse I", "02": "Nurse II", "03": "Nurse III", "04": "Nurse IV",
                "05": "Nurse V"}  # fmt: skip


@dataclass
class Cell:
    amount_cents: int | None
    note: str | None = None


@dataclass
class PayTable:
    family: str  # gs, gs_locality, va_nurse
    code: str
    slug: str
    name: str
    title: str
    year: int
    rows: list[str]
    cols: list[str]
    grid: list[list[Cell]]  # grid[row][col]
    area: str | None = None
    state: str | None = None
    group_slug: str | None = None
    effective_date: str | None = None
    notes: str | None = None
    row_header: str = "Grade"
    col_header: str = "Step"
    asset_name: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def cells(self) -> int:
        return sum(c.amount_cents is not None for r in self.grid for c in r)


# ---------------------------------------------------------------- OPM


class _OpmPage(HTMLParser):
    """Collect the paragraphs and the rows of the (single) data table of an OPM salary page."""

    def __init__(self) -> None:
        super().__init__()
        self.texts: list[str] = []
        self.rows: list[list[str]] = []
        self._in_table = 0
        self._cell: list[str] | None = None
        self._row: list[str] | None = None
        self._para: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._in_table += 1
        elif self._in_table and tag == "tr":
            self._row = []
        elif self._in_table and tag in ("td", "th"):
            self._cell = []
        elif not self._in_table and tag in ("p", "h1", "h2", "h3"):
            self._para = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "table":
            self._in_table -= 1
        elif self._in_table and tag in ("td", "th") and self._cell is not None:
            if self._row is not None:
                self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif self._in_table and tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
        elif tag in ("p", "h1", "h2", "h3") and self._para is not None:
            text = " ".join("".join(self._para).split())
            if text:
                self.texts.append(text)
            self._para = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)
        elif self._para is not None:
            self._para.append(data)


_TITLE = re.compile(r"^Salary Table (\d{4})-([A-Z]+)$")
_AREA = re.compile(r"^For the Locality Pay Area of (.+)$")
_MONEY = re.compile(r"^\$?([\d,]+)(?:\.(\d{2}))?\s*(\*?)$")


def _cents(text: str) -> Cell | None:
    m = _MONEY.match(text.strip())
    if not m:
        return None
    dollars = int(m.group(1).replace(",", ""))
    cents = int(m.group(2) or 0)
    return Cell(dollars * 100 + cents, "*" if m.group(3) else None)


def read_opm(html: str, asset_name: str = "") -> PayTable:
    page = _OpmPage()
    page.feed(html)
    title = next((t for t in page.texts if _TITLE.match(t)), "")
    m = _TITLE.match(title)
    if not m:
        raise ValueError(f"{asset_name}: không thấy 'Salary Table <năm>-<mã>'")
    year, code = int(m.group(1)), m.group(2)
    area = next((a.group(1) for t in page.texts if (a := _AREA.match(t))), None)
    header = page.rows[0]
    steps = [h for h in header[1:] if re.match(r"^Step\s*\d+$", h)]
    rows: list[str] = []
    grid: list[list[Cell]] = []
    for r in page.rows[1:]:
        if not r or not re.fullmatch(r"\d{1,2}", r[0]):
            continue
        rows.append(f"GS-{int(r[0])}")
        grid.append([_cents(v) or Cell(None) for v in r[1 : 1 + len(steps)]])
    texts = [t for t in page.texts if t != title]
    notes = [t for t in texts if t.startswith("*")]
    head = [t for t in texts if not t.startswith("*")][:4]
    family = "gs" if code == "GS" else "gs_locality"
    slug = "base" if family == "gs" else (slugify(area or code) or code.lower())
    table = PayTable(
        family=family,
        code=code,
        slug=slug,
        name="General Schedule (base)" if family == "gs" else (area or code),
        title=" — ".join([title, *head]),
        year=year,
        rows=rows,
        cols=[s.replace("Step", "Step ").replace("  ", " ") for s in steps],
        grid=grid,
        area=area,
        notes=" ".join(notes) or None,
        asset_name=asset_name,
    )
    table.problems = check_grid(table, expect_rows=15, expect_cols=10)
    return table


# ---------------------------------------------------------------- VA


_GEO = re.compile(r"\d+\s*-\s*([^,;]+),\s*([A-Z]{2})")
# VA writes Puerto Rico locations as "CE" (station 672, San Juan)
_GEO_STATE = {"CE": "PR"}
US_STATES = frozenset(
    {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "DC",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
    }
)


def _places(geoloc: str) -> list[tuple[str, str]]:
    return [(c.strip().title(), _GEO_STATE.get(s, s)) for c, s in _GEO.findall(geoloc or "")]


def read_va(path: Path, asset_name: str = "") -> list[PayTable]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    head_at = next(i for i, r in enumerate(rows) if r and r[0] == "Station")
    header = [str(h) if h is not None else "" for h in rows[head_at]]
    ix = {h: i for i, h in enumerate(header)}
    step_cols = [(i, h) for i, h in enumerate(header) if re.fullmatch(r"Step \d+", h)]
    plans: dict[tuple[str, str], list[tuple[Any, ...]]] = {}
    for r in rows[head_at + 1 :]:
        if not r or r[0] is None or r[ix["Sal Plan"]] is None:
            continue
        plans.setdefault((str(r[0]).strip(), str(r[ix["Sal Plan"]]).strip()), []).append(r)

    station_places: dict[str, Counter[tuple[str, str]]] = {}
    for (station, _), rs in plans.items():
        c = station_places.setdefault(station, Counter())
        for r in rs:
            c.update(_places(str(r[ix["Geoloc Cd (City,State,County)"]] or "")))

    tables: list[PayTable] = []
    for (station, plan), rs in sorted(plans.items()):
        used = [
            j
            for j, (i, _) in enumerate(step_cols)
            if any(isinstance(r[i], (int, float)) for r in rs)
        ]
        cols = [step_cols[j][1] for j in used]
        labels: list[str] = []
        grid: list[list[Cell]] = []
        for r in rs:
            grade = str(r[ix["Grade"]] or "").strip().zfill(2)
            level = r[ix["Nurse Level"]]
            label = NURSE_GRADES.get(grade, f"Grade {grade}")
            if isinstance(level, (int, float)) and level:
                label += f", Level {int(level)}"
            cells = []
            for j in used:
                v = r[step_cols[j][0]]
                cells.append(
                    Cell(round(float(v) * 100)) if isinstance(v, (int, float)) else Cell(None)
                )
            if label in labels and grid[labels.index(label)] == cells:
                continue  # the same row printed twice (Nurse Step variants with equal pay)
            if label in labels:
                label += f" ({len([x for x in labels if x.startswith(label)]) + 1})"
            labels.append(label)
            grid.append(cells)
        first = rs[0]
        places = _places(str(first[ix["Geoloc Cd (City,State,County)"]] or ""))
        states = Counter(s for _, s in places) or Counter(
            s for (_, s) in station_places[station].elements()
        )
        state = states.most_common(1)[0][0] if states else None
        if state not in US_STATES:
            state = None  # Puerto Rico and territories: no state page (states table is 50 + DC)
        dates: list[dt.datetime] = [
            r[ix["Eff Date"]] for r in rs if isinstance(r[ix["Eff Date"]], dt.datetime)
        ]
        eff = max(dates, default=None)
        main_city = station_places[station].most_common(1)
        station_name = f"VA station {station}" + (
            f" ({main_city[0][0][0]}, {main_city[0][0][1]})" if main_city else ""
        )
        title = str(first[ix["Schedule Title"]] or "").strip()
        area = "; ".join(f"{c}, {s}" for c, s in places) or None
        table = PayTable(
            family="va_nurse",
            code=f"{station}-{plan}",
            slug=slugify(f"station {station} {plan}"),
            group_slug=slugify(f"station {station}"),
            name=station_name,
            title=f"{title} (salary plan {plan})",
            year=eff.year if eff else 0,
            rows=labels,
            cols=cols,
            grid=grid,
            area=area,
            state=state,
            effective_date=eff.date().isoformat() if eff else None,
            row_header="Grade",
            asset_name=asset_name,
        )
        table.problems = check_grid(table)
        tables.append(table)
    return tables


# ---------------------------------------------------------------- checks


def check_grid(table: PayTable, expect_rows: int = 0, expect_cols: int = 0) -> list[str]:
    """Problems that keep a table out of the import (nothing is published on a doubt)."""
    out: list[str] = []
    if expect_rows and len(table.rows) != expect_rows:
        out.append(f"{len(table.rows)} hàng, cần {expect_rows}")
    if expect_cols and len(table.cols) != expect_cols:
        out.append(f"{len(table.cols)} cột, cần {expect_cols}")
    if not table.cells:
        out.append("không có ô nào")
    if table.year < 2000:
        out.append("không có năm")
    for label, row in zip(table.rows, table.grid, strict=True):
        values = [c.amount_cents for c in row if c.amount_cents is not None]
        if any(b < a for a, b in pairwise(values)):
            out.append(f"{label}: lương giảm khi tăng bậc")
        if any(not 1_000_000 <= v <= 100_000_000 for v in values):  # $10,000 .. $1,000,000
            out.append(f"{label}: ô ngoài khoảng $10,000–$1,000,000")
    return out


# ---------------------------------------------------------------- SQL


def load_sources(directory: Path) -> tuple[list[PayTable], dict[str, dict[str, str]]]:
    record = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    files = {f["name"]: f for f in record["files"]}
    tables: list[PayTable] = []
    for name in sorted(files):
        path = directory / name
        if name.startswith("opm_") and name.endswith(".html"):
            tables.append(read_opm(path.read_text(encoding="utf-8", errors="replace"), name))
        elif name.startswith("va_nurse_") and name.endswith(".xlsx"):
            tables += read_va(path, name)
    return tables, files


def pay_tables_sql(
    tables: Iterable[PayTable],
    files: dict[str, dict[str, str]],
    release_tag: str,
) -> list[str]:
    """Replace every (family, year) present in ``tables`` with the new tables."""
    good = [t for t in tables if not t.problems]
    keys = sorted({(t.family, t.year) for t in good})
    statements = [
        "CREATE TABLE IF NOT EXISTS _imp_pay_cells (family TEXT, slug TEXT, year INTEGER,"
        " row_pos INTEGER, row_label TEXT, col_pos INTEGER, col_label TEXT,"
        " amount_cents INTEGER, note TEXT)",
        "DELETE FROM _imp_pay_cells",
    ]
    for family, year in keys:
        statements.append(
            "DELETE FROM pay_cells WHERE table_id IN (SELECT id FROM pay_tables"
            f" WHERE family = {quote(family)} AND year = {year})"
        )
        statements.append(
            f"DELETE FROM pay_tables WHERE family = {quote(family)} AND year = {year}"
        )
    statements += batched_insert(
        "INSERT INTO pay_tables (family, code, slug, group_slug, name, area, state, year,"
        " effective_date, pay_basis, row_header, col_header, title, notes, source_url,"
        " source_sha256, release_tag, asset_name, fetched_at)",
        (
            (
                t.family, t.code, t.slug, t.group_slug, t.name, t.area, t.state, t.year,
                t.effective_date, "annual", t.row_header, t.col_header, t.title, t.notes,
                files[t.asset_name]["url"], files[t.asset_name]["sha256"], release_tag,
                t.asset_name, files[t.asset_name]["fetched_at"],
            )
            for t in good
        ),
    )  # fmt: skip
    statements += batched_insert(
        "INSERT INTO _imp_pay_cells (family, slug, year, row_pos, row_label, col_pos, col_label,"
        " amount_cents, note)",
        (
            (t.family, t.slug, t.year, i + 1, t.rows[i], j + 1, t.cols[j], c.amount_cents, c.note)
            for t in good
            for i, row in enumerate(t.grid)
            for j, c in enumerate(row)
            if c.amount_cents is not None
        ),
    )
    statements.append(
        "INSERT INTO pay_cells (table_id, row_pos, row_label, col_pos, col_label, amount_cents,"
        " note) SELECT t.id, c.row_pos, c.row_label, c.col_pos, c.col_label, c.amount_cents,"
        " c.note FROM _imp_pay_cells c JOIN pay_tables t"
        " ON t.family = c.family AND t.slug = c.slug AND t.year = c.year"
    )
    statements.append("DROP TABLE _imp_pay_cells")
    return statements


def report(tables: list[PayTable], release_tag: str) -> str:
    good = [t for t in tables if not t.problems]
    bad = [t for t in tables if t.problems]
    by = Counter((t.family, t.year) for t in good)
    lines = [
        f"# Nạp bảng lương liên bang ({release_tag})",
        "",
        f"- Bảng đọc được: {len(tables)}; nạp: {len(good)}; giữ lại vì lỗi: {len(bad)}",
        f"- Ô lương: {sum(t.cells for t in good)}",
        "",
        "| Loại | Năm | Số bảng |",
        "|---|---:|---:|",
        *[f"| {f} | {y} | {n} |" for (f, y), n in sorted(by.items())],
    ]
    if bad:
        lines += ["", "## Giữ lại", "", "| Mã | Tệp | Lỗi |", "|---|---|---|"]
        lines += [f"| {t.code} | {t.asset_name} | {'; '.join(t.problems)[:200]} |" for t in bad]
    return "\n".join(lines) + "\n"
