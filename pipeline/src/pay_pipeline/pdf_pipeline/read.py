"""Extract (PLAN Công đoạn 5, bước 4) without any AI API (D-022): read the salary grid from the
text layer of a document by position.

Two independent readers turn a page into lines of positioned words:

* ``layout``: ``pdftotext -layout`` (poppler); a word's position is its character column;
* ``words``: pdfplumber (pdfminer); a word's position is its x coordinate in points.

Both feed the same table finder:

1. A **data row** is a line that starts with a step label (``1``, ``31+``, ``0-3 Years``,
   ``Step 4``, or a letter: ``C``, ``AA``, ``T&U``) followed by amounts in the range of annual
   pay. A line of amounts without a label right under a data row continues it (schedules
   printed on two lines per step).
2. Consecutive data rows form a table; a step label that does not grow, or two non-data lines in
   a row, end it.
3. **Columns** are found by clustering the right edges of the amounts (numbers are right
   aligned); an amount is placed in the nearest column, so blank cells of a staircase schedule
   stay blank. Two amounts falling in one column of a row make the table unreadable.
4. **Lane labels** are the header words above the first row, placed in the nearest column.

The teacher table is the largest table with teacher words near it (and no classified or
administrator words), preferring the first one in the document, unless that one states a
calendar outside a standard teacher year and a later one states a standard year (D-026). The
result uses the same JSON shape as the extraction schema (``extract.to_draft``), so validation
and storage are shared with every other source. Comparing the two readers cell by cell is the
deterministic version of "extract twice independently" (as travienphi's trace-check).
"""

from __future__ import annotations

import re
import statistics
import subprocess
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any

import pdfplumber

from pay_pipeline.documents.classify import NEGATIVE_RE, TEACHER_RE, school_years

LAYOUT = "layout-text@9"
WORDS = "pdfplumber-words@9"
XLSX = "xlsx-cells@9"
DOCX = "docx-cells@9"
HTML = "html-cells@9"
# Đổi cách đọc thì tăng số phiên bản: tài liệu chỉ được coi là "đã xử lý" (bỏ qua khi sha256 không
# đổi) nếu đã có lần đọc bằng một bộ đọc trong danh sách này.
READERS = frozenset({LAYOUT, WORDS, XLSX, DOCX})
MIN_AMOUNT, MAX_AMOUNT = 10_000.0, 400_000.0
MIN_ROWS, MIN_CELLS = 3, 8
STANDARD_DAYS = (175, 200)

_MONEY = re.compile(r"^\(?\$?\(?(\d{1,3}(?:,\d{3})+|\d{5,6})(\.\d{1,2})?\)?\**$")
_LABEL = re.compile(
    r"^(?:(?:step|level|year|yrs?)\.?\s*)?(\d{1,2})(?:\s*(?:-|–|to)\s*(\d{1,2}))?\s*(\+|\*{1,3})?"
    r"(?:\s*(?:years?|yrs?\.?)(?:\s+and\s+(?:over|above|up))?)?\s*(\+)?$",
    re.I,
)
# Steps named by letters (Florida, Maryland): "C", "N", "AA", "T&U" (two steps paid the same).
_LETTER = re.compile(r"^([A-Z])\1?(?:&[A-Z]{1,2})?$")
_PLACEMENT = re.compile(r"^[\d,\-–+]+$")
_CODE = re.compile(r"^(?:[A-Z]{1,2}|[IVX]{1,5})$")
_NUMBER = re.compile(r"^\(?\$?\d[\d,]*\.\d{1,5}\)?\**$")
# Figures that sit beside the annual amounts without being one: a daily rate ("336.90"), a stipend
# below MIN_AMOUNT ("2,500", Garland ISD's retention allotment) or an empty cell ("-").
_SIDE = re.compile(r"^(?:\(?\$?\d[\d,]*\.\d{1,5}\)?\**|\$?\d,\d{3}|\$0|-|–|—|--)$")
_TITLE = re.compile(
    r"salary|salaries|schedule|district|schools?\b|board|approved|adopted|effective|revised|"
    r"unified|county|fiscal|\b20\d\d\b",
    re.I,
)
_NOISE = re.compile(
    r"^(?:20\d\d(?:[-–/]\d{2,4})?|\(?[+-]?\d+(?:\.\d+)?%\)?|_{3,}|annual|\(?1[6-9]\d|\(?2[0-4]\d|"
    r"days?\)?)$",
    re.I,
)
# Any calendar length, to tell a 240/260-day schedule from a 187-day one.
_ANY_DAYS = re.compile(
    r"\b(\d{3})\s*-?\s*(?:duty\s+|work\s+|working\s+|contract\s+|service\s+)?days?\b", re.I
)
_DAYS = re.compile(
    r"\b(1[6-9]\d|2[0-3]\d)\s*(?:-?\s*)(?:duty\s+|work\s+|working\s+|contract\s+|service\s+)?days?\b",
    re.I,
)


