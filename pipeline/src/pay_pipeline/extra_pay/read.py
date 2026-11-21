"""Read coaching / extra-duty stipend tables from a district document (PLAN 11, đợt 1).

A stipend table is a list of positions ("Football – Head Varsity") with one amount, or one amount
per experience column ("Year 1" … "Year 6"). Rows are found line by line: a label of words, then
amounts. A small integer before the first amount is a count of positions ("HS FOOTBALL ASST 7
3,250") and is dropped; words after the amounts ("+13 days") are notes and are dropped. When a
row prints any amount with "$", only "$" amounts count, so position codes ("1302") are not read
as money. "N/A" or a dash in an amount column is an empty cell.

Two readers see the same page (``pdftotext -layout`` and pdfplumber words, the readers of the
teacher pipeline); a table is trusted only when both give the same rows and amounts (D-036).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pay_pipeline.documents.classify import school_years
from pay_pipeline.extra_pay.survey import _ACTIVITY_RE, STIPEND_RANGE
from pay_pipeline.pdf_pipeline.read import Line, Word, _cluster, layout_lines, plumber_lines

READERS = ("stipend-layout@2", "stipend-plumber@2")

_NUM = re.compile(r"^\(?(\$)?\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{2}))?\)?\**$")
_EMPTY = {"n/a", "na", "-", "–", "—", "--"}
_LETTER = re.compile(r"[A-Za-z]")
_NOT_A_ROW = re.compile(r"^(total|subtotal|page \d|step|years?|column|level)\b", re.I)
MIN_ROWS = 5
HEADER_REACH = 4  # lines above the first row searched for column headers
COLUMN_GAP = {"stipend-layout@2": 3.0, "stipend-plumber@2": 9.0}


@dataclass
class Amount:
    x0: float
    x1: float
    value: float | None  # None: printed empty ("N/A", "-")


@dataclass
class StipendRow:
    label: str
    amounts: list[Amount]
    line_index: int


@dataclass
class StipendTable:
    page: int
    rows: list[StipendRow]
    columns: list[str] = field(default_factory=list)
    grid: list[list[float | None]] = field(default_factory=list)
    context: str = ""


def _number(word: str) -> tuple[bool, float] | None:
    m = _NUM.match(word)
    if not m:
        return None
    value = float(m.group(2).replace(",", "") + ("." + m.group(3) if m.group(3) else ""))
    return (m.group(1) == "$", value)


def parse_row(line: Line, index: int) -> StipendRow | None:
    words = line.words
    label: list[Word] = []
    nums: list[tuple[Word, bool, float | None]] = []
    for w in words:
        if nums:
            n = _number(w.text)
            if n is not None:
                nums.append((w, n[0], n[1]))
            elif w.text.lower() in _EMPTY:
                nums.append((w, False, None))
            else:
                break  # notes after the amounts
            continue
        n = _number(w.text)
        if n is not None and label and (n[0] or "," in w.text or n[1] >= STIPEND_RANGE[0]):
            nums.append((w, n[0], n[1]))
        elif n is not None and label and n[1] < STIPEND_RANGE[0] and not n[0]:
            continue  # a count of positions before the first amount
        elif w.text.lower() in _EMPTY and label:
            nums.append((w, False, None))
        else:
            label.append(w)
    text = " ".join(w.text for w in label).strip(" :.-–")
    if len(_LETTER.findall(text)) < 3 or _NOT_A_ROW.match(text):
        return None
    if any(dollar for _, dollar, _ in nums):
        nums = [(w, d, v) for w, d, v in nums if d or v is None]
    amounts = [Amount(w.x0, w.x1, v) for w, _, v in nums]
    if not any(a.value is not None for a in amounts):
        return None
    return StipendRow(text, amounts, index)


_ROLE_ONLY = re.compile(
    r"^(head|asst\.?|assistant|varsity|jv|junior varsity|freshman|9th grade|middle school|"
    r"ms|hs|high school|coach|sponsor|advisor|director|co-?head)"
    r"(\s+(head|asst\.?|assistant|varsity|jv|coach|sponsor|advisor|director|\d+(\.\d+)?))*$",
    re.I,
)
_HEADING = re.compile(r"^[A-Za-z][A-Za-z/&'.\- ]{2,40}$")


def find_tables(lines: list[Line], page: int) -> list[StipendTable]:
    """Runs of stipend rows on a page; a run may skip up to two non-row lines (section titles).
    A short heading line ("Football") names the rows under it that only give a role ("Head",
    "Asst."): those become "Football Head", "Football Asst."."""
    tables: list[StipendTable] = []
    run: list[StipendRow] = []
    gap = 0
    heading = ""
    for i, line in enumerate(lines):
        row = parse_row(line, i) if line.words else None
        if row is not None:
            if heading and _ROLE_ONLY.match(row.label):
                row.label = f"{heading} {row.label}"
            run.append(row)
            gap = 0
            continue
        text = line.text.strip() if line.words else ""
        if text and _HEADING.match(text) and len(text.split()) <= 4:
            heading = re.sub(r"\s+", " ", text)
        if line.words:
            gap += 1
        if run and gap > 2:
            tables.append(StipendTable(page, run))
            run, gap = [], 0
    if run:
        tables.append(StipendTable(page, run))
    return [t for t in tables if len(t.rows) >= MIN_ROWS]


def build(table: StipendTable, lines: list[Line], reader: str) -> StipendTable | None:
    """Columns from the amounts' right edges; headers from the lines just above the first row."""
    edges = [a.x1 for r in table.rows for a in r.amounts]
    columns = _cluster(edges, COLUMN_GAP[reader])
    if len(columns) > 8:
        return None
    grid: list[list[float | None]] = []
    for r in table.rows:
        cells: list[float | None] = [None] * len(columns)
        for a in r.amounts:
            k = min(range(len(columns)), key=lambda j: abs(columns[j] - a.x1))
            if cells[k] is not None:
                return None  # two amounts in one column: the columns are not clear
            cells[k] = a.value
        grid.append(cells)
    first = table.rows[0].line_index
    header = lines[max(0, first - HEADER_REACH) : first]
    spans = []
    for k, edge in enumerate(columns):
        xs = [a.x0 for r in table.rows for a in r.amounts if abs(a.x1 - edge) <= COLUMN_GAP[reader]]
        spans.append((min(xs) - COLUMN_GAP[reader], edge + COLUMN_GAP[reader]))
        del k
    labels = []
    for lo, hi in spans:
        words = [w.text for ln in header for w in ln.words if w.x1 > lo and w.x0 < hi]
        labels.append(" ".join(words).strip())
    if len(columns) == 1:
        labels = [labels[0] or "Amount"]
    elif not all(labels) or len(set(labels)) < len(labels):
        labels = [f"Column {k + 1}" for k in range(len(columns))]
    table.columns = labels
    table.grid = grid
    table.context = "\n".join(ln.text for ln in lines[max(0, first - 8) : first])
    return table


