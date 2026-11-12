"""PDF pipeline end to end, offline: a fake district website (httpx.MockTransport), a small
hand-built PDF, a fake Claude API, and the generated SQL run on the real D1 schema in SQLite.

Names contain "Test" and hosts use example.invalid.
"""

# ruff: noqa: E501

from __future__ import annotations

import datetime as dt
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

import httpx
import pytest

from pay_pipeline.acquisition.policy import CrawlPolicy
from pay_pipeline.acquisition.shared import SharedThrottle
from pay_pipeline.catalog.d1sql import render_sql
from pay_pipeline.discover.crawl import (
    Link,
    extract_links,
    is_document_url,
    same_site,
    score_document,
)
from pay_pipeline.documents.classify import classify, school_years
from pay_pipeline.pdf_pipeline import extract as ex
from pay_pipeline.pdf_pipeline.gather import QueueItem, gather, load_work
from pay_pipeline.pdf_pipeline.run import extract_all, pipeline_sql, prepare, render_report
from pay_pipeline.schedules.d1sql import schedules_sql
from pay_pipeline.schedules.state_import import CatalogDistrict

REPO = Path(__file__).resolve().parents[2]
MIGRATIONS = sorted((REPO / "packages" / "db" / "migrations").glob("*.sql"))
UA = "pay-schedules-test/0.1 (+https://example.invalid)"
NOW = dt.datetime(2026, 11, 12, 8, 0, tzinfo=dt.UTC)
HAS_PDFTOTEXT = shutil.which("pdftotext") is not None

SCHEDULE_LINES = [
    "Test Unified School District",
    "2025-2026 Certificated Teacher Salary Schedule",
    "Step      BA        BA+30      MA",
] + [
    f"{s:>4}   {50000 + 1500 * s:,}   {53000 + 1600 * s:,}   {56000 + 1700 * s:,}"
    for s in range(1, 16)
]


def make_pdf(lines: list[str]) -> bytes:
    """A one-page PDF with the given text lines (Helvetica), valid enough for pdftotext/pypdf."""
    text = (
        "BT /F1 10 Tf 40 760 Td 12 TL "
        + " ".join(
            "(" + ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") '"
            for ln in lines
        )
        + " ET"
    )
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(text)} >>\nstream\n{text}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out


SITE = "https://test-usd.example.invalid"
PDF = make_pdf(SCHEDULE_LINES)
ROUTES: dict[str, httpx.Response] = {
    f"{SITE}/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /private/\n"),
    f"{SITE}/": httpx.Response(200, headers={"content-type": "text/html"}, html=(
        '<a href="/departments/human-resources">Human Resources</a> <a href="/menu">Lunch menu</a>'
        ' <a href="/private/salary">Private</a>')),
    f"{SITE}/departments/human-resources": httpx.Response(200, headers={"content-type": "text/html"}, html=(
        '<a href="/files/2025-26%20Certificated%20Salary%20Schedule.pdf">2025-26 Teacher Salary Schedule</a>'
        ' <a href="/files/classified.pdf">Classified Salary Schedule</a>')),
    f"{SITE}/files/2025-26%20Certificated%20Salary%20Schedule.pdf": httpx.Response(
        200, headers={"content-type": "application/pdf"}, content=PDF),
    f"{SITE}/files/classified.pdf": httpx.Response(200, headers={"content-type": "application/pdf"},
                                                   content=make_pdf(["Classified hourly rates", "Grade 1  18.50  19.25"])),
    f"{SITE}/sitemap.xml": httpx.Response(404),
    "https://empty.example.invalid/robots.txt": httpx.Response(404),
    "https://empty.example.invalid/": httpx.Response(200, headers={"content-type": "text/html"}, html="<p>Welcome</p>"),
    "https://empty.example.invalid/sitemap.xml": httpx.Response(404),
}  # fmt: skip