@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    x1: float


@dataclass
class Line:
    words: list[Word]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass
class Row:
    label: str
    amounts: list[tuple[float, float, float]]  # (x0, x1, value)
    line_index: int


@dataclass
class Table:
    page: int
    rows: list[Row]
    header: list[Line]
    context: str  # lines above the table (title)
    columns: list[float] = field(default_factory=list)  # right edge per column
    grid: list[list[float | None]] = field(default_factory=list)
    lanes: list[str] = field(default_factory=list)
    step_header: str = ""

    @property
    def cells(self) -> int:
        return sum(v is not None for r in self.grid for v in r)


def money(text: str) -> float | None:
    m = _MONEY.match(text.strip())
    if not m:
        return None
    value = float(m.group(1).replace(",", "") + (m.group(2) or ""))
    return value if MIN_AMOUNT <= value <= MAX_AMOUNT else None


# ---------------------------------------------------------------- readers


def layout_lines(path: Path) -> list[list[Line]]:
    """Pages of lines from ``pdftotext -layout``; x is the character column."""
    out = subprocess.run(  # noqa: S603
        ["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],  # noqa: S607
        capture_output=True, timeout=120, check=False,
    ).stdout.decode("utf-8", errors="replace")  # fmt: skip
    pages = out.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    result = []
    for page in pages:
        lines = []
        for raw in page.split("\n"):
            words = [
                Word(m.group(), float(m.start()), float(m.end())) for m in re.finditer(r"\S+", raw)
            ]
            lines.append(Line(words))
        result.append(lines)
    return result


def plumber_lines(path: Path) -> list[list[Line]]:
    """Pages of lines from pdfplumber words; x in points, lines grouped by vertical position."""
    result = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=3, y_tolerance=2, keep_blank_chars=False)
            words.sort(key=lambda w: float(w["top"]))
            lines: list[Line] = []
            line_top: float | None = None
            reach = 2.5
            for w in words:
                top = float(w["top"])
                # Words of one printed row may sit a few points apart (step labels set lower
                # than the amounts, Mobile County): a word starting within 40 % of the first
                # word's height belongs to its line.
                if line_top is None or top - line_top > reach:
                    lines.append(Line([]))
                    line_top = top
                    reach = max(2.5, 0.4 * (float(w["bottom"]) - top))
                lines[-1].words.append(Word(str(w["text"]), float(w["x0"]), float(w["x1"])))
            for line in lines:
                line.words = _join_touching(sorted(line.words, key=lambda w: w.x0))
            result.append(lines)
    return result


def _join_touching(words: list[Word], gap: float = 0.6) -> list[Word]:
    """pdfminer may split one number when its glyphs come from two fonts ('4' '2,024')."""
    out: list[Word] = []
    for w in words:
        if out and -0.5 <= w.x0 - out[-1].x1 < gap:
            prev = out.pop()
            out.append(Word(prev.text + w.text, prev.x0, w.x1))
        else:
            out.append(w)
    return out


# ---------------------------------------------------------------- table finding


def _normalise(words: list[Word]) -> list[Word]:
    """Join '$' and '(' tokens to the number that follows; drop lone '$'."""
    out: list[Word] = []
    for w in words:
        if out and out[-1].text in ("$", "($", "(") and re.match(r"^[\d(]", w.text):
            prev = out.pop()
            out.append(Word(prev.text + w.text, prev.x0, w.x1))
        else:
            out.append(w)
    return [w for w in out if w.text not in ("$",)]


