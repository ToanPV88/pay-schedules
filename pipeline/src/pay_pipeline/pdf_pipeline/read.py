"""Extract (PLAN Công đoạn 5, bước 4) without any AI API (D-022): read the salary grid from the
text layer of a document by position.

Two independent readers turn a page into lines of positioned words:

* ``layout``: ``pdftotext -layout`` (poppler); a word's position is its character column;
* ``words``: pdfplumber (pdfminer); a word's position is its x coordinate in points.

Both feed the same table finder:

1. A **data row** is a line that starts with a step label (``1``, ``31+``, ``0-3 Years``,
   ``Step 4``) followed by amounts in the range of annual pay. A line of amounts without a label
   right under a data row continues it (schedules printed on two lines per step).
2. Consecutive data rows form a table; a step label that does not grow, or two non-data lines in
   a row, end it.
3. **Columns** are found by clustering the right edges of the amounts (numbers are right
   aligned); an amount is placed in the nearest column, so blank cells of a staircase schedule
   stay blank. Two amounts falling in one column of a row make the table unreadable.
4. **Lane labels** are the header words above the first row, placed in the nearest column.

The teacher table is the largest table with teacher words near it (and no classified or
administrator words), preferring the first one in the document. The result uses the same JSON
shape as the extraction schema (``extract.to_draft``), so validation and storage are shared with
every other source. Comparing the two readers cell by cell is the deterministic version of
"extract twice independently" (as travienphi's trace-check).
"""

from __future__ import annotations

import re
import statistics
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pdfplumber

from pay_pipeline.documents.classify import NEGATIVE_RE, TEACHER_RE, school_years

LAYOUT = "layout-text@1"
WORDS = "pdfplumber-words@1"
MIN_AMOUNT, MAX_AMOUNT = 10_000.0, 400_000.0
MIN_ROWS, MIN_CELLS = 3, 8

_MONEY = re.compile(r"^\(?\$?\(?(\d{1,3}(?:,\d{3})+|\d{5,6})(\.\d{1,2})?\)?\**$")
_LABEL = re.compile(
    r"^(?:(?:step|level|year|yrs?)\.?\s*)?(\d{1,2})(?:\s*(?:-|–|to)\s*(\d{1,2}))?\s*(\+|\*{1,3})?"
    r"(?:\s*(?:years?|yrs?\.?)(?:\s+and\s+(?:over|above|up))?)?\s*(\+)?$",
    re.I,
)
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
            for w in words:
                top = float(w["top"])
                if line_top is None or top - line_top > 2.5:
                    lines.append(Line([]))
                    line_top = top
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
    label = " ".join(w.text for w in words[:first]).strip()
    if not _LABEL.match(label):
        return None
    amounts = []
    for w in words[first:]:
        value = money(w.text)
        if value is not None:
            amounts.append((w.x0, w.x1, value))
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
    m = _LABEL.match(label)
    return int(m.group(1)) if m else None


def find_tables(lines: list[Line], page: int) -> list[Table]:
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
            if current and (gap > 1 or (n is not None and prev is not None and n <= prev)):
                close()
            current.append(row)
            gap = 0
            continue
        cont = _amount_only(line) if current and gap == 0 else None
        if cont:
            current[-1].amounts.extend(cont)
            current[-1].amounts.sort()
            continue
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
    title line ends it, e.g. "2025-2026 Certificated Teacher Salary Schedule". A title is one phrase (no wide gaps) with title words (salary,
    schedule, district, board, approved, a year...). At most 5 lines.
    """
    out: list[Line] = []
    blanks = 0
    for k, line in enumerate(reversed(candidates)):
        if not line.words:
            blanks += 1
            if blanks == 2 and out:
                break
            continue
        blanks = 0
        words = line.words
        gaps = [b.x0 - a.x1 for a, b in zip(words, words[1:], strict=False)]
        covered = sum(1 for c in centres if words[0].x0 <= c <= words[-1].x1)
        tight = not gaps or max(gaps) < 0.5 * width
        title = tight and covered >= 1 and bool(_TITLE.search(line.text))
        if title:
            break
        out.insert(0, line)
        if len(out) == 5:
            break
    return out


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
    best = max(_score(t) for t in usable)
    # First table in document order that is nearly as good as the best one.
    return next(t for t in usable if _score(t) >= best * 0.6)


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
            if re.search(r"schedule|salary|scale", ln, re.I)
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
        "lanes": [" ".join(x.split()) for x in table.lanes],
        "steps": [
            {"label": r.label, "years_experience": _label_number(r.label) if years else None}
            for r in table.rows
        ],
        "cells": table.grid,
        "stipends": [],
        "notes": None,
        "source_pages": [table.page],
        "other_schedules": [],
    }


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
    return to_answer(table, texts.get(table.page, "") if table else "", "xlsx-cells@1")


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
    return to_answer(table, text if table else "", "docx-cells@1")