_RUNNING_HEADER = re.compile(
    r"school district|\bISD\b|\bCISD\b|public schools|unified|compensation (plan|manual)|"
    r"salary (schedule|handbook)|^page \d+",
    re.IGNORECASE,
)


def title_of(context: str) -> str:
    """Lines printed above the table, without its column header line: "Campus Stipends — Dawson
    High School". At most three lines, each squeezed to single spaces."""
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in context.split("\n")]
    lines = [ln for ln in lines if _LETTER.search(ln)]
    lines = lines[-4:-1] if len(lines) > 1 else lines
    # The running header of the document (district name, plan name) says nothing about the table.
    lines = [ln for ln in lines if not _RUNNING_HEADER.search(ln)]
    return " — ".join(lines)[:200]


def to_answer(
    table: StipendTable | None, page_text: str, reader: str, doc_year: str | None = None
) -> dict[str, Any]:
    if table is None:
        return {"reader": reader, "rows": []}
    years = (
        school_years(table.context) or school_years(page_text) or ([doc_year] if doc_year else [])
    )
    return {
        "title": title_of(table.context),
        "reader": reader,
        "page": table.page,
        "school_year": years[0] if years else None,
        "columns": table.columns,
        "rows": [
            {"label": r.label, "amounts": g} for r, g in zip(table.rows, table.grid, strict=True)
        ],
    }