def parse_row(line: Line, index: int) -> Row | None:
    words = _normalise(line.words)
    first = next((i for i, w in enumerate(words) if money(w.text) is not None), None)
    if first is None:
        return None
    head = words[:first]
    while head and (_NUMBER.match(head[-1].text) or _SIDE.match(head[-1].text)):
        # a daily/hourly/semi-monthly figure ("$2,521") or an increase ("$0") before the first
        # annual amount (D-054)
        head = head[:-1]
    label = " ".join(w.text for w in head).strip()
    # "0,1,2   1   $27,175": a placement column (years of experience) before the step
    if (
        not _LABEL.match(label)
        and len(head) >= 2
        and _LABEL.match(head[-1].text)
        and all(_PLACEMENT.match(w.text) for w in head[:-1])
    ):
        label = head[-1].text
    if not _LABEL.match(label) and not _LETTER.match(label):
        # "1  A  $57,471 ...": a step number followed by one short code (letter or roman numeral)
        if len(head) == 2 and _LABEL.match(head[0].text) and _CODE.match(head[1].text):
            label = words[0].text
        else:
            return None
    amounts: list[tuple[float, float, float]] = []
    for w in words[first:]:
        value = money(w.text)
        if amounts and not _SIDE.match(w.text) and value is None:
            # Text far to the right of the amounts (a side box or footnote on the same line)
            # ends the row; text close to them means the line is not a plain table row.
            width = statistics.median(x1 - x0 for x0, x1, _ in amounts)
            if w.x0 - amounts[-1][1] > 1.5 * width:
                break
        if value is not None:
            amounts.append((w.x0, w.x1, value))
        elif _SIDE.match(w.text):
            continue  # a daily, hourly or monthly figure, or a stipend, beside the annual one
        elif w.text[:1] in "*†‡":
            continue  # a footnote marker such as "*2024-25" after the row
        elif w.text.strip("*") != label.strip("*") and not re.fullmatch(r"[*†‡]+|\d{1,2}", w.text):
            return None  # words mixed into the amounts: not a plain table row
    return Row(label, amounts, index)


def _amount_only(line: Line) -> list[tuple[float, float, float]] | None:
    words = _normalise(line.words)
    if not words:
        return None
    values = [money(w.text) for w in words]
    if any(v is None for v in values):
        return None
    return [(w.x0, w.x1, v) for w, v in zip(words, values, strict=True) if v is not None]


def _label_number(label: str) -> int | None:
    """Order of a step label: its number, or its letter (A = 1 … Z = 26, AA = 27 …)."""
    m = _LABEL.match(label)
    if m:
        return int(m.group(1))
    m = _LETTER.match(label)
    if m:
        return ord(m.group(1)) - ord("A") + 1 + (26 if m.group(0)[1:2] == m.group(1) else 0)
    return None


def _years_number(label: str) -> int | None:
    """Years of experience in a numeric step label; letters carry none."""
    m = _LABEL.match(label)
    return int(m.group(1)) if m else None


def _right_of(line: Line, rows: list[Row]) -> bool:
    """True when every word of ``line`` lies clearly right of the table's amounts."""
    right = max(x1 for r in rows for _, x1, _ in r.amounts)
    width = statistics.median(x1 - x0 for r in rows for x0, x1, _ in r.amounts)
    return min(w.x0 for w in line.words) > right + 2 * width


_TOTAL = re.compile(r"^(?:total|annual\s+total|total\s+salary)$", re.I)


