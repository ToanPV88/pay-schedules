"""Steps 4-6 of the PDF pipeline for one batch: Extract, Validate, Publish (as D1 SQL), report.

``extract_all`` calls the model for every district whose gather status is ``found`` (two
independent runs per document), within a cost budget, and checkpoints to ``extractions.json``
after every district. ``prepare`` turns gather + extraction results into an
:class:`ImportResult` (reusing the state-import SQL) plus the pipeline-state rows; ``pipeline_sql``
renders those rows.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

import httpx

from pay_pipeline.catalog.d1sql import batched_insert, quote
from pay_pipeline.pdf_pipeline import extract as ex
from pay_pipeline.pdf_pipeline.gather import DistrictWork, DocWork
from pay_pipeline.schedules.model import ScheduleDraft, school_year_from_start, school_year_start
from pay_pipeline.schedules.state_import import (
    CatalogDistrict,
    ImportResult,
    Prepared,
    PublishedSchedule,
    RunRecord,
    SourceDocument,
)
from pay_pipeline.schedules.validate import Issue, validate

CLASSIFIER = "heuristic@1"
RETRY_DAYS = {
    "no_website": 180, "unreachable": 30, "no_candidates": 90, "no_schedule": 90, "found": 0,
    "unchanged": 120, "published": 180, "error": 7, "review": None,
}  # fmt: skip


@dataclass
class Outcome:
    nces_id: str
    status: str
    detail: str
    cost_usd_micros: int = 0
    issue_codes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- extract


def extract_all(
    works: list[DistrictWork],
    work_dir: Path,
    api_key: str,
    *,
    budget_usd: float,
    models: tuple[str, str] = (ex.PRIMARY, ex.SECONDARY),
    workers: int = 4,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, dict[str, Any]]:
    path = work_dir / "extractions.json"
    results: dict[str, dict[str, Any]] = (
        json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    )
    spent = sum(r["cost_usd_micros"] for v in results.values() for r in v["runs"])
    lock = threading.Lock()
    todo = [w for w in works if w.status == "found" and w.chosen and w.nces_id not in results]

    def one(work: DistrictWork, client: httpx.Client) -> None:
        nonlocal spent
        with lock:
            if spent >= budget_usd * 1_000_000:
                return
        doc = next(d for d in work.docs if d.asset_name == work.chosen)
        content, pages = ex.build_content(
            work_dir / "docs" / doc.asset_name, doc.kind, doc.classification, work.name, work.state
        )
        runs = [ex.call_claude(client, api_key, m, content) for m in models]
        with lock:
            spent += sum(r.cost_usd_micros for r in runs)
            results[work.nces_id] = {"pages": pages, "runs": [asdict(r) for r in runs]}
            path.write_text(json.dumps(results, ensure_ascii=False) + "\n", encoding="utf-8")

    with httpx.Client(transport=transport) as client, ThreadPoolExecutor(workers) as pool:
        list(pool.map(lambda w: one(w, client), todo))
    return results


# ---------------------------------------------------------------- prepare


def _run(raw: dict[str, Any]) -> ex.ExtractionRun:
    return ex.ExtractionRun(**raw)


def _source(doc: DocWork, nces_id: str, release_tag: str) -> SourceDocument:
    return SourceDocument(
        asset_name=doc.asset_name,
        url=doc.url,
        sha256=doc.sha256,
        fetched_at=doc.fetched_at,
        mime=(doc.content_type or "").split(";")[0] or None,
        release_tag=release_tag,
        district_nces=nces_id,
    )


def _with_year(draft: ScheduleDraft, fallback: str | None) -> ScheduleDraft:
    try:
        school_year_start(draft.school_year)
        return draft
    except ValueError:
        return replace(draft, school_year=fallback or "")


def _clean_title(draft: ScheduleDraft) -> ScheduleDraft:
    """One teacher schedule per district and year: the printed title goes to the notes."""
    if not draft.title:
        return draft
    notes = f"Title: {draft.title}" + (f"\n{draft.notes}" if draft.notes else "")
    return replace(draft, title="", notes=notes)


def prepare(
    works: list[DistrictWork],
    extractions: dict[str, dict[str, Any]],
    catalog: dict[str, CatalogDistrict],
    published: list[PublishedSchedule],
    release_tag: str,
    today: dt.date,
) -> tuple[ImportResult, list[Outcome]]:
    previous = {(p.nces_id, p.school_year): p.start_cents for p in published if not p.title}
    latest: dict[str, str] = {}
    for p in published:
        if p.school_year > latest.get(p.nces_id, ""):
            latest[p.nces_id] = p.school_year
    sources: list[SourceDocument] = []
    runs: list[RunRecord] = []
    prepared: list[Prepared] = []
    outcomes: list[Outcome] = []
    for work in works:
        sources += [_source(d, work.nces_id, release_tag) for d in work.docs]
        if work.status != "found" or work.nces_id not in extractions:
            outcomes.append(Outcome(work.nces_id, work.status, work.detail))
            continue
        doc = next(d for d in work.docs if d.asset_name == work.chosen)
        record = extractions[work.nces_id]
        exruns = [_run(r) for r in record["runs"]]
        cost = sum(r.cost_usd_micros for r in exruns)
        runs += [
            RunRecord(doc.url, doc.sha256, r.model, r.prompt_version,
                      r.raw_output or json.dumps({"error": r.error}), r.cost_usd_micros)
            for r in exruns
        ]  # fmt: skip
        failed = [r for r in exruns if r.data() is None]
        if failed:
            detail = "; ".join(f"{r.model}: {r.error or 'JSON lỗi'}" for r in failed)[:500]
            outcomes.append(Outcome(work.nces_id, "error", detail, cost))
            continue
        data = [r.data() or {} for r in exruns]
        if not data[0].get("is_teacher_salary_schedule"):
            reason = str(data[0].get("reason") or "")[:300]
            outcomes.append(Outcome(work.nces_id, "no_schedule", f"Model: {reason}", cost))
            continue
        year_hint = doc.classification.get("best_year")
        try:
            draft = ex.to_draft(data[0], work.state, work.nces_id, work.name)
        except ex.ExtractionError as exc:
            outcomes.append(Outcome(work.nces_id, "error", f"{exruns[0].model}: {exc}", cost))
            continue
        draft = _clean_title(_with_year(draft, year_hint))
        issues: list[Issue] = []
        second: ScheduleDraft | None = None
        if not data[1].get("is_teacher_salary_schedule"):
            issues.append(Issue("double_extraction", f"{exruns[1].model} không thấy bảng lương"))
        else:
            try:
                second = _clean_title(
                    _with_year(ex.to_draft(data[1], work.state, work.nces_id, work.name), year_hint)
                )
            except ex.ExtractionError as exc:
                issues.append(Issue("double_extraction", f"{exruns[1].model}: {exc}"))
        try:
            start = school_year_start(draft.school_year)
        except ValueError:
            outcomes.append(
                Outcome(work.nces_id, "review", "Không đọc được năm học của bảng lương", cost,
                        ["school_year"])
            )  # fmt: skip
            continue
        prior = school_year_from_start(start - 1)
        issues += validate(
            draft,
            today=today,
            previous_start_cents=previous.get((work.nces_id, prior)),
            published_year=latest.get(work.nces_id),
            second_extraction=second,
        )
        if work.nces_id not in catalog:
            outcomes.append(Outcome(work.nces_id, "error", "Học khu không có trong danh mục", cost))
            continue
        item = Prepared(
            key=len(prepared) + 1,
            draft=draft,
            nces_id=work.nces_id,
            catalog_name=catalog[work.nces_id].name,
            source=_source(doc, work.nces_id, release_tag),
            importer=exruns[0].model,
            issues=issues,
            confidence=None,
        )
        prepared.append(item)
        outcomes.append(
            Outcome(work.nces_id, "published" if item.status == "published" else "review",
                    f"{draft.school_year}: " + ("; ".join(item.reasons) or "qua mọi kiểm tra"),
                    cost, sorted({i.code for i in issues}))
        )  # fmt: skip
    result = ImportResult(
        sources=sources, prepared=prepared, skipped=[], catalog=catalog,
        states=sorted({w.state for w in works}), runs=runs,
    )  # fmt: skip
    return result, outcomes


# ---------------------------------------------------------------- pipeline state SQL


def pipeline_sql(
    works: list[DistrictWork], outcomes: list[Outcome], run_key: str, now: dt.datetime
) -> list[str]:
    stamp = now.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    sql = [
        "DROP TABLE IF EXISTS _pp_cand",
        "CREATE TABLE _pp_cand (nces TEXT, url TEXT, found_on TEXT, anchor TEXT, method TEXT,"
        " score REAL)",
        "DROP TABLE IF EXISTS _pp_class",
        "CREATE TABLE _pp_class (url TEXT, sha256 TEXT, is_schedule INTEGER, scanned INTEGER,"
        " school_year TEXT, pages TEXT, score REAL, detail TEXT)",
        "DROP TABLE IF EXISTS _pp_status",
        "CREATE TABLE _pp_status (nces TEXT PRIMARY KEY, status TEXT, detail TEXT, next_run TEXT)",
    ]
    sql += batched_insert(
        "INSERT INTO _pp_cand (nces, url, found_on, anchor, method, score)",
        (
            (w.nces_id, c["url"], c["found_on"], c["anchor_text"][:300], c["method"], c["score"])
            for w in works
            for c in w.candidates
        ),
    )
    sql += batched_insert(
        "INSERT INTO _pp_class (url, sha256, is_schedule, scanned, school_year, pages, score,"
        " detail)",
        (
            (
                d.url, d.sha256, int(bool(d.classification.get("is_candidate"))),
                int(bool(d.classification.get("scanned"))), d.classification.get("best_year"),
                json.dumps(d.classification.get("schedule_pages") or []),
                d.classification.get("score"), str(d.classification.get("reason") or "")[:300],
            )
            for w in works
            for d in w.docs
        ),
    )  # fmt: skip
    rows = []
    for o in outcomes:
        days = RETRY_DAYS.get(o.status, 30)
        nxt = (
            None if days is None else (now + dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        rows.append((o.nces_id, o.status, o.detail[:1000], nxt))
    sql += batched_insert("INSERT INTO _pp_status (nces, status, detail, next_run)", rows)
    sql.append(
        "INSERT INTO document_candidates (district_id, url, found_on, anchor_text, method, score,"
        " first_seen_at, last_seen_at)"
        f" SELECT d.id, c.url, c.found_on, c.anchor, c.method, c.score, {quote(stamp)},"
        f" {quote(stamp)} FROM _pp_cand c JOIN districts d ON d.nces_id = c.nces WHERE true"
        " ON CONFLICT (district_id, url) DO UPDATE SET last_seen_at = excluded.last_seen_at,"
        " score = excluded.score, anchor_text = excluded.anchor_text"
    )
    sql.append(
        "INSERT INTO document_classifications (source_document_id, method, is_schedule, scanned,"
        " school_year, pages, score, detail, created_at)"
        f" SELECT s.id, {quote(CLASSIFIER)}, c.is_schedule, c.scanned, c.school_year, c.pages,"
        f" c.score, c.detail, {quote(stamp)} FROM _pp_class c"
        " JOIN source_documents s ON s.url = c.url AND s.sha256 = c.sha256 WHERE true"
        " ON CONFLICT (source_document_id, method) DO NOTHING"
    )
    sql.append(
        "INSERT INTO district_pipeline (district_id, status, detail, attempts, last_run_key,"
        " last_run_at, next_run_at)"
        f" SELECT d.id, s.status, s.detail, 1, {quote(run_key)}, {quote(stamp)}, s.next_run"
        " FROM _pp_status s JOIN districts d ON d.nces_id = s.nces WHERE true"
        " ON CONFLICT (district_id) DO UPDATE SET status = excluded.status,"
        " detail = excluded.detail, last_run_at = excluded.last_run_at,"
        " next_run_at = excluded.next_run_at,"
        " attempts = district_pipeline.attempts"
        " + (district_pipeline.last_run_key IS NOT excluded.last_run_key),"
        " last_run_key = excluded.last_run_key"
    )
    sql += ["DROP TABLE _pp_cand", "DROP TABLE _pp_class", "DROP TABLE _pp_status"]
    return sql


# ---------------------------------------------------------------- report


def render_report(
    works: list[DistrictWork], outcomes: list[Outcome], run_key: str, budget_usd: float
) -> str:
    by = Counter(o.status for o in outcomes)
    n = len(outcomes)
    extracted = [o for o in outcomes if o.cost_usd_micros]
    cost = sum(o.cost_usd_micros for o in outcomes) / 1_000_000
    found = sum(1 for w in works if w.status in ("found", "unchanged"))
    lines = [
        f"# Pipeline PDF: lần chạy {run_key}",
        "",
        f"- Học khu xử lý: {n} (ngân sách model {budget_usd:.2f} USD)",
        f"- Tìm thấy tài liệu giống bảng lương giáo viên: {found} ({found / n:.0%})" if n else "",
        f"- Đã trích bằng model: {len(extracted)}; chi phí {cost:.2f} USD"
        + (f", trung bình {cost / len(extracted):.3f} USD/học khu" if extracted else ""),
        f"- Published: {by['published']}; chờ xem tay: {by['review']}",
        "",
        "## Trạng thái",
        "",
        "| Trạng thái | Số học khu |",
        "|---|---:|",
    ]
    lines += [f"| {k} | {v} |" for k, v in sorted(by.items(), key=lambda kv: -kv[1])]
    codes = Counter(c for o in outcomes for c in o.issue_codes)
    lines += [
        "",
        "## Kiểm tra trượt (bảng chờ xem tay)",
        "",
        "| Kiểm tra | Số bảng |",
        "|---|---:|",
    ]
    lines += [f"| {k} | {v} |" for k, v in codes.most_common()] or ["| – | 0 |"]
    lines += ["", "## Từng học khu", ""]
    lines += [
        "| NCES | Học khu | Bang | Trạng thái | Chi phí | Chi tiết |",
        "|---|---|---|---|---:|---|",
    ]
    names = {w.nces_id: w for w in works}
    for o in outcomes:
        w = names[o.nces_id]
        detail = o.detail.replace("|", "/").replace("\n", " ")[:220]
        lines.append(
            f"| {o.nces_id} | {w.name} | {w.state} | {o.status} |"
            f" {o.cost_usd_micros / 1_000_000:.3f} | {detail} |"
        )
    return "\n".join(x for x in lines if x is not None) + "\n"
