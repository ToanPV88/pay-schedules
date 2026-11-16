"""Classify (PLAN Công đoạn 5, bước 3) without a model: is this file a teacher salary schedule,
for which school year, and on which pages?

Text comes from ``pdftotext -layout`` (poppler) for PDF, the XML of a DOCX, or the cells of an
XLSX. Each page is scored: many annual-pay-sized amounts, step/experience words, lane/degree
words and teacher words push the score up; classified/administrator words push it down. A
scanned PDF (almost no text) is marked so extraction can send page images to the model.
"""

from __future__ import annotations

import re
import subprocess
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

MONEY_RE = re.compile(r"(?<![\d.])\$?\s?(\d{2,3}),?(\d{3})(?:\.\d{2})?(?![\d,])")
STEP_RE = re.compile(r"\b(step|steps|years?|yrs|experience|level)\b", re.I)
LANE_RE = re.compile(
    r"\b(B\.?A\.?|M\.?A\.?|bachelor'?s?|master'?s?|class\s+[IVX\dA-H]|column|rank|lane|"
    r"doctorate|ph\.?d)\b"
    # Lane headings with credits after the degree: B+10, M+20 (Goddard), BS+8G (Carl Junction)
    r"|\b[BM]\.?(?:[AS]\.?)?\s?\+\s?\d{1,2}",
    re.I,
)
SALARY_RE = re.compile(r"\b(salar(?:y|ies)|pay\s+scales?|compensation)\b", re.I)
TEACHER_RE = re.compile(
    r"\b(teachers?|certificated|certified|instructional|licensed|faculty)\b", re.I
)
NEGATIVE_RE = re.compile(
    r"\b(classified|administrat\w*|principals?|custodi\w*|bus drivers?|food service|"
    r"paraprofessional|substitutes?|hourly|confidential|supervisory|management|"
    r"(?:instructional|teacher|classroom)\s+(?:assistants?|aides?|support)|assistants?|aides?|"
    r"attendants?|technicians?|secretar\w*|support\s+(?:staff|scale|personnel))\b",
    re.I,
)
YEAR_PATTERNS = (
    re.compile(r"\b(20\d\d)\s*[-‐‑‒–—/]\s*(20\d\d)\b"),
    re.compile(r"\b(20\d\d)\s*[-‐‑‒–—/]\s*(\d\d)\b"),
    re.compile(r"\bFY\s*-?\s*(20)?(\d\d)\b(?!\s*[-‐‑‒–—/]\s*\d)", re.I),
    re.compile(r"\b\d{1,2}/\d{1,2}/(20\d\d)\s*[-‐‑‒–—]\s*\d{1,2}/\d{1,2}/(20\d\d)\b"),
    re.compile(r"\bFY\s*-?\s*(\d\d)\s*[-‐‑‒–—/]\s*(\d\d)\b", re.I),  # FY26-27 = 2026-27
)
# Letter-spaced headings ("2 0 2 5 – 2026"): join the digits before matching.
_SPACED_YEAR = re.compile(r"\b2 0 (\d) (\d)\b")
MIN_TEXT_CHARS = 200


@dataclass(frozen=True)
class PageScore:
    page: int  # 1-based
    amounts: int
    score: float
    is_schedule: bool
    teacher: bool
    negative: int


@dataclass
class Classification:
    kind: str  # pdf | docx | xlsx | other
    pages_total: int
    scanned: bool
    schedule_pages: list[int] = field(default_factory=list)
    school_years: list[str] = field(default_factory=list)
    best_year: str | None = None
    score: float = 0.0
    is_candidate: bool = False
    reason: str = ""


_TABLE = re.compile(r"<table\b.*?</table>", re.I | re.S)
_ROW = re.compile(r"<tr\b.*?(?:</tr>|(?=<tr\b)|$)", re.I | re.S)
_CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)(?=<t[dh]\b|</tr>|$)", re.I | re.S)


def html_table_rows(table_html: str) -> list[list[str]]:
    """Cell texts of an HTML table, row by row (D-046)."""
    import html as _html

    rows = []
    for tr in _ROW.findall(table_html):
        cells = []
        for cell in _CELL.findall(tr):
            text = re.sub(r"<[^>]+>", " ", cell)
            cells.append(" ".join(_html.unescape(text).split()))
        if any(cells):
            rows.append(cells)
    return rows


def html_tables(html_text: str) -> list[str]:
    """The ``<table>`` blocks of a page, innermost content kept as written."""
    return _TABLE.findall(html_text)


