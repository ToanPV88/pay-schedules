"""Connecticut: teacher salary schedules of every district, compiled by the Connecticut Education
Association from the districts' contracts (D-071).

The book prints, for each school year ("2025-2026 SALARY SCHEDULES") and county, one grid per
district: a heading line ``BETHEL   STEP   BA   BA+15 ...`` and rows ``1  $54,501  $55,001 ...``.
A lane that has no pay at a step is left blank, so each amount is matched to the lane heading
nearest to it on the line, not by its order. Districts are named in capitals ("REGION 09",
"EAST HAMPTON"); the importer matches them to the NCES directory by name.
"""

from __future__ import annotations

import itertools
import re
from pathlib import Path

from pay_pipeline.schedules import ok_sde
from pay_pipeline.schedules.model import (
    Cell,
    Lane,
    ScheduleDraft,
    Step,
    dollars_to_cents,
    normalize_lane,
)

STATE = "CT"
NOTES = (
    "Compiled by the Connecticut Education Association from the district's teacher contract."
    " Blank cells: the lane has no pay at that step."
)

ALIASES = {"AMITY": "REGION 5"}
"""Book names of regional districts that the NCES directory lists by number."""

_YEAR = re.compile(r"(\d{4})\s*\D{1,3}\s*(\d{4})\s+SALARY\s+SCHEDULES")
_HEADING = re.compile(r"^(\S.*?)\s{2,}STEP\b(.*)$")
_ROW = re.compile(r"^\s+(\d{1,2}(?:\.\d)?[A-Z]?|[A-Z])\s+(\$.*)$")
_AMOUNT = re.compile(r"\$\s?\d{1,3}(?:,\d{3})+(?:\.\d{2})?")


def district_key(name: str) -> str:
    """'REGION 09' / 'Regional School District 09' -> 'REGION 9'; 'Bethel School District' ->
    'BETHEL'."""
    n = re.sub(r"\s+", " ", name.upper()).strip()
    n = re.sub(r"\b(?:SCHOOL DISTRICT|PUBLIC SCHOOLS|SCHOOLS)\b", "", n).strip()
    n = re.sub(r"^REGIONAL (?:SCHOOL )?(?:DISTRICT )?", "REGION ", n)
    n = re.sub(r"\b0+(\d)", r"\1", n)
    n = re.sub(r"\s+", " ", n).strip()
    return ALIASES.get(n, n)


def _clusters(centres: list[float], gap: float = 4.0) -> list[float]:
    """Column centres: amounts whose centres lie within ``gap`` characters form one column."""
    groups: list[list[float]] = []
    for c in sorted(centres):
        if groups and c - groups[-1][-1] <= gap:
            groups[-1].append(c)
        else:
            groups.append([c])
    return [sum(g) / len(g) for g in groups]


class _Grid:
    def __init__(self, name: str, year: str, page: int, words: list[tuple[str, float]]) -> None:
        self.name = name
        self.year = year
        self.page = page
        self.words = words  # heading words and their centre column
        self.rows: list[tuple[str, list[tuple[float, int]]]] = []

    def add(self, line: str, step: str, rest_at: int) -> None:
        amounts = [
            ((m.start() + m.end()) / 2, dollars_to_cents(m.group(0)))
            for m in _AMOUNT.finditer(line, rest_at)
        ]
        if amounts:
            self.rows.append((step, amounts))

    def draft(self) -> ScheduleDraft | None:
        """Columns are where the amounts are (a lane with no pay at a step is blank), and each
        heading word names the column nearest to it ("BA 30/ MA" is one lane, D-071)."""
        if len(self.rows) < 3:
            return None
        steps: list[str] = []
        for s, _ in self.rows:  # a step printed twice (Manchester's top step) is "13", "13b"
            steps.append(s if s not in steps else f"{s}b")
        if len(set(steps)) != len(steps):
            return None
        columns = _clusters([c for _, amounts in self.rows for c, _ in amounts])
        widest = max(len(a) for _, a in self.rows)
        if len(columns) != widest:
            # Tightly printed columns run into each other (Bethel 2026-27): take the column
            # centres from the rows that have every lane.
            full = [a for _, a in self.rows if len(a) == widest]
            columns = [sum(a[i][0] for a in full) / len(full) for i in range(widest)]
            gaps = [b - a for a, b in itertools.pairwise(columns)]
            if len(full) < 3 or min(gaps, default=9.0) < 5:
                return None  # amounts that do not line up in columns: do not guess
        names: list[list[str]] = [[] for _ in columns]
        for word, centre in self.words:
            k = min(range(len(columns)), key=lambda i: abs(columns[i] - centre))
            names[k].append(word)
        if not all(names):
            return None
        labels = [re.sub(r"(?<=\+)l(?=\d)", "1", " ".join(n)) for n in names]
        cells: dict[tuple[int, int | None], Cell] = {}
        for i, (_, amounts) in enumerate(self.rows):
            for c, a in amounts:
                k = min(range(len(columns)), key=lambda j: abs(columns[j] - c))
                if (i, k) in cells:
                    return None
                cells[(i, k)] = Cell(a)
        return ScheduleDraft(
            state=STATE,
            state_district_id=district_key(self.name),
            district_name=self.name.title(),
            school_year=self.year,
            lanes=[Lane(label, normalize_lane(label)) for label in labels],
            steps=[Step(s, int(s) - 1 if s.isdigit() else None) for s in steps],
            cells=cells,
            notes=NOTES,
            source_page=self.page,
        )


def read_pages(pages: list[str], years: set[str] | None = None) -> list[ScheduleDraft]:
    """Every district grid of the book; only the given school years ('2025-26') when set."""
    grids: list[_Grid] = []
    year: str | None = None
    current: _Grid | None = None
    for number, page in enumerate(pages, 1):
        for line in page.splitlines():
            m = _YEAR.search(line)
            if m and int(m.group(2)) == int(m.group(1)) + 1:
                year = f"{m.group(1)}-{m.group(2)[2:]}"
                current = None
                continue
            h = _HEADING.match(line)
            if h and year:
                at = h.start(2)
                words = [
                    (x.group(0), at + (x.start() + x.end()) / 2)
                    for x in re.finditer(r"\S+", h.group(2))
                ]
                current = _Grid(h.group(1).strip(), year, number, words) if words else None
                if current:
                    grids.append(current)
                continue
            r = _ROW.match(line)
            if r and current:
                current.add(line, r.group(1), r.start(2))
            elif current and not current.rows and line.strip() and "$" not in line:
                # the heading goes on over a second line (Ridgefield: "YR  YR 9  YR 18")
                current.words += [
                    ((x.start() + x.end()) / 2, x.group(0))[::-1] for x in re.finditer(r"\S+", line)
                ]
    out = []
    for g in grids:
        if years is None or g.year in years:
            d = g.draft()
            if d:
                out.append(d)
    return out


def read_pdf(path: Path, years: set[str] | None = None) -> list[ScheduleDraft]:
    return read_pages(ok_sde.pages(path), years)