def read_pages(pages: list[list[Line]], wanted: list[int], reader: str) -> list[dict[str, Any]]:
    out = []
    doc_year = document_year(pages)
    for p in wanted:
        if not 1 <= p <= len(pages):
            continue
        lines = pages[p - 1]
        text = "\n".join(ln.text for ln in lines)
        for t in find_tables(lines, p):
            built = build(t, lines, reader)
            if built is not None:
                out.append(to_answer(built, text, reader, doc_year))
    return out


def document_year(pages: list[list[Line]]) -> str | None:
    """The school year the document is for, when a table's page does not print one: the first
    year on the first three pages (the cover), else the year printed on the most pages."""
    texts = ["\n".join(ln.text for ln in lines) for lines in pages]
    for text in texts[:3]:
        years = school_years(text)
        if years:
            return years[0]
    counts: dict[str, int] = {}
    for text in texts:
        for y in set(school_years(text)):
            counts[y] = counts.get(y, 0) + 1
    return max(counts, key=lambda y: (counts[y], y)) if counts else None


def read_document(
    path: Path, pages: list[int]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Both readers' tables on the given pages of a text PDF."""
    return (
        read_pages(layout_lines(path), pages, READERS[0]),
        read_pages(plumber_lines(path), pages, READERS[1]),
    )


def _key(answer: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(
        (re.sub(r"\s+", " ", r["label"]).lower(), tuple(r["amounts"])) for r in answer["rows"]
    )


def agreed(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tables both readers read the same, rows and amounts (column labels may differ)."""
    keys = {(x["page"], _key(x)) for x in b}
    return [x for x in a if (x["page"], _key(x)) in keys]


_GENERIC_COLUMN = re.compile(r"^Column \d+$")
_MONEY_IN = re.compile(r"\$\s*\d|\d[\d,]*\.\d\d\b")


_FOOTER = re.compile(
    r"\b(board approved|approved|revised|effective|adopted|updated)\b|^page\b|"
    r"\b(january|february|march|april|may|june|july|august|september|october|november|"
    r"december)\s+\d{1,2},?$",
    re.I,
)
_FRAGMENT = re.compile(r"\b(are|is|will|shall|must|may be|be paid|per the)\b", re.I)
_HEADER_WORDS = re.compile(
    r"\b(amount|position|assignment|stipend type|number|rate|activity|description)\b", re.I
)


def _title_part(part: str) -> bool:
    """A heading, not prose or a column header: starts with a capital or digit, no amount,
    no column-header words, does not end a sentence, at most ten words."""
    part = part.strip()
    return bool(
        part
        and (part[0].isupper() or part[0].isdigit())
        and not _MONEY_IN.search(part)
        and not _HEADER_WORDS.search(part)
        and not part.endswith(".")
        and len(part.split()) <= 10
    )


def clean(answer: dict[str, Any]) -> dict[str, Any]:
    """Tidy one agreed table before the checks: columns no row fills are dropped (a stray "$" or
    a percentage printed apart), a lone column is "Amount", labels lose a trailing "$", and a
    column header or title line that holds an amount (a data row read as a header) is dropped."""
    rows = [
        {**r, "label": re.sub(r"[\s$]+$", "", r["label"])}
        for r in answer["rows"]
        if not _FOOTER.search(r["label"])
    ]
    # Sentences and the wrapped tail of a label read as rows: "Teachers are compensated 187".
    fragments = [r for r in rows if _FRAGMENT.search(r["label"]) or not r["label"][:1].isalnum()
                 or r["label"][:1].islower()]  # fmt: skip
    rows = [r for r in rows if r not in fragments]
    lo = STIPEND_RANGE[0]
    small = [r for r in rows if any(v is not None and v < lo for v in r["amounts"])]
    if small and len(small) <= 0.25 * len(rows):
        # Per-game or hourly rates printed among season stipends: left out, the rest kept.
        rows = [r for r in rows if r not in small]
    cols = list(answer["columns"])
    keep = [j for j in range(len(cols)) if any(r["amounts"][j] is not None for r in rows)]
    cols = [cols[j] for j in keep]
    rows = [{**r, "amounts": [r["amounts"][j] for j in keep]} for r in rows]
    unnamed = all(_GENERIC_COLUMN.match(c) or _MONEY_IN.search(c) for c in cols)
    if (
        len(cols) > 1
        and unnamed
        and all(sum(v is not None for v in r["amounts"]) == 1 for r in rows)
    ):
        # One amount per row, landing in different columns: the "$" or a cent part printed apart.
        cols = ["Amount"]
        rows = [{**r, "amounts": [next(v for v in r["amounts"] if v is not None)]} for r in rows]
    if len(cols) == 1:
        cols = ["Amount"]
    parts = [p for p in answer.get("title", "").split(" — ") if _title_part(p)]
    title = " — ".join(parts)
    return {**answer, "columns": cols, "rows": rows, "title": title, "dropped": len(fragments)}


_DUTY_RE = re.compile(
    r"\b(sponsor|advisor|adviser|club|coordinator|department chair|grade level chair|"
    r"student council|national honor society|mentor|newspaper|academic decathlon|"
    r"science fair|spelling bee|math|chess|esports|orchestra|theat(?:er|re)|speech|"
    r"forensics|scholastic|quiz bowl|destination imagination|ffa|fbla|deca|hosa|skills ?usa)",
    re.I,
)


def check(answer: dict[str, Any]) -> list[str]:
    """Reasons a stipend table is not published; empty when it passes."""
    problems = []
    rows = answer["rows"]
    if answer.get("dropped", 0) > 0.2 * (len(rows) + answer.get("dropped", 0)):
        problems.append("nhiều dòng là câu văn hoặc nhãn bị ngắt dòng")
    if len(rows) < MIN_ROWS:
        problems.append(f"chỉ có {len(rows)} hàng")
    acts = {m.group(1).lower() for r in rows for m in _ACTIVITY_RE.finditer(r["label"])}
    acts |= {m.group(1).lower() for r in rows for m in _DUTY_RE.finditer(r["label"])}
    if len(acts) < 2:
        problems.append("ít hơn 2 môn hoặc hoạt động")
    lo, hi = STIPEND_RANGE
    bad = [v for r in rows for v in r["amounts"] if v is not None and not lo <= v <= hi]
    if bad:
        problems.append(f"số tiền ngoài khoảng ${lo:,}–${hi:,}: {bad[:3]}")
    if not answer.get("school_year"):
        problems.append("không thấy năm học")
    cols = answer["columns"]
    if len(cols) > 1 and any(_GENERIC_COLUMN.match(c) or _MONEY_IN.search(c) for c in cols):
        problems.append("nhiều cột nhưng không đọc được tiêu đề cột")
    if any(all(v is None for v in r["amounts"]) for r in rows):
        problems.append("có hàng không có số tiền")
    cells = [v for r in rows for v in r["amounts"]]
    if cells and sum(v is not None for v in cells) < 0.9 * len(cells):
        problems.append("bảng nhiều cột thiếu quá 10% ô")
    labels = [re.sub(r"\W+", " ", r["label"]).strip().lower() for r in rows]
    if rows and len(set(labels)) < 0.8 * len(labels):
        problems.append("nhiều hàng trùng tên (thiếu tên môn)")
    if any(_PERCENT.search(r["label"]) for r in rows):
        problems.append("phụ cấp tính theo phần trăm lương")
    return problems


_PERCENT = re.compile(r"\d\s*%")