def collapse_components(lines: list[Line]) -> list[Line]:
    """Keep only the TOTAL line of each step when a step is printed as several pay components.

    Seattle prints, under each step number, "Base Pay", "Contractual Days", "Tech Days",
    "Responsibility/Incentive" and "TOTAL" lines; the annual salary is the TOTAL line. Pages
    without at least three such TOTAL lines are returned unchanged. Dropped lines become empty
    lines so that line numbers (used for headers and context) do not move.
    """

    def label_of(line: Line) -> str:
        words = [w.text for w in line.words if money(w.text) is None and not _SIDE.match(w.text)]
        return " ".join(words)

    totals = [ln for ln in lines if ln.words and _TOTAL.match(label_of(ln))]
    if len(totals) < 3:
        return lines
    out: list[Line] = []
    step: Word | None = None
    for line in lines:
        words = line.words
        has_money = any(money(w.text) is not None or _SIDE.match(w.text) for w in words)
        if words and has_money and _LABEL.match(words[0].text):
            step = words[0]  # "1  Base Pay  180.00  $63,117 ..."
            out.append(Line([]))
        elif words and has_money and step is not None and _TOTAL.match(label_of(line)):
            amounts = [w for w in words if money(w.text) is not None]
            out.append(Line([step, *amounts]))
            step = None
        elif words and has_money and step is not None:
            out.append(Line([]))  # another component of the same step
        else:
            out.append(line)
    return out


def find_tables(lines: list[Line], page: int) -> list[Table]:
    lines = collapse_components(lines)
    tables: list[Table] = []
    current: list[Row] = []
    gap = 0

    def close() -> None:
        nonlocal current
        if len(current) >= MIN_ROWS:
            first = current[0].line_index
            header = lines[max(0, first - 7) : first]  # filtered in _build
            context = "\n".join(ln.text for ln in lines[max(0, first - 14) : first])
            tables.append(Table(page, current, header, context))
        current = []

    for i, line in enumerate(lines):
        row = parse_row(line, i)
        if row is not None:
            n, prev = (
                _label_number(row.label),
                _label_number(current[-1].label) if current else None,
            )
            # Steps run up, or (Muhlenberg: "From Top", 16 down to 1) down; a step that breaks the
            # direction of the rows so far starts a new table.
            first_n = _label_number(current[0].label) if current else None
            descending = (
                len(current) >= 2 and first_n is not None and prev is not None and prev < first_n
            )
            if n is not None and prev is not None:
                broken = n == prev or (n < prev) != (descending or (len(current) == 1 and n < prev))
            else:
                broken = False
            if current and (gap > 1 or broken):
                close()
            current.append(row)
            gap = 0
            continue
        cont = _amount_only(line) if current and gap == 0 else None
        if cont:
            current[-1].amounts.extend(cont)
            current[-1].amounts.sort()
            continue
        if line.words and current and _right_of(line, current):
            continue  # a side box printed beside the table: not part of it, not a break
        if current and len(line.words) == 1 and _LABEL.match(line.words[0].text):
            n, prev = _label_number(line.words[0].text), _label_number(current[-1].label)
            if n is not None and prev is not None and n > prev:
                continue  # a step with no amount in any lane (empty row of a staircase)
        if line.words:
            gap += 1
            if gap > 1:
                close()
    close()
    return [t for t in (_build(t) for t in tables) if t is not None]


def _cluster(edges: list[float], tolerance: float) -> list[float]:
    groups: list[list[float]] = []
    for e in sorted(edges):
        if groups and e - groups[-1][-1] <= tolerance:
            groups[-1].append(e)
        else:
            groups.append([e])
    return [statistics.median(g) for g in groups]


