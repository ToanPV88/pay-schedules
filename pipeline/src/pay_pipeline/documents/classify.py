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
    r"doctorate|ph\.?d)\b",
    re.I,
)
TEACHER_RE = re.compile(
    r"\b(teachers?|certificated|certified|instructional|licensed|faculty)\b", re.I
)
NEGATIVE_RE = re.compile(
    r"\b(classified|administrat\w*|principals?|custodi\w*|bus drivers?|food service|"
    r"paraprofessional|substitutes?|hourly|confidential|supervisory|management)\b",
    re.I,
)
YEAR_PATTERNS = (
    re.compile(r"\b(20\d\d)\s*[-–—/]\s*(20\d\d)\b"),
    re.compile(r"\b(20\d\d)\s*[-–—/]\s*(\d\d)\b"),
    re.compile(r"\bFY\s*-?\s*(20)?(\d\d)\b", re.I),
    re.compile(r"\b\d{1,2}/\d{1,2}/(20\d\d)\s*[-–—]\s*\d{1,2}/\d{1,2}/(20\d\d)\b"),
)
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


def detect_kind(data: bytes) -> str:
    if data[:5] == b"%PDF-":
        return "pdf"
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


def document_pages(path: Path, kind: str) -> list[str]:
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
    for m in YEAR_PATTERNS[2].finditer(text):
        end = 2000 + int(m.group(2))
        found.add(end - 1)  # FY26 = 2025-26
    years = sorted((y for y in found if 2015 <= y <= 2030), reverse=True)
    return [f"{y}-{(y + 1) % 100:02d}" for y in years]


def score_page(text: str, page: int) -> PageScore:
    amounts = annual_amounts(text)
    has_step = bool(STEP_RE.search(text))
    has_lane = bool(LANE_RE.search(text))
    teacher = bool(TEACHER_RE.search(text))
    negative = len(NEGATIVE_RE.findall(text))
    score = (
        min(amounts, 80) / 10 + 2 * has_step + 2 * has_lane + 2 * teacher - min(negative, 6) * 0.5
    )
    is_schedule = amounts >= 12 and has_step and (has_lane or teacher)
    return PageScore(page, amounts, round(score, 2), is_schedule, teacher, negative)


def classify(path: Path, data: bytes | None = None) -> Classification:
    data = data if data is not None else path.read_bytes()
    kind = detect_kind(data)
    if kind not in ("pdf", "docx", "xlsx"):
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
