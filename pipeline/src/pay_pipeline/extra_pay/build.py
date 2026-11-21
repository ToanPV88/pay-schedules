"""Coaching / extra-duty stipend tables: read documents, choose, and build D1 SQL (PLAN 11).

``read_dir`` reads the stipend pages the survey found in one Release's documents with both
readers and keeps the tables they agree on. ``prepare`` picks, per district, the document whose
agreed tables pass every check and carry the school year in force, and turns each table into a
``ScheduleDraft`` of type ``extra_duty``: rows are positions (steps), columns are experience
levels (lanes) or one "Amount" column (no lane). Only tables that pass every check are imported,
and they are published: nothing goes to the review queue (the owner cannot review by hand, D-034).
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pay_pipeline.extra_pay import read as sr
from pay_pipeline.extra_pay.survey import survey_file
from pay_pipeline.pdf_pipeline.read import year_in_force
from pay_pipeline.schedules.model import Cell, Lane, ScheduleDraft, Step, school_year_start
from pay_pipeline.schedules.state_import import (
    CatalogDistrict,
    ImportResult,
    Prepared,
    RunRecord,
    SourceDocument,
)
from pay_pipeline.schedules.validate import current_school_year_start

SCHEDULE_TYPE = "extra_duty"
MAX_AGE_YEARS = 2
"""Oldest school year published, counted back from the current one (2024-25 in 2026-27)."""
EMPTY_NOTE = "Not printed in the document (N/A)"


@dataclass
class DocReading:
    nces_id: str
    asset_name: str
    url: str
    sha256: str
    fetched_at: str
    content_type: str | None
    release_tag: str
    stipend_pages: list[int]
    tables: list[dict[str, Any]] = field(default_factory=list)
    """Tables both readers agree on, each with ``problems`` (empty when it passes)."""
    disagreed: int = 0


def read_dir(docs: Path, manifest: Path, release_tag: str, seen: set[str]) -> list[DocReading]:
    files = {f["name"]: f for f in json.loads(manifest.read_text()).get("files", [])}
    out = []
    for path in sorted(docs.iterdir()):
        if path.name in seen or path.suffix.lower() != ".pdf":
            continue
        seen.add(path.name)
        s = survey_file(path)
        if s is None or s.scanned or not s.stipend_pages:
            continue
        meta = files.get(path.name, {})
        try:
            a, b = sr.read_document(path, s.stipend_pages)
        except Exception as exc:  # a broken file is skipped, not fatal
            print(f"bỏ qua {path.name}: {type(exc).__name__}: {exc}"[:300])
            continue
        agreed = [sr.clean(t) for t in sr.agreed(a, b)]
        tables = [{**t, "problems": sr.check(t)} for t in agreed]
        out.append(
            DocReading(
                nces_id=s.nces_id,
                asset_name=path.name,
                url=meta.get("final_url") or meta.get("url", ""),
                sha256=meta.get("sha256", ""),
                fetched_at=meta.get("fetched_at", ""),
                content_type=meta.get("content_type"),
                release_tag=release_tag,
                stipend_pages=s.stipend_pages,
                tables=tables,
                disagreed=max(len(a), len(b)) - len(agreed),
            )
        )
    return out


def write_readings(rows: Iterable[DocReading], out: Path) -> int:
    n = 0
    with out.open("a") as fh:
        for r in rows:
            fh.write(json.dumps(r.__dict__) + "\n")
            n += 1
    return n


def load_readings(paths: Iterable[Path]) -> list[DocReading]:
    seen: dict[str, DocReading] = {}
    for p in paths:
        for line in p.read_text().splitlines():
            if line.strip():
                r = DocReading(**json.loads(line))
                seen.setdefault(r.asset_name, r)
    return list(seen.values())


def _good(r: DocReading, today: dt.date) -> list[dict[str, Any]]:
    """Passing tables of the school year in force, duplicates (same rows) dropped."""
    now = current_school_year_start(today)
    # A future year (a multi-year contract's later column) is not the pay in force today.
    ok = [t for t in r.tables if not t["problems"] and school_year_start(t["school_year"]) <= now]
    if not ok:
        return []
    year = year_in_force({t["school_year"] for t in ok}, today)
    if school_year_start(year) < current_school_year_start(today) - MAX_AGE_YEARS:
        return []
    out, keys = [], set()
    for t in ok:
        k = (t["title"], sr._key(t))
        if t["school_year"] == year and k not in keys:
            keys.add(k)
            out.append(t)
    return out


def to_draft(t: dict[str, Any], state: str, nces_id: str, name: str) -> ScheduleDraft:
    single = len(t["columns"]) == 1
    lanes = [] if single else [Lane(c) for c in t["columns"]]
    steps = [Step(r["label"]) for r in t["rows"]]
    cells: dict[tuple[int, int | None], Cell] = {}
    for i, r in enumerate(t["rows"]):
        for j, v in enumerate(r["amounts"]):
            lane = None if single else j
            cells[(i, lane)] = Cell(round(v * 100)) if v is not None else Cell(None, EMPTY_NOTE)
    title = t["title"] or "Coaching and extra-duty stipends"
    return ScheduleDraft(
        state=state, state_district_id=nces_id, district_name=name,
        school_year=t["school_year"], lanes=lanes, steps=steps, cells=cells,
        schedule_type=SCHEDULE_TYPE, title=title, source_page=t["page"],
    )  # fmt: skip


@dataclass
class Outcome:
    nces_id: str
    status: str  # published | no_table | not_in_catalog
    detail: str


def prepare(
    readings: list[DocReading], catalog: dict[str, CatalogDistrict], today: dt.date
) -> tuple[ImportResult, list[Outcome]]:
    by_district: dict[str, list[DocReading]] = {}
    for r in readings:
        by_district.setdefault(r.nces_id, []).append(r)
    sources: list[SourceDocument] = []
    runs: list[RunRecord] = []
    prepared: list[Prepared] = []
    outcomes: list[Outcome] = []
    for nces, docs in sorted(by_district.items()):
        cat = catalog.get(nces)
        if cat is None or not cat.active:
            outcomes.append(Outcome(nces, "not_in_catalog", ""))
            continue
        scored = [(r, _good(r, today)) for r in docs]
        scored = [(r, g) for r, g in scored if g]
        if not scored:
            why = "; ".join(sorted({p for r in docs for t in r.tables for p in t["problems"]}))
            outcomes.append(Outcome(nces, "no_table", why[:300] or "hai bộ đọc không khớp"))
            continue
        # The latest school year wins; then the document with the most rows; then the newest.
        doc, tables = max(
            scored,
            key=lambda rg: (
                school_year_start(rg[1][0]["school_year"]),
                sum(len(t["rows"]) for t in rg[1]),
                rg[0].fetched_at,
            ),
        )
        source = SourceDocument(
            asset_name=doc.asset_name, url=doc.url, sha256=doc.sha256,
            fetched_at=doc.fetched_at, mime=(doc.content_type or "").split(";")[0] or None,
            release_tag=doc.release_tag, district_nces=nces,
        )  # fmt: skip
        sources.append(source)
        runs.append(
            RunRecord(doc.url, doc.sha256, sr.READERS[0], None,
                      json.dumps({"tables": tables})[:20000], 0)
        )  # fmt: skip
        titles: set[str] = set()
        for t in tables:
            draft = to_draft(t, cat.state, nces, cat.name)
            if draft.title in titles:  # two tables, one title: tell them apart by page
                draft.title = f"{draft.title} (page {t['page']})"
            titles.add(draft.title)
            prepared.append(
                Prepared(
                    key=len(prepared) + 1, draft=draft, nces_id=nces, catalog_name=cat.name,
                    source=source, importer=sr.READERS[0], issues=[], confidence=None,
                )
            )  # fmt: skip
        outcomes.append(
            Outcome(nces, "published", f"{len(tables)} bảng, {tables[0]['school_year']}, {doc.url}")
        )
    result = ImportResult(
        sources=sources, prepared=prepared, skipped=[], catalog=catalog,
        states=sorted({c.state for n, c in catalog.items() if n in by_district}), runs=runs,
    )  # fmt: skip
    return result, outcomes


def with_retire(sql: list[str]) -> list[str]:
    """A new reading replaces the district's earlier stipend tables, even those under a title no
    longer read: they are retired just before the staging tables are dropped."""
    newer = (
        "SELECT max(m.schedule_id) FROM _imp_map m JOIN schedules n ON n.id = m.schedule_id"
        " WHERE n.district_id = schedules.district_id AND n.status = 'published'"
    )
    retire = (
        f"UPDATE schedules SET status = 'superseded', superseded_by = ({newer})"
        f" WHERE schedule_type = '{SCHEDULE_TYPE}' AND status = 'published'"
        f" AND id NOT IN (SELECT schedule_id FROM _imp_map) AND ({newer}) IS NOT NULL"
    )
    at = next(i for i, q in enumerate(sql) if q.startswith("DROP TABLE _imp"))
    return [*sql[:at], retire, *sql[at:]]
