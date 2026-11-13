"""Oklahoma: "Oklahoma Public Schools Local Salary Schedules" (OSDE, Office of School Personnel
Records), one PDF book per school year (D-029).

Every district that has its own schedule gets one page in the same state form::

    School Year: 2025-2026
    COUNTY-DISTRICT NAME: TULSA- TULSA   COUNTY-DISTRICT CODE: 72 - I001   Hours/Days: 7.84/176
      Years   Bach.   *Bach.+  ...  NBCT  ...  Mast.  ...  Doct.  *NBCT
     of Exp.  Degree  30 Hrs   ...  Bach. ...  Degree ...  Degree Doct.
        0     43,500  ...

The 18 columns are always the same (bachelor's, bachelor's + hours x3, the same with National Board
certification, then master's, then doctorate); a column the district does not use is printed
empty ("0 Hrs") and is left out. Columns are found from the header words' positions in
``pdftotext -layout`` text, and each amount goes to the nearest column.

Districts that pay the state minimum are only listed ("THE FOLLOWING SCHOOL DISTRICTS ARE USING
THE STATE MINIMUM SALARY SCHEDULE"): they get the state minimum schedule printed in the book,
with a note saying so.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from pay_pipeline.schedules.model import Cell, Lane, ScheduleDraft, Step, dollars_to_cents

STATE = "OK"
COLUMNS = 18
MAX_OFFSET = 0.4
"""An amount's centre must lie within this share of the column spacing from its column."""
BLANK_NOTE = "No salary in the state book for this column and years of experience"
MINIMUM_NOTE = (
    "This district uses the Oklahoma state minimum teacher salary schedule"
    " (70 O.S. § 18-114.15), as listed by the Oklahoma State Department of Education."
)

_YEAR = re.compile(r"School Year:\s*(\d{4})\s*-\s*(\d{4})")
_DISTRICT = re.compile(
    r"COUNTY-DISTRICT NAME:\s*(?P<name>.+?)\s{2,}COUNTY-DISTRICT CODE:\s*(?P<county>\d{2})\s*-\s*"
    r"(?P<code>[A-Z]\d{3})(?:.*?Hours/Days:\s*[\d.]+\s*/\s*(?P<days>\d{2,3}))?"
)
_AMOUNT = re.compile(r"^\$?(\d{1,3}(?:,\d{3})+|\d{4,6})(?:\.\d{2})?$")
_LISTED = re.compile(
    r"\b(\d{2})([CIDV]\d{3})\s+([A-Z][A-Z0-9 .'&/-]*?[A-Z0-9.])(?=\s{2,}|$)", re.MULTILINE
)

# Column heading (words of the three header lines) -> normalised lane (D-017 names); NBCT lanes
# have no normalised form, so they never mix with plain degree lanes in comparisons.
_BASE = {"BACH": ("BA", 1), "MAST": ("MA", 2), "DOCT": ("PhD", 3)}


@dataclass(frozen=True)
class _Word:
    text: str
    x0: int
    x1: int

    @property
    def centre(self) -> float:
        return (self.x0 + self.x1) / 2


def _words(line: str) -> list[_Word]:
    return [_Word(m.group(), m.start(), m.end()) for m in re.finditer(r"\S+", line)]