def _build(table: Table) -> Table | None:
    edges = [x1 for r in table.rows for _, x1, _ in r.amounts]
    widths = [x1 - x0 for r in table.rows for x0, x1, _ in r.amounts]
    tolerance = max(1.5, statistics.median(widths) * 0.45) if widths else 2.0
    columns = _cluster(edges, tolerance)
    grid: list[list[float | None]] = []
    for r in table.rows:
        row: list[float | None] = [None] * len(columns)
        for _, x1, value in r.amounts:
            j = min(range(len(columns)), key=lambda k: abs(columns[k] - x1))
            if row[j] is not None:
                return None  # two amounts in one column: layout not understood
            row[j] = value
        grid.append(row)
    table.columns, table.grid = columns, grid
    if table.cells < MIN_CELLS:
        return None
    # Header words: nearest column by horizontal centre; words left of the first column (minus
    # half a column width) label the step column.
    lefts = [
        min(x0 for r in table.rows for x0, x1, _ in r.amounts if abs(x1 - c) <= tolerance)
        for c in columns
    ]
    centres = [(lo + c) / 2 for lo, c in zip(lefts, columns, strict=True)]
    table.header = _header_lines(table.header, centres, statistics.median(widths))
    lanes: list[list[str]] = [[] for _ in columns]
    step_words: list[str] = []
    for line in table.header:
        for w in line.words:
            centre = (w.x0 + w.x1) / 2
            if w.x1 <= lefts[0] or centre < lefts[0] - (columns[0] - lefts[0]) * 0.5:
                step_words.append(w.text)
                continue
            if centre > columns[-1] + (columns[-1] - lefts[-1]) * 0.6:
                continue  # right of the table (e.g. step numbers repeated on the right)
            j = min(range(len(columns)), key=lambda k: abs(centres[k] - centre))
            lanes[j].append(w.text)
    table.lanes = [
        " ".join(w for w in words if not _NOISE.match(w)) or f"Column {j + 1}"
        for j, words in enumerate(lanes)
    ]
    table.step_header = " ".join(step_words)
    return table


def _header_lines(candidates: list[Line], centres: list[float], width: float) -> list[Line]:
    """Lines right above the table that label its columns.

    Going up from the first row: blank lines are skipped (two in a row end the header), and a
    title line ends it, e.g. "2025-2026 Certificated Teacher Salary Schedule". A title is one
    phrase (no wide gaps) with title words (salary, schedule, district, board, approved, a
    year...). At most 5 lines.
    """
    out: list[Line] = []
    blanks = 0
    for line in reversed(candidates):
        if not line.words:
            blanks += 1
            if blanks == 2 and out:
                break
            continue
        blanks = 0
        words = line.words
        if any(money(w.text) is not None for w in words):
            break  # a line of amounts above the table is another table, not a header
        gaps = [b.x0 - a.x1 for a, b in pairwise(words)]
        covered = sum(1 for c in centres if words[0].x0 <= c <= words[-1].x1)
        tight = not gaps or max(gaps) < 0.5 * width
        title = tight and covered >= 1 and bool(_TITLE.search(line.text))
        if title:
            break
        out.insert(0, line)
        if len(out) == 5:
            break
    return out


# A schedule for only part of the teachers: hired before a date (grandfathered), non-classroom.
# Preferred less than the main schedule, and sent to review when chosen (D-022).
_SCOPE = re.compile(
    r"hired\s+(?:prior\s+to|before|on\s+or\s+before)|grandfather\w*|"
    r"non[-\s]?classroom|non[-\s]?instructional",
    re.I,
)


def scope_note(t: Table) -> str | None:
    tail = t.context.splitlines()[-12:]
    hit = next((ln for ln in reversed(tail) if _SCOPE.search(ln)), None)
    return " ".join(hit.split())[:200] if hit else None


def _score(t: Table) -> float:
    near = t.context[-900:]
    score = float(t.cells)
    if TEACHER_RE.search(near) or TEACHER_RE.search(" ".join(t.lanes)):
        score += 200
    if NEGATIVE_RE.search("\n".join(near.splitlines()[-6:])):
        score -= 300
    return score


def pick_table(tables: list[Table]) -> Table | None:
    usable = [t for t in tables if _score(t) > 0]
    if not usable:
        return None
    # A schedule for the whole staff beats one for part of it (hired before a date, non-classroom).
    if any(not scope_note(t) for t in usable):
        usable = [t for t in usable if not scope_note(t)]
    best = max(_score(t) for t in usable)
    # First table in document order that is nearly as good as the best one. When that table
    # states a calendar outside a standard teacher year (175-200 days), a later one that states
    # a standard year is taken instead (Mobile County prints 202- and 187-day schedules after
    # one for 240/260 days).
    good = [t for t in usable if _score(t) >= best * 0.6]
    # A multi-year contract prints one grid per school year (2022-23, 2023-24, 2024-25): the
    # latest year is the one in force, so only its grids stay in the running (D-052).
    years = {id(t): (school_years(t.context) or [""])[-1] for t in good}
    latest = max(years.values())
    if latest and len({y for y in years.values() if y}) > 1:
        good = [t for t in good if years[id(t)] == latest]
    first_days = _table_days(good[0])
    if first_days is None or _standard(first_days):
        return good[0]
    return next((t for t in good if _standard(_table_days(t))), good[0])