def detect_kind(data: bytes) -> str:
    if data[:5] == b"%PDF-":
        return "pdf"
    head = data[:300].lstrip().lower()
    if head.startswith((b"<!doctype html", b"<html", b"<table", b"<meta", b"<title")):
        return "html"
    if data[:2] == b"PK":
        head = data[:4000]
        if b"word/" in head:
            return "docx"
        if b"xl/" in head:
            return "xlsx"
        return "zip"
    return "other"


def pdf_pages(path: Path) -> list[str]:
    result = subprocess.run(  # noqa: S603 - fixed tool, path argument
        ["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],  # noqa: S607
        capture_output=True,
        timeout=120,
        check=False,
    )
    text = result.stdout.decode("utf-8", errors="replace")
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


def docx_pages(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    xml = re.sub(r"</w:p>|</w:tr>", "\n", xml)
    xml = re.sub(r"</w:tc>", "  ", xml)
    return [re.sub(r"<[^>]+>", "", xml)]


def xlsx_pages(path: Path) -> list[str]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        pages = []
        for ws in wb.worksheets:
            rows = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i > 400:
                    break
                rows.append("  ".join("" if v is None else str(v) for v in row))
            pages.append(f"[sheet {ws.title}]\n" + "\n".join(rows))
        return pages
    finally:
        wb.close()


def html_pages(path: Path) -> list[str]:
    """One page per HTML table: its rows, cells separated by two spaces."""
    text = path.read_bytes().decode("utf-8", errors="replace")
    title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    head = (" ".join(title.group(1).split()) + "\n") if title else ""
    pages = []
    for table in html_tables(text):
        pages.append(head + "\n".join("  ".join(row) for row in html_table_rows(table)))
    return pages or [head]


def document_pages(path: Path, kind: str) -> list[str]:
    if kind == "html":
        return html_pages(path)
    if kind == "pdf":
        return pdf_pages(path)
    if kind == "docx":
        return docx_pages(path)
    if kind == "xlsx":
        return xlsx_pages(path)
    return []


def annual_amounts(text: str) -> int:
    count = 0
    for m in MONEY_RE.finditer(text):
        value = int(m.group(1) + m.group(2))
        if 15_000 <= value <= 300_000:
            count += 1
    return count


def school_years(text: str) -> list[str]:
    """School years written in the text, as 'YYYY-YY', most recent first."""
    found: set[int] = set()
    text = _SPACED_YEAR.sub(r"20\1\2", text)
    text = re.sub(r"\b(20\d\d)_(20\d\d)\b", r"\1-\2", text)  # "School Year 2026_2027"
    for m in YEAR_PATTERNS[0].finditer(text):
        a, b = int(m.group(1)), int(m.group(2))
        if b == a + 1:
            found.add(a)
    for m in YEAR_PATTERNS[1].finditer(text):
        a, b = int(m.group(1)), int(m.group(2))
        if b == (a + 1) % 100:
            found.add(a)
    for m in YEAR_PATTERNS[3].finditer(text):
        a, b = int(m.group(1)), int(m.group(2))
        if b == a + 1:
            found.add(a)
    for m in YEAR_PATTERNS[4].finditer(text):
        a, b = int(m.group(1)), int(m.group(2))
        if b == (a + 1) % 100:
            found.add(2000 + a)
    for m in YEAR_PATTERNS[2].finditer(text):
        end = 2000 + int(m.group(2))
        found.add(end - 1)  # FY26 = 2025-26
    for m in _DATE_RANGE.finditer(text):
        # "July 1, 2026 to June 30, 2027" (Anne Arundel), "August 10, 2026 – June 7, 2027"
        a, b = int(m.group(1)), int(m.group(2))
        if b == a + 1:
            found.add(a)
    for m in _FY_ENDING.finditer(text):
        found.add(int(m.group(1)) - 1)  # "fiscal year ending June 30, 2026" = 2025-26
    if not found:
        for m in _FISCAL_YEAR.finditer(text):
            found.add(int(m.group(1)) - 1)  # "Fiscal Year 2027" = 2026-27
        for m in _EFFECTIVE_NUMERIC.finditer(text):
            month, year = int(m.group(1)), int(m.group(2))
            year += 2000 if year < 100 else 0
            if 1 <= month <= 12:
                found.add(year - (month < 7))  # "Effective 08/23/26" = 2026-27
    if not found:
        # "Effective August 1, 2026": no school year written, only the start date (Knox County)
        for m in _EFFECTIVE.finditer(text):
            month = _MONTHS.index(m.group(1)[:3].lower()) + 1
            found.add(int(m.group(2)) - (month < 7))
    years = sorted((y for y in found if 2015 <= y <= 2030), reverse=True)
    return [f"{y}-{(y + 1) % 100:02d}" for y in years]


_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_MONTH_DAY = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+"
_DATE_RANGE = re.compile(
    _MONTH_DAY + r"(20\d\d)\s*(?:[-‐‑–—]|to|through|thru)\s*" + _MONTH_DAY + r"(20\d\d)\b", re.I
)
_FY_ENDING = re.compile(r"\bfiscal\s+year\s+ending:?\s+(?:june|jun\.?)\s+30,?\s+(20\d\d)\b", re.I)
_FISCAL_YEAR = re.compile(r"\bfiscal\s+year\s+(20\d\d)\b(?!\s*[-‐‑–—/_]\s*\d)", re.I)
_EFFECTIVE_NUMERIC = re.compile(r"\beffective:?\s+(\d{1,2})/\d{1,2}/(\d{2}|20\d\d)\b", re.I)
_EFFECTIVE = re.compile(
    r"\beffective:?\s+(?:on\s+)?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
    r"\s+\d{1,2},?\s+(20\d\d)\b",
    re.I,
)


def score_page(text: str, page: int) -> PageScore:
    amounts = annual_amounts(text)
    has_step = bool(STEP_RE.search(text))
    has_lane = bool(LANE_RE.search(text))
    teacher = bool(TEACHER_RE.search(text))
    negative = len(NEGATIVE_RE.findall(text))
    score = (
        min(amounts, 80) / 10 + 2 * has_step + 2 * has_lane + 2 * teacher - min(negative, 6) * 0.5
    )
    salary = bool(SALARY_RE.search(text))
    is_schedule = (
        (amounts >= 12 and has_step and (has_lane or teacher))
        # Rows numbered without the word "step" (Muhlenberg: "From Top 16 … 1"; Carroll: rows A-Z)
        or (amounts >= 40 and salary and (has_lane or teacher))
        # A short single-lane schedule (Tyler ISD: 11 rows of years of experience)
        or (amounts >= 8 and has_step and teacher and salary)
    )
    return PageScore(page, amounts, round(score, 2), is_schedule, teacher, negative)


def classify(path: Path, data: bytes | None = None) -> Classification:
    data = data if data is not None else path.read_bytes()
    kind = detect_kind(data)
    if kind not in ("pdf", "docx", "xlsx", "html"):
        return Classification(kind, 0, False, reason="Không phải PDF/DOCX/XLSX")
    try:
        pages = document_pages(path, kind)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.SubprocessError) as exc:
        return Classification(kind, 0, False, reason=f"Không đọc được tệp: {exc}"[:200])
    total_chars = sum(len(p.strip()) for p in pages)
    scanned = kind == "pdf" and total_chars < MIN_TEXT_CHARS * max(1, len(pages)) / 4
    result = Classification(kind, len(pages), scanned)
    if scanned:
        result.is_candidate = True
        result.reason = "PDF dạng ảnh quét: cần model đọc ảnh"
        return result
    scores = [score_page(text, i + 1) for i, text in enumerate(pages)]
    schedule = [s for s in scores if s.is_schedule]
    teacher_pages = [s for s in schedule if s.teacher and s.negative <= 2] or schedule
    result.schedule_pages = [s.page for s in sorted(teacher_pages, key=lambda s: -s.score)[:4]]
    result.score = max((s.score for s in teacher_pages), default=0.0)
    years_text = "\n".join(pages[p - 1] for p in result.schedule_pages) or "\n".join(pages[:2])
    result.school_years = school_years(years_text) or school_years("\n".join(pages[:3]))
    result.best_year = result.school_years[0] if result.school_years else None
    result.is_candidate = bool(result.schedule_pages)
    result.reason = (
        f"{len(schedule)} trang có dạng bảng lương" if schedule else "Không thấy trang bảng lương"
    )
    return result


def salary_table_page(data: bytes) -> bytes | None:
    """The salary tables of a web page as a small, stable HTML document, or None (D-046).

    Only tables that look like a salary schedule page (score_page) are kept, with the page title,
    so the document's hash does not change with the page's menus, scripts and timestamps.
    """
    text = data.decode("utf-8", errors="replace")
    keep = []
    for table in html_tables(text):
        rows = html_table_rows(table)
        if score_page("\n".join("  ".join(r) for r in rows), 1).is_schedule:
            keep.append(table)
    if not keep:
        return None
    title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    head = f"<title>{title.group(1).strip()}</title>" if title else ""
    body = "\n".join(keep)
    return f"<!doctype html><html><head>{head}</head><body>\n{body}\n</body></html>".encode()
