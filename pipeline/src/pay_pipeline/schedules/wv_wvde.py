"""West Virginia Department of Education: the teacher salary schedule of every county board of
education (D-071).

Each county (one school district per county) prints one page per training class (4th class to
doctorate). A page lists years of experience 0-35 and, for each, the state basic salary, the state
and county supplements and the total salary; the total (last column) is what a teacher is paid.
The state minimum schedules and the county averages at the end of the book are not read.
"""

from __future__ import annotations

import re
from pathlib import Path

from pay_pipeline.schedules import ok_sde
from pay_pipeline.schedules.model import (
    Cell,
    Lane,
    ScheduleDraft,
    Step,
    dollars_to_cents,
)

STATE = "WV"
NOTES = (
    "Total salary: the state basic salary plus the state and county supplements, as listed by the"
    " West Virginia Department of Education. Steps are years of experience."
)

_COUNTY = re.compile(r"^\s*([A-Z][A-Z .']+?)\s+COUNTY\s+BOARD\s+OF\s+EDUCATION", re.M)
_YEAR = re.compile(r"FOR\s+THE\s+(\d{4})-(\d{2})\s+YEAR")
_CLASS = re.compile(
    r"^\s*(4TH CLASS|3RD CLASS|2ND CLASS|A\.B\.(?:\+15)?|M\.A\.(?:\+\d{2})?|DOCTORATE)\s*$", re.M
)
_ROW = re.compile(r"^\s*(\d{1,2})\s+\d.*?(\d{1,3},\d{3})\s*$")
LANE_NAMES = {
    "4TH CLASS": ("4th Class", None),
    "3RD CLASS": ("3rd Class", None),
    "2ND CLASS": ("2nd Class", None),
    "A.B.": ("A.B. (Bachelor's)", "BA"),
    "A.B.+15": ("A.B.+15", "BA+15"),
    "M.A.": ("M.A. (Master's)", "MA"),
    "M.A.+15": ("M.A.+15", "MA+15"),
    "M.A.+30": ("M.A.+30", "MA+30"),
    "M.A.+45": ("M.A.+45", "MA+45"),
    "DOCTORATE": ("Doctorate", "PhD"),
}


def district_key(name: str) -> str:
    """'BARBOUR' / 'Barbour County Schools' -> 'BARBOUR'."""
    n = re.sub(r"\s+", " ", name.upper()).strip()
    return re.sub(r"\s+COUNTY(?:\s+(?:SCHOOLS|SCHOOL DISTRICT|BOARD OF EDUCATION))?$", "", n)


def read_pages(pages: list[str]) -> list[ScheduleDraft]:
    counties: dict[tuple[str, str], list[tuple[str, int, list[tuple[int, int]]]]] = {}
    for number, page in enumerate(pages, 1):
        county, year, cls = _COUNTY.search(page), _YEAR.search(page), _CLASS.search(page)
        if not (county and year and cls):
            continue
        if int(year.group(2)) != (int(year.group(1)) + 1) % 100:
            continue
        rows = []
        for line in page.splitlines():
            m = _ROW.match(line)
            if m:
                rows.append((int(m.group(1)), dollars_to_cents(m.group(2))))
        if not rows:
            continue
        key = (county.group(1).strip(), f"{year.group(1)}-{year.group(2)}")
        counties.setdefault(key, []).append((cls.group(1), number, rows))
    out = []
    for (name, school_year), classes in counties.items():
        draft = _draft(name, school_year, classes)
        if draft:
            out.append(draft)
    return out


def _draft(
    county: str, school_year: str, classes: list[tuple[str, int, list[tuple[int, int]]]]
) -> ScheduleDraft | None:
    names = [c for c, _, _ in classes]
    if len(set(names)) != len(names):
        return None  # a class printed twice: not the layout this reader knows
    years = sorted({y for _, _, rows in classes for y, _ in rows})
    if years != list(range(len(years))) or len(years) < 10:
        return None
    index = {y: i for i, y in enumerate(years)}
    cells: dict[tuple[int, int | None], Cell] = {}
    for k, (_, _, rows) in enumerate(classes):
        for y, cents in rows:
            if (index[y], k) in cells:
                return None
            cells[(index[y], k)] = Cell(cents)
    return ScheduleDraft(
        state=STATE,
        state_district_id=district_key(county),
        district_name=f"{county.title()} County Board of Education",
        school_year=school_year,
        lanes=[Lane(*LANE_NAMES[c]) for c in names],
        steps=[Step(f"{y} years", y) for y in years],
        cells=cells,
        notes=NOTES,
        source_page=min(p for _, p, _ in classes),
    )


def read_pdf(path: Path) -> list[ScheduleDraft]:
    return read_pages(ok_sde.pages(path))