def _table_days(t: Table) -> int | None:
    """Contract days stated in the lines just above a table ("187 DAYS", "196-Day")."""
    text = "\n".join(t.context.splitlines()[-8:]) + "\n" + " ".join(t.lanes)
    found = [int(d) for d in _ANY_DAYS.findall(text) if 100 <= int(d) <= 366]
    return found[-1] if found else None


def _standard(days: int | None) -> bool:
    return days is not None and STANDARD_DAYS[0] <= days <= STANDARD_DAYS[1]


def _years(table: Table, page_text: str) -> str | None:
    found = school_years(table.context) or school_years(page_text)
    return found[0] if found else None


def _days(table: Table, page_text: str) -> int | None:
    for text in (table.context, page_text):
        m = _DAYS.search(text)
        if m:
            return int(m.group(1))
    return None


def to_answer(table: Table | None, page_text: str, reader: str, reason: str = "") -> dict[str, Any]:
    if table is None:
        return {
            "is_teacher_salary_schedule": False,
            "reason": reason or "Không tìm thấy bảng bậc × lane",
            "reader": reader, "lanes": [], "steps": [], "cells": [],
        }  # fmt: skip
    years = bool(re.search(r"year|yrs|experience", table.step_header, re.I))
    title = next(
        (
            ln.strip()
            for ln in reversed(table.context.splitlines())
            if re.search(r"schedule|salary|scale|pay plan", ln, re.I)
            and not re.search(
                r"years of experience|daily rate|^\s*steps?\b|do not use|"
                r"\b(?:can|will|may|must)\b",
                ln,
                re.I,
            )
        ),
        "",
    )
    return {
        "is_teacher_salary_schedule": True,
        "reason": f"Bảng {len(table.rows)} bậc × {len(table.columns)} cột ở trang {table.page}",
        "reader": reader,
        "school_year": _years(table, page_text),
        "title": " ".join(title.split())[:300],
        "contract_days": _days(table, page_text),
        "pay_basis": "annual",
        "lanes": [lane_label(x, title) for x in table.lanes],
        "steps": [
            {"label": r.label, "years_experience": _years_number(r.label) if years else None}
            for r in table.rows
        ],
        "cells": table.grid,
        "stipends": [],
        "notes": None,
        "source_pages": [table.page],
        "scope_note": scope_note(table),
        "other_schedules": [],
    }


# Column-unit words printed under each lane ("Hourly Rate | Annual Rate"): not part of the lane.
_UNIT_WORDS = frozenset(
    {
        "hourly",
        "daily",
        "annual",
        "annualized",
        "rate",
        "rates",
        "monthly",
        "semi-monthly",
        "biweekly",
        "bi-weekly",
    }
)
# Words that name a lane: never removed even when the title uses them too.
_LANE_WORDS = re.compile(
    r"^(ba|bs|ma|ms|bachelors?|masters?|bachelor's|master's|doctor\w*|degrees?|phd|eds?|"
    r"specialist|plus|lane|class|column|rank|teachers?|credits?|hours?|units?)$",
    re.I,
)
_DATE_WORD = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")
_ABBREV = re.compile(r"^[A-Z][A-Z0-9+/&.-]*$")


