"""Survey of downloaded district documents for extra-duty stipends and substitute pay (PLAN 11).

Công đoạn 11, đợt 1, bước 1: before writing a reader, count which documents the PDF pipeline has
already downloaded (Release ``docs-*``) carry a coaching / extra-duty stipend page or a substitute
pay page. Pages are only scored here; nothing is extracted and nothing goes to D1.

A page looks like a stipend schedule when it names at least two sports or activities and prints
several amounts in the stipend range. It looks like a substitute pay schedule when it says
"substitute" next to a daily or hourly rate in the substitute range.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pay_pipeline.documents.classify import document_pages

KINDS = {".pdf": "pdf", ".html": "html", ".htm": "html", ".docx": "docx", ".xlsx": "xlsx"}

ACTIVITIES = (
    "football", "basketball", "volleyball", "baseball", "softball", "soccer", "wrestling",
    "track", "cross country", "swim", "tennis", "golf", "cheer", "lacrosse", "hockey",
    "band", "choir", "drama", "debate", "yearbook", "robotics", "athletic director",
)  # fmt: skip
_ACTIVITY_RE = re.compile(r"\b(" + "|".join(re.escape(a) for a in ACTIVITIES) + r")", re.I)
_STIPEND_RE = re.compile(
    r"stipend|extra[\s-]duty|supplemental|co-?curricular|extra[\s-]curricular|coach", re.I
)
_SUB_RE = re.compile(r"substitute", re.I)
_RATE_RE = re.compile(
    r"daily|per\s+day|day\s+rate|half[\s-]day|full[\s-]day|hourly|per\s+hour", re.I
)
# Amounts printed as money: "$4,300", "$950", "4,300.00". A bare "950" is not counted.
_MONEY_RE = re.compile(
    r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?|\b(\d{1,3}(?:,\d{3})+)(?:\.\d{2})?\b"
)

STIPEND_RANGE = (50, 40_000)
SUB_RANGE = (40, 800)
MIN_STIPEND_AMOUNTS = 4
MIN_ACTIVITIES = 2


def amounts(text: str) -> list[int]:
    found = []
    for m in _MONEY_RE.finditer(text):
        raw = m.group(1) or m.group(2)
        found.append(int(raw.replace(",", "")))
    return found


def _in(values: Iterable[int], lo_hi: tuple[int, int]) -> int:
    lo, hi = lo_hi
    return sum(lo <= v <= hi for v in values)


def stipend_page(text: str) -> int:
    """Number of distinct activities on a stipend-looking page, or 0."""
    names = {m.group(1).lower() for m in _ACTIVITY_RE.finditer(text)}
    if len(names) < MIN_ACTIVITIES or not _STIPEND_RE.search(text):
        return 0
    if _in(amounts(text), STIPEND_RANGE) < MIN_STIPEND_AMOUNTS:
        return 0
    return len(names)


def substitute_page(text: str) -> bool:
    return bool(
        _SUB_RE.search(text) and _RATE_RE.search(text) and _in(amounts(text), SUB_RANGE) >= 1
    )


@dataclass
class DocSurvey:
    nces_id: str
    file: str
    url: str
    sha256: str
    pages: int
    scanned: bool
    stipend_pages: list[int] = field(default_factory=list)
    activities: int = 0
    substitute_pages: list[int] = field(default_factory=list)


def survey_file(path: Path, url: str = "", sha256: str = "") -> DocSurvey | None:
    kind = KINDS.get(path.suffix.lower())
    if kind is None:
        return None
    try:
        pages = document_pages(path, kind)
    except Exception:  # a broken file is reported as unreadable, not fatal
        pages = []
    nces = path.name.split("-", 1)[0]
    out = DocSurvey(nces, path.name, url, sha256, len(pages), not any(p.strip() for p in pages))
    for i, text in enumerate(pages, start=1):
        n = stipend_page(text)
        if n:
            out.stipend_pages.append(i)
            out.activities = max(out.activities, n)
        if substitute_page(text):
            out.substitute_pages.append(i)
    return out


def survey_dir(docs: Path, manifest: Path | None, seen: set[str]) -> list[DocSurvey]:
    """Survey every document file in ``docs`` not already in ``seen`` (by file name)."""
    meta: dict[str, dict[str, str]] = {}
    if manifest is not None and manifest.exists():
        for f in json.loads(manifest.read_text()).get("files", []):
            meta[f["name"]] = f
    results = []
    for path in sorted(docs.iterdir()):
        if path.name in seen or not path.is_file():
            continue
        seen.add(path.name)
        m = meta.get(path.name, {})
        r = survey_file(path, m.get("final_url") or m.get("url", ""), m.get("sha256", ""))
        if r is not None:
            results.append(r)
    return results


def write_jsonl(rows: Iterable[DocSurvey], out: Path) -> int:
    n = 0
    with out.open("a") as fh:
        for r in rows:
            fh.write(json.dumps(asdict(r)) + "\n")
            n += 1
    return n