def pages(path: Path) -> list[str]:
    out = subprocess.run(  # noqa: S603
        ["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],  # noqa: S607
        capture_output=True, timeout=300, check=True,
    ).stdout.decode("utf-8", errors="replace")  # fmt: skip
    return out.split("\f")


def school_year(text: str) -> str | None:
    m = _YEAR.search(text)
    if not m:
        return None
    start, end = int(m.group(1)), int(m.group(2))
    return f"{start}-{end % 100:02d}" if end == start + 1 else None


def _normalised(label: str) -> str | None:
    text = label.upper()
    if "NBCT" in text or "NATIONAL BOARD" in text:
        return None
    for key, (lane, _) in _BASE.items():
        if text.startswith(key):
            hours = re.search(r"(\d+)\s*HRS", text)
            if hours and lane != "PhD":
                return f"{lane}+{hours.group(1)}"
            return lane if "DEGREE" in text else None
    return None


def _label(words: list[str]) -> str:
    return " ".join(w.lstrip("*") for w in words)


def read_district_page(text: str, page_number: int, year: str) -> ScheduleDraft | None:
    """One district page; None when the page is not a district schedule."""
    head = _DISTRICT.search(text)
    if head is None:
        return None
    lines = text.splitlines()
    top = next((i for i, ln in enumerate(lines) if re.match(r"^\s*Years\b", ln)), None)
    if top is None or top + 2 >= len(lines):
        return None
    titles = _words(lines[top])[1:]  # drop "Years"
    if len(titles) != COLUMNS:
        return None
    centres = [w.centre for w in titles]
    gap = min(b - a for a, b in pairwise(centres))
    left_edge = (_words(lines[top])[0].centre + centres[0]) / 2

    def column(x: float) -> int:
        return min(range(len(centres)), key=lambda j: abs(centres[j] - x))

    headings: list[list[str]] = [[w.text] for w in titles]
    for line in lines[top + 1 : top + 3]:
        for w in _words(line):
            if w.centre > left_edge:
                headings[column(w.centre)].append(w.text)

    rows: list[tuple[int, dict[int, int]]] = []
    for line in lines[top + 3 :]:
        words = _words(line)
        if not words:
            continue
        if not re.fullmatch(r"\d{1,2}", words[0].text):
            if rows:
                break  # notes under the table
            continue
        amounts: dict[int, int] = {}
        for w in words[1:]:
            m = _AMOUNT.match(w.text)
            if m is None:
                return None  # a word that is not an amount: layout not understood
            j = column(w.centre)
            if abs(centres[j] - w.centre) > MAX_OFFSET * gap:
                return None  # amount between two columns: layout not understood
            if j in amounts:
                return None  # two amounts in one column
            amounts[j] = dollars_to_cents(m.group(0).lstrip("$"))
        rows.append((int(words[0].text), amounts))
    used = sorted({j for _, amounts in rows for j in amounts})
    if len(rows) < 3 or not used:
        return None

    lanes = []
    for j in used:
        label = _label(headings[j])
        lanes.append(Lane(label, _normalised(label)))
    steps = [Step(str(years), years) for years, _ in rows]
    cells: dict[tuple[int, int | None], Cell] = {}
    for i, (_, amounts) in enumerate(rows):
        for k, j in enumerate(used):
            amount = amounts.get(j)
            cells[(i, k)] = Cell(amount) if amount is not None else Cell(None, BLANK_NOTE)
    days = head.group("days")
    return ScheduleDraft(
        state=STATE,
        state_district_id=f"{head.group('county')}{head.group('code')}",
        district_name=" ".join(head.group("name").split()),
        school_year=year,
        lanes=lanes,
        steps=steps,
        cells=cells,
        contract_days=int(days) if days and 100 <= int(days) <= 366 else None,
        source_page=page_number,
    )


def read_minimum(text: str, page_number: int, year: str) -> ScheduleDraft | None:
    """The state minimum schedule page (lanes in fixed order, amounts with a dollar sign)."""
    if not re.search(r"STATE MINIMUM TEACHER SALARY\s+SCHEDULE", text.upper()):
        return None
    rows: list[tuple[int, list[int]]] = []
    for line in text.splitlines():
        words = line.split()
        if len(words) == 6 and words[0].isdigit() and all(_AMOUNT.match(w) for w in words[1:]):
            rows.append((int(words[0]), [dollars_to_cents(w.lstrip("$")) for w in words[1:]]))
    if len(rows) < 3:
        return None
    lanes = [
        Lane("Bachelor's Degree", "BA"),
        Lane("Bachelor's + National Board Certification"),
        Lane("Master's Degree", "MA"),
        Lane("Master's + National Board Certification"),
        Lane("Doctor's Degree", "PhD"),
    ]
    cells: dict[tuple[int, int | None], Cell] = {}
    for i, (_, amounts) in enumerate(rows):
        for k, amount in enumerate(amounts):
            cells[(i, k)] = Cell(amount)
    return ScheduleDraft(
        state=STATE,
        state_district_id="",
        district_name="",
        school_year=year,
        lanes=lanes,
        steps=[Step(str(years), years) for years, _ in rows],
        cells=cells,
        notes=MINIMUM_NOTE,
        source_page=page_number,
    )


def listed_on_minimum(text: str) -> list[tuple[str, str]]:
    """(state district id, name) of the districts listed as using the state minimum schedule."""
    if "USING" not in text.upper() or "STATE MIN" not in text.upper():
        return []
    return [(f"{c}{code}", " ".join(name.split())) for c, code, name in _LISTED.findall(text)]


def read_book(path: Path) -> list[ScheduleDraft]:
    texts = pages(path)
    year = next((y for t in texts if (y := school_year(t))), None)
    if year is None:
        raise ValueError(f"{path.name}: không đọc được năm học")
    out: list[ScheduleDraft] = []
    minimum: ScheduleDraft | None = None
    listed: list[tuple[str, str]] = []
    for n, text in enumerate(texts, 1):
        draft = read_district_page(text, n, year)
        if draft is not None:
            out.append(draft)
            continue
        if minimum is None:
            minimum = read_minimum(text, n, year)
        listed += listed_on_minimum(text)
    own = {d.state_district_id for d in out}
    if minimum is not None:
        for sid, name in listed:
            if sid not in own:
                out.append(
                    ScheduleDraft(
                        state=STATE,
                        state_district_id=sid,
                        district_name=name,
                        school_year=year,
                        lanes=list(minimum.lanes),
                        steps=list(minimum.steps),
                        cells=dict(minimum.cells),
                        notes=MINIMUM_NOTE,
                        source_page=minimum.source_page,
                    )
                )
                own.add(sid)
    return out