def site_transport(seen: list[str] | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if seen is not None:
            seen.append(url)
        return ROUTES.get(url, httpx.Response(404))

    return httpx.MockTransport(handler)


QUEUE = [
    QueueItem(1, "0600001", "Test Unified", "CA", f"{SITE}/", 9000),
    QueueItem(2, "0600002", "Test Empty Elementary", "CA", "https://empty.example.invalid/", 500),
    QueueItem(3, "0600003", "Test No Website", "CA", None, 100),
]


def tool_answer(
    lines: list[str] | None = None, *, teacher: bool = True, year: str | None = "2025-26"
) -> dict[str, Any]:
    steps = list(range(1, 16))
    return {
        "is_teacher_salary_schedule": teacher,
        "reason": "Teacher schedule" if teacher else "Not a teacher schedule",
        "school_year": year,
        "title": "2025-2026 Certificated Teacher Salary Schedule",
        "contract_days": 185,
        "pay_basis": "annual",
        "lanes": ["BA", "BA+30", "MA"] if teacher else [],
        "steps": [{"label": str(s), "years_experience": None} for s in steps] if teacher else [],
        "cells": [[50000 + 1500 * s, 53000 + 1600 * s, 56000 + 1700 * s] for s in steps]
        if teacher
        else [],
        "stipends": [{"name": "Doctorate", "amount": 2000, "amount_text": None, "condition": None}],
        "notes": None,
        "source_pages": [1],
        "other_schedules": [],
    }


def claude_transport(
    answers: dict[str, dict[str, Any]], calls: list[dict[str, Any]]
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append({"model": body["model"], "headers": dict(request.headers)})
        answer = answers[body["model"]]
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "tool_use", "name": "record_salary_schedule", "input": answer}
                ],
                "usage": {"input_tokens": 3000, "output_tokens": 1500},
            },
        )

    return httpx.MockTransport(handler)


def fresh_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys = ON")
    for path in MIGRATIONS:
        db.executescript(path.read_text(encoding="utf-8"))
    db.execute("INSERT INTO states (code, name, slug) VALUES ('CA', 'California', 'california')")
    for item in QUEUE:
        db.execute(
            "INSERT INTO districts (id, nces_id, name, slug, state, website) VALUES (?, ?, ?, ?, ?, ?)",
            (item.district_id, item.nces_id, item.name, item.nces_id, item.state, item.website),
        )
    return db


CATALOG = {i.nces_id: CatalogDistrict(i.nces_id, i.state, i.name, True) for i in QUEUE}


# ---------------------------------------------------------------- units


class TestDiscoverUnits:
    def test_links_and_scores(self) -> None:
        links = extract_links(
            '<base href="/a/"><a href="x.pdf">Salary <b>Schedule</b></a><a href="mailto:x@y">m</a>'
            '<a href="#top">t</a><iframe src="https://docs.google.com/d/1"></iframe>',
            f"{SITE}/p",
        )
        assert [link.url for link in links] == [f"{SITE}/a/x.pdf", "https://docs.google.com/d/1"]
        assert links[0].text == "Salary Schedule"
        teacher = score_document(Link(f"{SITE}/2025-26-certificated-salary-schedule.pdf", ""))
        classified = score_document(Link(f"{SITE}/classified-salary-schedule.pdf", ""))
        assert teacher > classified > 0
        assert score_document(Link(f"{SITE}/lunch-menu.pdf", "Menu")) < 1
        assert is_document_url(
            "https://files-backend.assets.thrillshare.com/documents/asset/x?disposition=inline"
        )
        assert not is_document_url(f"{SITE}/departments/hr")
        assert same_site("https://www.test-usd.example.invalid/hr", f"{SITE}/")

    def test_school_years(self) -> None:
        assert school_years("Salary Schedule 2025-2026 and 2024-25, FY26") == ["2025-26", "2024-25"]
        assert school_years("Effective 7/1/2021 - 6/30/2022") == ["2021-22"]
        assert school_years("2025-2027 agreement") == []

    def test_shared_throttle_spaces_requests_per_host(self) -> None:
        clock = [0.0]
        sleeps: list[float] = []

        def sleep(s: float) -> None:
            sleeps.append(s)

        throttle = SharedThrottle(
            CrawlPolicy(user_agent=UA, min_delay_seconds=2.0), sleep=sleep, clock=lambda: clock[0]
        )
        throttle.wait("a")
        throttle.wait("a")
        throttle.wait("b")
        throttle.wait("a")
        assert sleeps == [2.0, 4.0]