def _word_key(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


def lane_label(text: str, title: str = "") -> str:
    """Lane heading without unit words and dates, and without title words swept in front of it.

    Title words are dropped only from the start of the label and only when what is left starts
    like a lane name ("Licensed MA" under "... Licensed ... Schedule" -> "MA").
    """
    words = [
        w
        for w in text.split()
        if re.sub(r"\(\d\)$", "", w.lower()).strip("()") not in _UNIT_WORDS
        and not _DATE_WORD.match(w)
        and w.lower() != "effective"
    ] or text.split()
    title_words = {
        _word_key(w) for w in title.split() if len(_word_key(w)) >= 4 and not _LANE_WORDS.match(w)
    }
    start = 0
    while start < len(words) - 1 and _word_key(words[start]) in title_words:
        start += 1
    rest = words[start:]
    if start and (_LANE_WORDS.match(rest[0]) or _ABBREV.match(rest[0])):
        words = rest
    return " ".join(words)


def read_pages(pages: list[list[Line]], prefer: list[int], reader: str) -> dict[str, Any]:
    order = sorted(p for p in prefer if 1 <= p <= len(pages)) + [
        p for p in range(1, len(pages) + 1) if p not in prefer
    ]
    tables: list[Table] = []
    for p in order[:12]:
        tables += find_tables(pages[p - 1], p)
    table = pick_table(tables)
    text = "\n".join(ln.text for ln in pages[table.page - 1]) if table else ""
    return to_answer(table, text, reader)


def read_pdf(path: Path, prefer: list[int]) -> list[dict[str, Any]]:
    """Two independent readings of a PDF (pdfplumber words, then layout text)."""
    answers = []
    # pdfplumber first: exact coordinates give better lane labels; layout text is the check.
    for reader, loader in ((WORDS, plumber_lines), (LAYOUT, layout_lines)):
        try:
            answers.append(read_pages(loader(path), prefer, reader))
        except Exception as exc:  # a broken PDF must not stop the batch
            answers.append(to_answer(None, "", reader, f"{type(exc).__name__}: {exc}"[:200]))
    return answers


def grid_lines(rows: list[list[Any]]) -> list[Line]:
    """Lines from spreadsheet/Word table cells; x is the column index."""
    out = []
    for row in rows:
        words = []
        for j, value in enumerate(row):
            text = "" if value is None else str(value).strip()
            if isinstance(value, float) and value.is_integer():
                text = str(int(value))
            if text:
                words.append(Word(text, j * 10.0, j * 10.0 + 9))
        out.append(Line(words))
    return out


def read_xlsx(path: Path) -> dict[str, Any]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        tables: list[Table] = []
        texts: dict[int, str] = {}
        for i, ws in enumerate(wb.worksheets, 1):
            rows = [
                list(r) for _, r in zip(range(500), ws.iter_rows(values_only=True), strict=False)
            ]
            lines = grid_lines(rows)
            texts[i] = f"{ws.title}\n" + "\n".join(ln.text for ln in lines)
            tables += find_tables(lines, i)
    finally:
        wb.close()
    table = pick_table(tables)
    return to_answer(table, texts.get(table.page, "") if table else "", XLSX)


def read_docx(path: Path) -> dict[str, Any]:
    import zipfile

    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    tables: list[Table] = []
    for i, tbl in enumerate(re.findall(r"<w:tbl>.*?</w:tbl>", xml, re.S), 1):
        rows = []
        for tr in re.findall(r"<w:tr[ >].*?</w:tr>", tbl, re.S):
            cells = re.findall(r"<w:tc>.*?</w:tc>", tr, re.S)
            rows.append([" ".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", c)) for c in cells])
        tables += find_tables(grid_lines(rows), i)
    table = pick_table(tables)
    text = re.sub(r"<[^>]+>", " ", xml)
    return to_answer(table, text if table else "", DOCX)


def read_html(path: Path) -> dict[str, Any]:
    """Salary tables written as HTML tables on a district web page (D-046)."""
    from pay_pipeline.documents.classify import html_table_rows, html_tables

    text = path.read_bytes().decode("utf-8", errors="replace")
    tables: list[Table] = []
    pages: dict[int, str] = {}
    for i, block in enumerate(html_tables(text), 1):
        lines = grid_lines(html_table_rows(block))
        pages[i] = "\n".join(ln.text for ln in lines)
        tables += find_tables(lines, i)
    table = pick_table(tables)
    title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    head = (title.group(1).strip() + "\n") if title else ""
    return to_answer(table, head + pages.get(table.page, "") if table else "", HTML)