@pytest.mark.skipif(not HAS_PDFTOTEXT, reason="cần poppler-utils (pdftotext)")
class TestPipeline:
    def run_gather(self, tmp_path: Path, seen: list[str] | None = None) -> list[Any]:
        return gather(
            QUEUE, tmp_path, {}, UA, workers=3, transport=site_transport(seen), sleep=lambda _: None
        )

    def test_classify_hand_built_pdf(self, tmp_path: Path) -> None:
        path = tmp_path / "s.pdf"
        path.write_bytes(PDF)
        c = classify(path)
        assert (c.kind, c.is_candidate, c.schedule_pages, c.best_year) == (
            "pdf",
            True,
            [1],
            "2025-26",
        )

    def test_gather_finds_teacher_schedule_and_respects_robots(self, tmp_path: Path) -> None:
        seen: list[str] = []
        works = self.run_gather(tmp_path, seen)
        by = {w.nces_id: w for w in works}
        assert by["0600001"].status == "found"
        assert by["0600002"].status == "no_candidates"
        assert by["0600003"].status == "no_website"
        chosen = next(d for d in by["0600001"].docs if d.asset_name == by["0600001"].chosen)
        assert chosen.url.endswith("Certificated%20Salary%20Schedule.pdf")
        assert (tmp_path / "docs" / chosen.asset_name).read_bytes() == PDF
        assert not any("/private/" in u for u in seen)
        assert not any(u.endswith("/menu") for u in seen)
        manifest = json.loads((tmp_path / "docs" / "manifest.json").read_text())
        assert {f["name"] for f in manifest["files"]} == {d.asset_name for d in by["0600001"].docs}
        assert [w.nces_id for w in load_work(tmp_path)] == [w.nces_id for w in works]

    def test_known_document_is_not_processed_again(self, tmp_path: Path) -> None:
        url = f"{SITE}/files/2025-26%20Certificated%20Salary%20Schedule.pdf"
        import hashlib

        known = {url: {hashlib.sha256(PDF).hexdigest()}}
        works = gather(
            QUEUE[:1],
            tmp_path,
            known,
            UA,
            workers=1,
            transport=site_transport(),
            sleep=lambda _: None,
        )
        assert works[0].status == "unchanged"

    def test_extract_validate_publish(self, tmp_path: Path) -> None:
        works = self.run_gather(tmp_path)
        calls: list[dict[str, Any]] = []
        answers = {ex.PRIMARY: tool_answer(), ex.SECONDARY: tool_answer()}
        extractions = extract_all(
            works,
            tmp_path,
            "sk-test-key",
            budget_usd=1.0,
            transport=claude_transport(answers, calls),
        )
        assert sorted(c["model"] for c in calls) == sorted([ex.PRIMARY, ex.SECONDARY])
        assert all(c["headers"]["x-api-key"] == "sk-test-key" for c in calls)
        assert json.loads((tmp_path / "extractions.json").read_text()).keys() == {"0600001"}

        result, outcomes = prepare(works, extractions, CATALOG, [], "docs-test-1", NOW.date())
        status = {o.nces_id: o.status for o in outcomes}
        assert status == {
            "0600001": "published",
            "0600002": "no_candidates",
            "0600003": "no_website",
        }
        cost = next(o for o in outcomes if o.nces_id == "0600001").cost_usd_micros
        assert cost == ex.cost_micros(ex.PRIMARY, 3000, 1500) + ex.cost_micros(
            ex.SECONDARY, 3000, 1500
        )

        db = fresh_db()
        sql = render_sql(schedules_sql(result, NOW) + pipeline_sql(works, outcomes, "run-1", NOW))
        db.executescript(sql)
        row = db.execute(
            "SELECT s.status, s.school_year, s.title, s.contract_days, s.source_page, d.district_id,"
            " d.release_tag, (SELECT count(*) FROM cells c WHERE c.schedule_id = s.id),"
            " (SELECT count(*) FROM extraction_runs e WHERE e.source_document_id = d.id)"
            " FROM schedules s JOIN source_documents d ON d.id = s.source_document_id"
        ).fetchone()
        assert row == ("published", "2025-26", "", 185, 1, 1, "docs-test-1", 45, 2)
        pipeline = dict(db.execute("SELECT district_id, status FROM district_pipeline").fetchall())
        assert pipeline == {1: "published", 2: "no_candidates", 3: "no_website"}
        assert db.execute("SELECT count(*) FROM document_classifications").fetchone()[0] == 2
        assert (
            db.execute("SELECT count(*) FROM document_candidates WHERE district_id = 1").fetchone()[
                0
            ]
            == 2
        )
        # rerun: nothing duplicated, attempts unchanged for the same run key, +1 for a new one
        db.executescript(sql)
        assert db.execute("SELECT count(*) FROM schedules").fetchone()[0] == 1
        assert (
            db.execute("SELECT attempts FROM district_pipeline WHERE district_id = 1").fetchone()[0]
            == 1
        )
        db.executescript(render_sql(pipeline_sql(works, outcomes, "run-2", NOW)))
        assert (
            db.execute("SELECT attempts FROM district_pipeline WHERE district_id = 1").fetchone()[0]
            == 2
        )
        report = render_report(works, outcomes, "run-1", 1.0)
        assert "Published: 1" in report and "Test Unified" in report

    def test_disagreeing_extractions_go_to_review(self, tmp_path: Path) -> None:
        works = self.run_gather(tmp_path)
        other = tool_answer()
        other["cells"][4][1] += 100
        answers = {ex.PRIMARY: tool_answer(), ex.SECONDARY: other}
        extractions = extract_all(
            works, tmp_path, "k", budget_usd=1.0, transport=claude_transport(answers, [])
        )
        result, outcomes = prepare(works, extractions, CATALOG, [], "docs-test-1", NOW.date())
        o = next(o for o in outcomes if o.nces_id == "0600001")
        assert o.status == "review" and o.issue_codes == ["double_extraction"]
        assert result.prepared[0].status == "draft"

    def test_not_a_schedule_and_budget(self, tmp_path: Path) -> None:
        works = self.run_gather(tmp_path)
        answers = {ex.PRIMARY: tool_answer(teacher=False), ex.SECONDARY: tool_answer(teacher=False)}
        assert (
            extract_all(
                works,
                tmp_path / "none",
                "k",
                budget_usd=0.0,
                transport=claude_transport(answers, []),
            )
            == {}
        )  # budget 0: no calls
        extractions = extract_all(
            works, tmp_path, "k", budget_usd=1.0, transport=claude_transport(answers, [])
        )
        _, outcomes = prepare(works, extractions, CATALOG, [], "t", NOW.date())
        assert next(o for o in outcomes if o.nces_id == "0600001").status == "no_schedule"


class TestExtractUnits:
    def test_to_draft_rejects_ragged_rows(self) -> None:
        data = tool_answer()
        data["cells"][2] = data["cells"][2][:2]
        with pytest.raises(ex.ExtractionError):
            ex.to_draft(data, "CA", "1", "Test")

    def test_to_draft_blank_cells_and_stipends(self) -> None:
        data = tool_answer()
        data["cells"][0][2] = None
        draft = ex.to_draft(data, "CA", "1", "Test")
        assert draft.cells[(0, 2)] == ex.Cell(None, ex.BLANK_NOTE)
        assert draft.lanes[0].lane_normalized == "BA" and draft.stipends[0].amount_cents == 200000

    def test_api_error_is_recorded(self) -> None:
        transport = httpx.MockTransport(lambda r: httpx.Response(400, json={"error": "bad"}))
        with httpx.Client(transport=transport) as client:
            run = ex.call_claude(
                client, "k", ex.PRIMARY, [{"type": "text", "text": "x"}], sleep=lambda _: None
            )
        assert run.error and run.error.startswith("HTTP 400") and run.data() is None
