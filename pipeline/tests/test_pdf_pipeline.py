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
from dataclasses import asdict
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
from pay_pipeline.pdf_pipeline import read as rd
from pay_pipeline.pdf_pipeline.gather import QueueItem, gather, load_work, website_variants
from pay_pipeline.pdf_pipeline.run import pipeline_sql, prepare, read_all, render_report
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


def fake_extractions(first: dict[str, Any], second: dict[str, Any] | None) -> dict[str, Any]:
    runs = [ex.ExtractionRun(rd.LAYOUT, None, json.dumps(first))]
    if second is not None:
        runs.append(ex.ExtractionRun(rd.WORDS, None, json.dumps(second)))
    return {"0600001": {"runs": [asdict(r) for r in runs]}}


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

    def test_landing_pages_and_google_links(self) -> None:
        from pay_pipeline.pdf_pipeline.gather import export_url, landing_target

        html = (
            b'<script>var d={"file":"https:\\/\\/files-backend.assets.thrillshare.com\\/documents'
            b'\\/asset\\/uploaded_file\\/1\\/X\\/a\\/2025-26-Teacher-Salary.pdf"}</script>'
            b'<a href="/menu">Lunch menu</a>'
        )
        target = landing_target(html, f"{SITE}/documents/hr/123456", "Teacher salary")
        assert target is not None and target.endswith("/2025-26-Teacher-Salary.pdf")
        assert landing_target(b"<a href='/menu'>Menu</a>", f"{SITE}/documents/1", "") is None
        assert export_url("https://drive.google.com/file/d/1AbCdEfGhIjK/view?usp=sharing") == (
            "https://drive.google.com/uc?export=download&id=1AbCdEfGhIjK"
        )
        assert export_url(
            "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjK/edit#gid=0"
        ).endswith("/spreadsheets/d/1AbCdEfGhIjK/export?format=xlsx")

    def test_google_links_through_drive_api_with_a_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # drive.google.com / docs.google.com disallow bots; the Drive API is Google's channel for
        # programs. The key goes in a header, never in the logged URL.
        from pay_pipeline.pdf_pipeline.gather import export_url, fetch_headers

        monkeypatch.setenv("GOOGLE_API_KEY", "k-123")
        api = "https://www.googleapis.com/drive/v3/files"
        for link in (
            "https://drive.google.com/file/d/1AbCdEfGhIjK/view?usp=sharing",
            "https://drive.google.com/open?id=1AbCdEfGhIjK&usp=drive_copy",
            "https://drive.google.com/uc?export=download&id=1AbCdEfGhIjK",
        ):
            assert export_url(link) == f"{api}/1AbCdEfGhIjK?alt=media&supportsAllDrives=true"
        doc = export_url("https://docs.google.com/document/d/1AbCdEfGhIjK/edit")
        assert doc.startswith(f"{api}/1AbCdEfGhIjK/export?mimeType=application%2Fvnd.openxml")
        assert "k-123" not in doc
        assert fetch_headers(doc) == {"X-goog-api-key": "k-123"}
        assert fetch_headers("https://www.district.example.invalid/a.pdf") is None
        monkeypatch.delenv("GOOGLE_API_KEY")
        assert fetch_headers(doc) is None

    def test_sitemap_pages_and_one_level_deeper_for_salary_pages(self) -> None:
        # D-027: the salary page is only in the sitemap (index -> page sitemap), and another one
        # sits three links below the home page.
        from pay_pipeline.acquisition.http import PoliteFetcher
        from pay_pipeline.discover.crawl import discover

        site = "https://deep.example.invalid"
        html = {"content-type": "text/html"}
        xml = {"content-type": "application/xml"}
        routes = {
            f"{site}/robots.txt": httpx.Response(404),
            f"{site}/": httpx.Response(200, headers=html, html='<a href="/departments">Departments</a>'),
            f"{site}/departments": httpx.Response(200, headers=html, html='<a href="/departments/human-resources">Human Resources</a>'),
            f"{site}/departments/human-resources": httpx.Response(200, headers=html, html='<a href="/departments/human-resources/salary-schedules">Salary Schedules</a>'),
            f"{site}/departments/human-resources/salary-schedules": httpx.Response(200, headers=html, html='<a href="/f/2025-26-teacher-salary-schedule.pdf">Teacher</a>'),
            f"{site}/sitemap.xml": httpx.Response(200, headers=xml, text=(
                f"<?xml version='1.0'?><sitemapindex><sitemap><loc>{site}/post-sitemap.xml</loc></sitemap>"
                f"<sitemap><loc>{site}/page-sitemap.xml</loc></sitemap></sitemapindex>")),
            f"{site}/page-sitemap.xml": httpx.Response(200, headers=xml, text=(
                f"<?xml version='1.0'?><urlset><url><loc>{site}/about</loc></url>"
                f"<url><loc>{site}/hr/compensation/certificated-salary</loc></url>"
                f"<url><loc>{site}/f/salary-schedule-2025-26.pdf</loc></url></urlset>")),
            f"{site}/hr/compensation/certificated-salary": httpx.Response(200, headers=html, html='<a href="/f/2026-27-certificated-salary-schedule.pdf">2026-27</a>'),
        }  # fmt: skip
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return routes.get(str(request.url), httpx.Response(404))

        policy = CrawlPolicy(user_agent=UA, min_delay_seconds=1.0)
        fetcher = PoliteFetcher(
            policy, transport=httpx.MockTransport(handler), sleep=lambda _: None
        )
        found = discover(fetcher, "0000001", f"{site}/")
        urls = {c.url for c in found.candidates}
        assert f"{site}/f/2026-27-certificated-salary-schedule.pdf" in urls  # via the sitemap
        assert f"{site}/f/2025-26-teacher-salary-schedule.pdf" in urls  # depth 3
        assert f"{site}/f/salary-schedule-2025-26.pdf" in urls  # document listed in the sitemap
        assert f"{site}/about" not in seen  # sitemap pages without salary words are not fetched

    def test_school_years(self) -> None:
        assert school_years("Salary Schedule 2025-2026 and 2024-25, FY26") == ["2025-26", "2024-25"]
        assert school_years("Effective 7/1/2021 - 6/30/2022") == ["2021-22"]
        assert school_years("2025-2027 agreement") == []
        assert school_years("2026\u20102027 Teacher Salary") == ["2026-27"]  # Unicode hyphen
        assert school_years("2 0 2 5 \u2013 2026 Pay Schedule") == ["2025-26"]  # letter-spaced
        assert school_years("Teachers Salary Scales FY26-27") == ["2026-27"]
        assert school_years("FY25/26 and FY 2026") == ["2025-26"]

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

    def test_folder_page_of_documents_is_opened(self, tmp_path: Path) -> None:
        # D-027: the salary link leads to a folder page listing document pages (Thrillshare).
        site = "https://folder.example.invalid"
        folder = f"{site}/documents/human-resources/salary-schedules/826164"
        html = {"content-type": "text/html"}
        routes = {
            f"{site}/robots.txt": httpx.Response(404),
            f"{site}/sitemap.xml": httpx.Response(404),
            f"{site}/": httpx.Response(200, headers=html, html=f'<a href="{folder}">Salary Schedules</a>'),
            folder: httpx.Response(200, headers=html, html=(
                f'<a href="{folder}/900001">2026-27 Teacher Salary Schedule</a>'
                f'<a href="{folder}/900002">Bus driver pay</a>')),
            f"{folder}/900001": httpx.Response(200, headers=html, html=(
                '<script>var f="https:\\/\\/files-backend.assets.thrillshare.com\\/documents'
                '\\/asset\\/uploaded_file\\/1\\/X\\/2026-27-Teacher-Salary.pdf"</script>')),
            "https://files-backend.assets.thrillshare.com/robots.txt": httpx.Response(404),
            "https://files-backend.assets.thrillshare.com/documents/asset/uploaded_file/1/X/2026-27-Teacher-Salary.pdf":
                httpx.Response(200, headers={"content-type": "application/pdf"}, content=PDF),
        }  # fmt: skip

        def handler(request: httpx.Request) -> httpx.Response:
            return routes.get(str(request.url), httpx.Response(404))

        item = QueueItem(9, "0600009", "Folder USD", "CA", f"{site}/", 100)
        works = gather([item], tmp_path, {}, UA, workers=1,
                       transport=httpx.MockTransport(handler), sleep=lambda _: None)  # fmt: skip
        assert works[0].status == "found"
        assert works[0].docs[0].url == f"{folder}/900001"

    def test_known_documents_only_count_current_readers(self) -> None:
        from pay_pipeline.pdf_pipeline.gather import known_documents

        rows = [
            {"url": "u1", "sha256": "a", "model": rd.WORDS},
            {"url": "u2", "sha256": "b", "model": "pdfplumber-words@0"},  # older reader: read again
            {"url": "u3", "sha256": "c"},
        ]
        assert known_documents(rows) == {"u1": {"a"}, "u3": {"c"}}

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

    def test_read_validate_publish(self, tmp_path: Path) -> None:
        works = self.run_gather(tmp_path)
        extractions = read_all(works, tmp_path)
        assert json.loads((tmp_path / "extractions.json").read_text()).keys() == {"0600001"}
        runs = extractions["0600001"]["runs"]
        assert [r["model"] for r in runs] == [rd.WORDS, rd.LAYOUT]
        answer = json.loads(runs[0]["raw_output"])
        assert answer["lanes"] == ["BA", "BA+30", "MA"] and answer["school_year"] == "2025-26"
        assert answer["cells"][0] == [51500.0, 54600.0, 57700.0]
        assert json.loads(runs[1]["raw_output"])["cells"] == answer["cells"]

        result, outcomes = prepare(works, extractions, CATALOG, [], "docs-test-1", NOW.date())
        status = {o.nces_id: o.status for o in outcomes}
        assert status == {
            "0600001": "published",
            "0600002": "no_candidates",
            "0600003": "no_website",
        }

        db = fresh_db()
        sql = render_sql(schedules_sql(result, NOW) + pipeline_sql(works, outcomes, "run-1", NOW))
        db.executescript(sql)
        row = db.execute(
            "SELECT s.status, s.school_year, s.title, s.source_page, d.district_id,"
            " d.release_tag, (SELECT count(*) FROM cells c WHERE c.schedule_id = s.id),"
            " (SELECT count(*) FROM extraction_runs e WHERE e.source_document_id = d.id)"
            " FROM schedules s JOIN source_documents d ON d.id = s.source_document_id"
        ).fetchone()
        assert row == ("published", "2025-26", "", 1, 1, "docs-test-1", 45, 2)
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
        report = render_report(works, outcomes, "run-1")
        assert "published): 1" in report and "Test Unified" in report and "0 USD" in report

    def test_disagreeing_readings_go_to_review(self, tmp_path: Path) -> None:
        works = self.run_gather(tmp_path)
        other = tool_answer()
        other["cells"][4][1] += 100
        result, outcomes = prepare(
            works, fake_extractions(tool_answer(), other), CATALOG, [], "t", NOW.date()
        )
        o = next(o for o in outcomes if o.nces_id == "0600001")
        assert o.status == "review" and o.issue_codes == ["double_extraction"]
        assert result.prepared[0].status == "draft"

    def test_single_reading_and_not_a_schedule(self, tmp_path: Path) -> None:
        works = self.run_gather(tmp_path)
        _, outcomes = prepare(
            works, fake_extractions(tool_answer(), None), CATALOG, [], "t", NOW.date()
        )
        assert next(o for o in outcomes if o.nces_id == "0600001").status == "published"
        nothing = tool_answer(teacher=False)
        _, outcomes = prepare(
            works, fake_extractions(nothing, nothing), CATALOG, [], "t", NOW.date()
        )
        assert next(o for o in outcomes if o.nces_id == "0600001").status == "no_schedule"

    def test_table_found_only_by_the_second_reader_goes_to_review(self, tmp_path: Path) -> None:
        works = self.run_gather(tmp_path)
        nothing = tool_answer(teacher=False)
        result, outcomes = prepare(
            works, fake_extractions(nothing, tool_answer()), CATALOG, [], "t", NOW.date()
        )
        o = next(o for o in outcomes if o.nces_id == "0600001")
        assert o.status == "review" and o.issue_codes == ["double_extraction"]
        assert result.prepared[0].status == "draft"


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


class TestGold:
    def test_committed_gold_files_load(self) -> None:
        from pay_pipeline.pdf_pipeline.gold import load_gold

        golds = load_gold(REPO / "pipeline" / "gold")
        assert len(golds) >= 15
        assert all(g.school_year[:2] == "20" and len(g.sha256) == 64 for g in golds)
        assert len({g.id for g in golds}) == len(golds)

    def test_compare_matches_labels_then_positions(self) -> None:
        from pay_pipeline.pdf_pipeline.gold import Gold, compare

        gold = Gold(
            "t",
            "1",
            "KY",
            "Test",
            "a.pdf",
            "https://x.invalid",
            "0" * 64,
            "2025-26",
            ["RANK III", "RANK II", "RANK I"],
            ["0", "1"],
            [[40000.0, 45000.0, 50000.0], [41000.0, None, 51000.0]],
        )
        data = tool_answer()
        data["lanes"] = ["Rank I", "Rank II", "Rank III", "Rank IV"]
        data["steps"] = [
            {"label": "0", "years_experience": 0},
            {"label": "1", "years_experience": 1},
        ]
        data["cells"] = [[50000, 45000, 40000, 30000], [51000, 46000, 41000, 30000]]
        total, right, wrong = compare(gold, ex.to_draft(data, "KY", "1", "Test"))
        assert (total, right, wrong) == (5, 5, [])
        data["cells"][1][0] = 51001
        total, right, wrong = compare(gold, ex.to_draft(data, "KY", "1", "Test"))
        assert (total, right) == (5, 4) and "chuẩn 51,000.00, trích 51,001.00" in wrong[0]

    def test_evaluate_on_hand_built_pdf(self, tmp_path: Path) -> None:
        if not HAS_PDFTOTEXT:
            pytest.skip("cần pdftotext")
        from pay_pipeline.pdf_pipeline.gold import Gold, evaluate, render

        (tmp_path / "s.pdf").write_bytes(PDF)
        steps = [str(s) for s in range(1, 16)]
        cells = [[50000.0 + 1500 * s, 53000.0 + 1600 * s, 56000.0 + 1700 * s] for s in range(1, 16)]
        gold = Gold("g1", "1", "CA", "Test", "s.pdf", "https://x.invalid", "0" * 64, "2025-26",
                    ["BA", "BA+30", "MA"], steps, cells)  # fmt: skip
        results = evaluate([gold], tmp_path, today=NOW.date())
        assert (
            results[0].status == "published"
            and results[0].accuracy == 1.0
            and results[0].school_year_ok
        )
        assert "45/45" in render(results)
        cells[3][1] = 1.0
        bad = Gold("g2", "1", "CA", "Test", "s.pdf", "https://x.invalid", "0" * 64, "2025-26",
                   ["BA", "BA+30", "MA"], steps, cells)  # fmt: skip
        assert "Bảng sai mà vẫn qua Validate: 1" in render(
            evaluate([bad], tmp_path, today=NOW.date())
        )


def L(*cells: str, step: float = 10.0) -> rd.Line:
    """A line of words; each cell is right-aligned in a column of width ``step``."""
    words = []
    for j, text in enumerate(cells):
        if text:
            words.append(rd.Word(text, j * step + step - len(text), j * step + step))
    return rd.Line(words)


class TestReader:
    def test_staircase_continuation_and_header(self) -> None:
        lines = [
            L("", "Teacher Salary Schedule 2025-26"),
            rd.Line([]),
            L("Step", "BA", "MA", "MA+30"),
            L("1", "50,000", "", ""),
            L("2", "51,000", "53,000", ""),
            L("3", "$52,000", "$54,000", "$56,000"),
            L("4", "", "", "57,500"),
            L("", "53,000", "55,000", ""),  # amounts of step 4 printed on the next line
            L("Rank IV", "40,000"),
        ]
        tables = rd.find_tables(lines, 1)
        assert len(tables) == 1
        t = tables[0]
        assert t.lanes == ["BA", "MA", "MA+30"]
        assert [r.label for r in t.rows] == ["1", "2", "3", "4"]
        assert t.grid == [
            [50000, None, None],
            [51000, 53000, None],
            [52000, 54000, 56000],
            [53000, 55000, 57500],
        ]

    def test_side_figures_and_dashes(self) -> None:
        # Garland ISD: daily rate, a stipend below the salary range and "-" for no stipend sit
        # between the annual amounts; they are skipped, not taken as words inside the row.
        lines = [
            L("Years", "Daily", "Without", "Stipend", "With"),
            L("0", "336.90", "63,000", "-", "63,000"),
            L("1", "342.07", "63,967", "-", "63,967"),
            L("2", "353.58", "66,119", "2,500", "68,619"),
            L("3", "355.31", "66,442", "2,500", "68,942"),
        ]
        tables = rd.find_tables(lines, 1)
        assert len(tables) == 1
        assert tables[0].grid == [
            [63000, 63000],
            [63967, 63967],
            [66119, 68619],
            [66442, 68942],
        ]

    def test_pay_components_keep_the_total(self) -> None:
        # Seattle: each step prints its pay components; the TOTAL line is the annual salary.
        lines = [L("Step", "Item", "BA", "MA")]
        for step in range(1, 5):
            base = 60000 + 1000 * step
            lines += [
                L(str(step), "Base Pay", f"${base:,}", f"${base + 9000:,}"),
                L("", "Tech Days", "$1,403", "$1,626"),
                L("", "TOTAL", f"${base + 9000:,}", f"${base + 19000:,}"),
            ]
        tables = rd.find_tables(lines, 1)
        assert len(tables) == 1
        assert [r.label for r in tables[0].rows] == ["1", "2", "3", "4"]
        assert tables[0].grid[0] == [70000, 80000]

    def test_unreadable_layout_and_table_choice(self) -> None:
        clash = [L("Step", "BA"), L("1", "50,000"), L("2", "51,000"), rd.Line([rd.Word("3", 0, 1),
                 rd.Word("52,000", 14, 20), rd.Word("52,500", 15, 20.5)])]  # fmt: skip
        assert rd.find_tables(clash, 1) == []
        classified = [L("", "Classified hourly staff"), rd.Line([]), L("Grade", "A", "B")] + [
            L(str(s), f"{30000 + s * 900:,}", f"{31000 + s * 900:,}") for s in range(1, 10)
        ]
        teacher = [L("", "Certificated teacher schedule"), rd.Line([]), L("Step", "BA", "MA")] + [
            L(str(s), f"{50000 + s * 900:,}", f"{52000 + s * 900:,}") for s in range(1, 6)
        ]
        tables = rd.find_tables(classified + [rd.Line([])] * 3 + teacher, 1)
        assert len(tables) == 2
        picked = rd.pick_table(tables)
        assert picked is not None and picked.grid[0] == [50900, 52900]

    def test_labels(self) -> None:
        for label in ("1", "31+", "0-3 Years", "20 Years and Over", "Step 4", "10**"):
            assert rd.parse_row(L(label, "50,000"), 0) is not None, label
        for label in ("Rank IV--41", "Total", ""):
            assert rd.parse_row(L(label, "50,000"), 0) is None, label

    def test_row_variants_seen_in_the_pilot(self) -> None:
        # step + code letter (Clark County), placement column (Fairfax), footnote marker (Detroit),
        # daily rate beside the annual one (Horry), side text far right (Pinellas)
        assert rd.parse_row(L("1", "A", "$57,471", "$63,986"), 0) is not None
        assert rd.parse_row(L("0,1,2", "1", "27,175", "30,876"), 0).label == "1"  # type: ignore[union-attr]
        assert rd.parse_row(L("11*", "79,000", "90,000", "*2024-25"), 0) is not None
        row = rd.parse_row(L("0", "284.96", "54,142", "304.24", "57,806"), 0)
        assert row is not None and [a for _, _, a in row.amounts] == [54142, 57806]
        side = rd.Line(
            [rd.Word("2", 0, 1), rd.Word("$60,880", 10, 17), rd.Word("Advanced", 60, 68)]
        )
        row = rd.parse_row(side, 0)
        assert row is not None and [a for _, _, a in row.amounts] == [60880]
        assert rd.parse_row(L("3", "61,118", "abc"), 0) is None  # words mixed in: not a row
        # hourly rate with four decimals before each annual amount (Hillsborough)
        row = rd.parse_row(L("1", "29.9874", "47,500.04", "31.8174", "50,398.76"), 0)
        assert row is not None and row.label == "1"
        assert [a for _, _, a in row.amounts] == [47500.04, 50398.76]

    def test_schedule_for_part_of_the_staff_is_second_choice_and_flagged(self) -> None:
        def block(title: str, base: int) -> list[rd.Line]:
            return [L("", title), rd.Line([]), L("Step", "BA", "MA")] + [
                L(str(s), f"{base + s * 900:,}", f"{base + 2000 + s * 900:,}") for s in range(1, 7)
            ]

        old = block("Teacher schedule for employees hired prior to July 1, 2013", 47000)
        new = block("Teacher salary schedule", 50000)
        tables = rd.find_tables(old + [rd.Line([])] * 3 + new, 1)
        picked = rd.pick_table(tables)
        assert picked is not None and picked.grid[0] == [50900, 52900]
        assert rd.scope_note(picked) is None
        only_old = rd.pick_table(rd.find_tables(old, 1))
        assert only_old is not None and "hired prior to" in (rd.scope_note(only_old) or "")
        assert rd.to_answer(only_old, "", rd.WORDS)["scope_note"]

    def test_letter_steps(self) -> None:
        # Broward, Collier, Volusia: steps named by letters, two steps paid the same ("T&U")
        lines = [L("Level", "Annual")] + [
            L(step, f"{54000 + i * 700:,}") for i, step in enumerate("CDEFGHIJ")
        ]
        lines += [L("Z", "75,000"), L("AA", "76,000"), L("T&U", "77,000")]
        tables = rd.find_tables(lines, 1)
        assert [r.label for r in tables[0].rows] == [*"CDEFGHIJ", "Z", "AA"]
        answer = rd.to_answer(tables[0], "", rd.LAYOUT)
        assert answer["steps"][0] == {"label": "C", "years_experience": None}
        for label in ("C", "AA", "T&U"):
            assert rd.parse_row(L(label, "50,000"), 0) is not None, label
        for label in ("CERT1", "Ab", "ABC"):
            assert rd.parse_row(L(label, "50,000"), 0) is None, label

    def test_standard_teacher_year_is_preferred_over_a_longer_calendar(self) -> None:
        # Mobile County: 240/260-day, then 187-day schedules for the same ranks
        def block(days: str, base: int) -> list[rd.Line]:
            return [L("", "Teachers"), L("", days), rd.Line([]), L("Step", "B", "A")] + [
                L(str(s), f"{base + s * 900:,}", f"{base + 5000 + s * 900:,}") for s in range(1, 7)
            ]

        long = block("240/260 DAYS", 67000)
        standard = block("187 DAYS", 48000)
        picked = rd.pick_table(rd.find_tables(long + [rd.Line([])] * 3 + standard, 1))
        assert picked is not None and picked.grid[0] == [48900, 53900]
        # No calendar stated: the first table is kept.
        plain = block("", 67000)
        picked = rd.pick_table(rd.find_tables(plain + [rd.Line([])] * 3 + standard, 1))
        assert picked is not None and picked.grid[0] == [67900, 72900]

    def test_lane_label_drops_unit_words(self) -> None:
        assert rd.lane_label("Bachelor’s Degree  Hourly Rate Rate") == "Bachelor’s Degree"
        assert rd.lane_label("MA (Annual)") == "MA"
        assert rd.lane_label("Bachelors ANNUAL(1) DAILY(2)") == "Bachelors"
        # title words swept in front of the lane name (Douglas County), date in the heading
        title = "2025-2026 Licensed General Compensation Schedule Effective 7/1/2025"
        assert rd.lane_label("General Compensation MA + 15", title) == "MA + 15"
        assert rd.lane_label("Effective 7/1/2025 PHDEDS", title) == "PHDEDS"
        # kept when what is left would not start like a lane name
        assert rd.lane_label("10NC Pay Schedule", "10NC Pay Schedule 8NC") == "10NC Pay Schedule"
        assert rd.lane_label("New Hire Salary", "Years of New Hire Salary") == "New Hire Salary"

    def test_pdf_checks_flag_prose_labels_and_partial_schedules(self) -> None:
        from pay_pipeline.pdf_pipeline.run import pdf_checks
        from pay_pipeline.schedules.model import Cell, Lane, ScheduleDraft, Step

        draft = ScheduleDraft(
            state="NV", state_district_id="x", district_name="x", school_year="2026-27",
            lanes=[Lane("MA+16 V"), Lane("institution from an accredited X")],
            steps=[Step("1")], cells={},
        )  # fmt: skip
        assert [i.code for i in pdf_checks({}, draft, NOW.date())] == ["lane_label"]
        draft.lanes = [Lane("BA"), Lane("MA")]
        assert pdf_checks({}, draft, NOW.date()) == []
        assert [
            i.code for i in pdf_checks({"scope_note": "hired prior to 2013"}, draft, NOW.date())
        ] == ["schedule_scope"]
        draft.school_year = "2023-24"  # more than two school years before 2026-27
        assert [i.code for i in pdf_checks({}, draft, NOW.date())] == ["school_year"]
        draft.school_year = "2024-25"
        assert pdf_checks({}, draft, NOW.date()) == []
        assert rd.lane_label("Annual Rate") == "Annual Rate"  # nothing else left: keep it
        # Every step paid the same (Volusia performance-pay tiers): a person confirms.
        flat = ScheduleDraft(
            state="FL", state_district_id="x", district_name="x", school_year="2025-26",
            lanes=[Lane("Pay")], steps=[Step(x) for x in "ABC"],
            cells={(i, 0): Cell(5_000_000) for i in range(3)},
        )  # fmt: skip
        assert [i.code for i in pdf_checks({}, flat, NOW.date())] == ["flat_schedule"]
        flat.cells[(2, 0)] = Cell(5_100_000)
        assert pdf_checks({}, flat, NOW.date()) == []

    def test_side_box_and_empty_staircase_rows_do_not_split_the_table(self) -> None:
        lines = [L("Step", "BA", "MA")] + [
            L(str(s), f"{50000 + s * 900:,}", f"{52000 + s * 900:,}") for s in (1, 2)
        ]
        lines += [rd.Line([rd.Word("Masters", 80, 87), rd.Word("2,251", 90, 95)])] * 2  # side box
        lines += [L("3", "52,700", "54,700"), L("4"), L("5"), L("6", "", "57,500")]
        lines += [L("7", "", "58,400")]
        tables = rd.find_tables(lines, 1)
        assert len(tables) == 1
        assert [r.label for r in tables[0].rows] == ["1", "2", "3", "6", "7"]
        assert tables[0].grid[-2] == [None, 57500]


class TestShards:
    def _rows(self) -> list[dict[str, Any]]:
        return [
            {"nces_id": "1", "website": "https://www.big.k12.ca.us/"},
            {"nces_id": "2", "website": "http://big.k12.ca.us/hr"},
            {"nces_id": "3", "website": "small.org"},
            {"nces_id": "4", "website": None},
            {"nces_id": "5", "website": "https://other.net"},
        ]

    def test_host(self) -> None:
        from pay_pipeline.pdf_pipeline.gather import website_host

        assert website_host("https://WWW.Big.k12.ca.us/x") == "big.k12.ca.us"
        assert website_host("small.org") == "small.org"
        assert website_host(None) is None
        assert website_host("") is None

    def test_same_host_same_shard_and_nothing_lost(self) -> None:
        from pay_pipeline.pdf_pipeline.gather import shard_queue

        parts = shard_queue(self._rows(), 3)
        assert len(parts) == 3
        ids = [r["nces_id"] for p in parts for r in p]
        assert sorted(ids) == ["1", "2", "3", "4", "5"]
        holder = [i for i, p in enumerate(parts) if any(r["nces_id"] == "1" for r in p)]
        assert any(r["nces_id"] == "2" for r in parts[holder[0]])
        assert max(len(p) for p in parts) - min(len(p) for p in parts) <= 2

    def test_one_shard_keeps_order(self) -> None:
        from pay_pipeline.pdf_pipeline.gather import shard_queue

        assert [r["nces_id"] for r in shard_queue(self._rows(), 1)[0]] == ["1", "2", "3", "4", "5"]

    def test_bounds(self) -> None:
        from pay_pipeline.pdf_pipeline.gather import MAX_SHARDS, shard_queue

        with pytest.raises(ValueError):
            shard_queue([], 0)
        with pytest.raises(ValueError):
            shard_queue([], MAX_SHARDS + 1)

    def test_cli_writes_parts(self, tmp_path: Path) -> None:
        from pay_pipeline.cli import main

        q = tmp_path / "queue.json"
        q.write_text(json.dumps([{"results": self._rows()}]), encoding="utf-8")
        assert (
            main(
                ["pdf-shard", "--queue", str(q), "--shards", "2", "--out-dir", str(tmp_path / "s")]
            )
            == 0
        )
        parts = [json.loads((tmp_path / "s" / f"queue-{i}.json").read_text()) for i in range(2)]
        assert sum(len(p) for p in parts) == 5


class TestOcr:
    """D-036: scanned schedules read with Tesseract."""

    def test_fix_token(self) -> None:
        from pay_pipeline.pdf_pipeline.ocr import fix_token

        assert fix_token("S45,123") == "$45,123"
        assert fix_token("4O,l23") == "40,123"
        assert fix_token("45.123") == "45,123"
        assert fix_token("45.12") == "45.12"  # cents stay
        assert fix_token("71,449]") == "71,449"
        assert fix_token("Step") == "Step"
        assert fix_token("L3") == "13"
        assert fix_token("“10") == "10"

    def test_step_number_above_its_row(self) -> None:
        from pay_pipeline.pdf_pipeline.ocr import (
            fill_step_labels,
            lift_step_labels,
            repair_step_labels,
        )

        def line(*items: tuple[str, float]) -> rd.Line:
            return rd.Line([rd.Word(t, x, x + 60) for t, x in items])

        amounts = [("$43,992", 300.0), ("$45,221", 400.0), ("$48,303", 500.0)]
        lines = [
            line(("1", 100.0)),
            line(*amounts),
            line(("oe", 120.0)),
            line(("2", 100.0)),
            line(("iz", 200.0), *amounts),
            line(("3", 100.0)),
            line(*amounts),
        ]
        rows = fill_step_labels(repair_step_labels(lift_step_labels(lines)))
        assert [ln.words[0].text for ln in rows if len(ln.words) > 3] == ["1", "2", "3"]
        assert all(len(ln.words) == 4 for ln in rows if len(ln.words) > 3)

    def test_repair_step_labels(self) -> None:
        from pay_pipeline.pdf_pipeline.ocr import repair_step_labels

        amounts = ["$41,000", "$42,000", "$43,000"]

        def row(label: str) -> rd.Line:
            return rd.Line(
                [rd.Word(t, 100.0 * i, 100.0 * i + 60) for i, t in enumerate([label, *amounts])]
            )

        labels = ["9", "10", "1", "12", "13", "14", "7"]
        fixed = [ln.words[0].text for ln in repair_step_labels([row(x) for x in labels])]
        assert fixed == ["9", "10", "11", "12", "13", "14", "15"]
        jump = ["1", "2", "3", "10", "15"]  # longevity steps stay as printed
        assert [ln.words[0].text for ln in repair_step_labels([row(x) for x in jump])] == jump

    def test_vote_cell_by_cell(self) -> None:
        from pay_pipeline.pdf_pipeline.ocr import vote

        def answer(cells: list[list[float | None]], labels: list[str], page: int = 48) -> dict:
            return {
                "is_teacher_salary_schedule": True, "school_year": "2026-27",
                "lanes": ["BA", "MA"], "steps": [{"label": x} for x in labels],
                "cells": cells, "source_pages": [page],
            }  # fmt: skip

        good = [[100.0, 200.0], [110.0, 220.0]]
        readings = [
            answer(good, ["1", "2"]),
            answer([[100.0, 200.0], [110.0, 228.0]], ["1", "2"]),  # one misread digit
            answer([[110.0, 220.0]], ["2"]),  # first row dropped
            answer(good, ["1", "2"]),
            answer([[900.0, 900.0], [900.0, 900.0]], ["1", "2"], page=49),  # another page
        ]
        voted = vote(readings)
        assert voted is not None
        assert voted["cells"] == good
        assert voted["ocr_agree"] == 3
        assert vote(readings[:2]) is None  # too few readings
        split = [answer(good, ["1", "2"]), answer(good, ["1", "2"]),
                 answer([[100.0, 201.0], [110.0, 220.0]], ["1", "2"]),
                 answer([[100.0, 201.0], [110.0, 220.0]], ["1", "2"])]  # fmt: skip
        assert vote(split) is None  # 2 against 2: no amount wins

    def test_scan_order_keeps_the_appendix(self) -> None:
        from pay_pipeline.pdf_pipeline.ocr import MAX_SCAN_PAGES, SCAN_HEAD_PAGES, scan_order

        assert scan_order(67) == list(range(1, 68))  # Marysville: schedule on page 62
        long = scan_order(400)
        assert len(long) == MAX_SCAN_PAGES
        assert long[:SCAN_HEAD_PAGES] == list(range(1, SCAN_HEAD_PAGES + 1))
        assert long[-1] == 400

    def test_known_documents_reread_old_scans(self) -> None:
        from pay_pipeline.pdf_pipeline.gather import known_documents
        from pay_pipeline.pdf_pipeline.ocr import CONFIGS

        rows = [
            {"url": "u1", "sha256": "a", "model": rd.LAYOUT, "scanned": 1},  # before OCR
            {"url": "u2", "sha256": "b", "model": CONFIGS[0][0], "scanned": 1},
            {"url": "u3", "sha256": "c", "model": rd.LAYOUT, "scanned": 0},
        ]
        assert known_documents(rows) == {"u2": {"b"}, "u3": {"c"}}

    def test_fill_step_labels(self) -> None:
        from pay_pipeline.pdf_pipeline.ocr import fill_step_labels

        def line(*texts: str) -> rd.Line:
            return rd.Line([rd.Word(t, 100.0 * i, 100.0 * i + 60) for i, t in enumerate(texts)])

        amounts = ("50,000", "52,000", "54,000")
        lines = [
            line("STEP", "BA", "MA", "PhD"),
            line(*amounts),  # step 1 dropped
            line(*amounts),  # step 2 dropped
            line("3", *amounts),
            line("4", *amounts),
            line(*amounts),  # step 5 dropped
            line("6", *amounts),
            line("10", *amounts),
            line(*amounts),  # between 10 and 15: two rows for four numbers, left alone
            line("15", *amounts),
        ]
        labels = [ln.words[0].text for ln in fill_step_labels(lines)]
        assert labels == ["STEP", "1", "2", "3", "4", "5", "6", "10", "50,000", "15"]

    def test_same_grid(self) -> None:
        from pay_pipeline.pdf_pipeline.ocr import same_grid

        a = {"is_teacher_salary_schedule": True, "cells": [[1.0, None], [2.0, 3.0]]}
        assert same_grid(a, {**a, "cells": [[1.0, None], [2.0, 3.0]]})
        assert not same_grid(a, {**a, "cells": [[1.0, None], [2.0, 8.0]]})
        assert not same_grid(a, {**a, "cells": [[1.0, 5.0], [2.0, 3.0]]})
        assert not same_grid(a, {"is_teacher_salary_schedule": False, "cells": []})

    @pytest.mark.skipif(shutil.which("tesseract") is None, reason="cần tesseract")
    def test_reads_a_scanned_table(self, tmp_path: Path) -> None:
        from PIL import Image, ImageDraw, ImageFont

        from pay_pipeline.pdf_pipeline.ocr import read_scanned

        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 34)
        except OSError:
            font = ImageFont.load_default(size=34)
        page = Image.new("L", (1700, 2200), 255)
        draw = ImageDraw.Draw(page)
        draw.text((300, 150), "Teacher Salary Schedule 2025-2026", font=font, fill=0)
        lanes = ["Step", "BA", "BA+15", "MA", "MA+30"]
        for j, lane in enumerate(lanes):
            draw.text((200 + 300 * j, 300), lane, font=font, fill=0)
        want = []
        for i in range(15):
            row = [48000 + 1100 * i + 2500 * j for j in range(4)]
            want.append([float(v) for v in row])
            y = 370 + 60 * i
            draw.text((200, y), str(i + 1), font=font, fill=0)
            for j, v in enumerate(row):
                draw.text((500 + 300 * j, y), f"{v:,}", font=font, fill=0)
            draw.line((180, y + 50, 1500, y + 50), fill=0, width=3)  # table rule
        pdf = tmp_path / "scan.pdf"
        page.save(pdf, "PDF", resolution=200)
        answers = read_scanned(pdf)
        assert len(answers) == 2
        assert answers[0]["is_teacher_salary_schedule"]
        assert answers[0]["cells"] == want
        assert answers[1]["cells"] == want
        assert answers[0]["school_year"] == "2025-26"


def test_pdf_checks_hold_uncertain_scans() -> None:
    """D-036: a scan needs three matching OCR readings, step 0 or 1 first and short lane labels."""
    from pay_pipeline.pdf_pipeline.ocr import CONFIGS
    from pay_pipeline.pdf_pipeline.run import pdf_checks
    from pay_pipeline.schedules.model import Lane, ScheduleDraft, Step

    draft = ScheduleDraft(
        state="KY", state_district_id="x", district_name="x", school_year="2026-27",
        lanes=[Lane("BA"), Lane("MA")], steps=[Step("1"), Step("2")], cells={},
    )  # fmt: skip
    ocr_answer = {"reader": CONFIGS[0][0], "ocr_agree": 3}
    assert pdf_checks(ocr_answer, draft, NOW.date()) == []
    assert [i.code for i in pdf_checks({**ocr_answer, "ocr_agree": 2}, draft, NOW.date())] == [
        "ocr"
    ]
    draft.steps = [Step("2"), Step("3")]
    assert [i.code for i in pdf_checks(ocr_answer, draft, NOW.date())] == ["ocr"]
    draft.steps = [Step("1")]
    draft.lanes = [Lane("Level 3 Theta Hanlon Instructors ATC at"), Lane("MA")]
    assert [i.code for i in pdf_checks(ocr_answer, draft, NOW.date())] == ["ocr"]
    assert pdf_checks({"reader": rd.WORDS}, draft, NOW.date()) == []  # text PDFs unaffected


class TestSeeds:
    """D-038: schedule URLs found by hand go straight to download, without a crawl."""

    def test_load_seeds(self, tmp_path: Path) -> None:
        from pay_pipeline.pdf_pipeline.gather import load_seeds

        f = tmp_path / "seeds.csv"
        f.write_text(
            "nces_id,url,note\n"
            "0600002,https://a.example.invalid/s.pdf,first\n"
            "0600002,https://a.example.invalid/t.pdf,second\n"
            "bad,https://x.example.invalid/x.pdf,\n"
            "0600003,ftp://x.example.invalid/x.pdf,\n",
            encoding="utf-8",
        )
        assert load_seeds(f) == {
            "0600002": ("https://a.example.invalid/s.pdf", "https://a.example.invalid/t.pdf")
        }
        assert load_seeds(None) == {}

    def test_seed_skips_the_crawl(self, tmp_path: Path) -> None:
        from dataclasses import replace

        url = f"{SITE}/files/2025-26%20Certificated%20Salary%20Schedule.pdf"
        # The district's own website is empty; the hand-found link is what gets the schedule.
        item = replace(QUEUE[1], seeds=(url,))
        seen: list[str] = []
        works = gather(
            [item], tmp_path, {}, UA, workers=1, transport=site_transport(seen),
            sleep=lambda _: None,
        )  # fmt: skip
        assert works[0].status == "found"
        assert works[0].candidates[0]["method"] == "manual"
        assert not any(u.startswith("https://empty.example.invalid/") for u in seen)

    def test_old_http_address_falls_back_to_https(self, tmp_path: Path) -> None:
        from dataclasses import replace

        assert website_variants("http://www.old.example.invalid/") == [
            "http://www.old.example.invalid/",
            "https://www.old.example.invalid/",
            "https://old.example.invalid/",
            "http://old.example.invalid/",
        ]

        # NCES lists http://; that server does not answer, the https one does.
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if url.startswith("http://"):
                raise httpx.ConnectError("refused", request=request)
            return ROUTES.get(url, httpx.Response(404))

        item = replace(QUEUE[0], website=SITE.replace("https://", "http://") + "/")
        works = gather(
            [item], tmp_path, {}, UA, workers=1, transport=httpx.MockTransport(handler),
            sleep=lambda _: None,
        )  # fmt: skip
        assert works[0].status == "found"
        assert works[0].website == f"{SITE}/"

    def test_seed_page_without_files_is_crawled(self, tmp_path: Path) -> None:
        from dataclasses import replace

        # The hand-found page links only to the HR page, which holds the schedule.
        item = replace(QUEUE[1], seeds=(f"{SITE}/",))
        works = gather(
            [item], tmp_path, {}, UA, workers=1, transport=site_transport(),
            sleep=lambda _: None,
        )  # fmt: skip
        assert works[0].status == "found"

    def test_seed_page_tries_its_files(self, tmp_path: Path) -> None:
        from dataclasses import replace

        # A hand-found HR page: its files are fetched in order of how salary-like their links are.
        item = replace(QUEUE[1], seeds=(f"{SITE}/departments/human-resources",))
        seen: list[str] = []
        works = gather(
            [item], tmp_path, {}, UA, workers=1, transport=site_transport(seen),
            sleep=lambda _: None,
        )  # fmt: skip
        assert works[0].status == "found"
        assert seen.index(
            f"{SITE}/files/2025-26%20Certificated%20Salary%20Schedule.pdf"
        ) < seen.index(f"{SITE}/files/classified.pdf")


class TestScriptLinks:
    def test_menu_in_json(self) -> None:
        from pay_pipeline.discover.crawl import script_links

        html = (
            '<a href="/">Home</a><script>window.__DATA__={"menu":[{"url":'
            '"https:\\/\\/www.fisd.example.invalid\\/o\\/fisd\\/page\\/compensation-plan"},'
            '{"url":"\\/page\\/human-resources"},{"img":"/assets/logo.png"},'
            '{"url":"https:\\/\\/cdn.example.invalid\\/docs\\/salary.pdf"},'
            '{"url":"https:\\/\\/other.example.invalid\\/page\\/x"}]}</script>'
        )
        links = script_links(html, "https://www.fisd.example.invalid/")
        assert [(ln.url, ln.text) for ln in links] == [
            ("https://www.fisd.example.invalid/o/fisd/page/compensation-plan", "compensation plan"),
            ("https://www.fisd.example.invalid/page/human-resources", "human resources"),
            ("https://cdn.example.invalid/docs/salary.pdf", "salary.pdf"),
        ]


class TestRelaxedPages:
    def test_short_single_lane_page(self) -> None:
        from pay_pipeline.documents.classify import score_page

        rows = "\n".join(f"{y}   {50000 + 1000 * y:,}" for y in range(10))
        text = f"TEACHERS\nYEARS OF EXPERIENCE   BACHELORS SALARY SCHEDULE\n{rows}"
        assert score_page(text, 1).is_schedule

    def test_rows_without_step_word(self) -> None:
        from pay_pipeline.documents.classify import score_page

        rows = "\n".join(
            f"{n}  " + "  ".join(f"{50000 + 1000 * n + 2000 * c:,}" for c in range(4))
            for n in range(16, 0, -1)
        )
        text = f"SALARY SCHEDULE\nTop  Bachelors  B+9  Masters  M+9\n{rows}"
        assert score_page(text, 1).is_schedule

    def test_lane_headings_with_credits(self) -> None:
        # Goddard KS: "STEP  B  B+10  M  M+10" with no teacher/salary word on the page
        from pay_pipeline.documents.classify import score_page

        rows = "\n".join(
            f"{n}  " + "  ".join(f"{50000 + 500 * n + 1300 * c:,}" for c in range(4))
            for n in range(1, 16)
        )
        for header in ("STEP  B  B+10  M  M+10", "Certfied Staff  Step\n  BS  BS+8G  MS  MS+8G"):
            assert score_page(f"2026-2027 Placement Schedule\n{header}\n{rows}", 1).is_schedule

    def test_descending_steps(self) -> None:
        lines = [L("Top", "BA", "MA")] + [
            L(str(n), f"{70000 - 1000 * n:,}", f"{80000 - 1000 * n:,}") for n in range(5, 0, -1)
        ]
        tables = rd.find_tables(lines, 1)
        assert len(tables) == 1
        assert [r.label for r in tables[0].rows] == ["5", "4", "3", "2", "1"]


class TestHtmlTables:
    PAGE = (
        "<!DOCTYPE html><html><head><title>2026-27 Teacher Salary Schedule</title>"
        "<script>var t = Date.now();</script></head><body><nav><a href='/'>Home</a></nav>"
        "<table><tr><th>Years of Experience</th><th>Bachelor's</th><th>Master's</th></tr>"
        + "".join(
            f"<tr><td>{y}</td><td>${60000 + 900 * y:,}</td><td>${62000 + 900 * y:,}</td></tr>"
            for y in range(12)
        )
        + "</table><table><tr><td>Menu</td></tr></table></body></html>"
    )

    def test_page_with_salary_table_is_a_document(self, tmp_path: Path) -> None:
        from pay_pipeline.documents.classify import classify, detect_kind, salary_table_page

        page = salary_table_page(self.PAGE.encode())
        assert page is not None and b"Menu" not in page and b"Date.now" not in page
        assert salary_table_page(b"<html><body><table><tr><td>x</td></tr></table>") is None
        path = tmp_path / "p.html"
        path.write_bytes(page)
        assert detect_kind(page) == "html"
        c = classify(path)
        assert c.is_candidate and c.schedule_pages == [1] and c.best_year == "2026-27"
        answer = rd.read_html(path)
        assert answer["lanes"] == ["Bachelor's", "Master's"]
        assert answer["cells"][0] == [60000.0, 62000.0]
        assert len(answer["cells"]) == 12


class TestManualFiles:
    """Files the owner downloaded by hand (D-051): read from disk, never fetched."""

    def test_manual_files_are_read_from_disk(self, tmp_path: Path) -> None:
        from dataclasses import replace

        from pay_pipeline.pdf_pipeline.gather import load_manual

        files = tmp_path / "files"
        files.mkdir()
        (files / "001_schedule.pdf").write_bytes(PDF)
        (files / "001_other.pdf").write_bytes(make_pdf(["Lunch menu", "Monday pizza"]))
        csv_path = tmp_path / "manual.csv"
        url = "https://drive.google.com/file/d/abcdefghijk/view"
        csv_path.write_text(
            "nces_id,file,url\n"
            f"{QUEUE[1].nces_id},001_other.pdf,https://example.invalid/menu.pdf\n"
            f"{QUEUE[1].nces_id},001_schedule.pdf,{url}\n"
            f"{QUEUE[1].nces_id},../outside.pdf,https://example.invalid/x.pdf\n"
            "bad,001_schedule.pdf,https://example.invalid/y.pdf\n",
            encoding="utf-8",
        )
        manual = load_manual(csv_path, files)
        assert len(manual[QUEUE[1].nces_id]) == 2  # the path outside the folder is dropped

        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError(f"no network expected: {request.url}")

        item = replace(QUEUE[1], manual=manual[QUEUE[1].nces_id])
        works = gather(
            [item], tmp_path / "work", {}, UA, workers=1,
            transport=httpx.MockTransport(handler), sleep=lambda _: None,
        )  # fmt: skip
        assert works[0].status == "found"
        chosen = next(d for d in works[0].docs if d.asset_name == works[0].chosen)
        assert chosen.url == url
        assert (tmp_path / "work" / "docs" / chosen.asset_name).read_bytes() == PDF


def test_multi_year_contract_takes_latest_year(tmp_path: Path) -> None:
    # A contract prints the grid of each year it covers; the latest year is the one in force.
    def grid(year: str, base: int) -> list[str]:
        return [f"{year} Teacher Salary Schedule", "Step      BA        BA+30      MA"] + [
            f"{s:>4}   {base + 1500 * s:,}   {base + 3000 + 1600 * s:,}   {base + 6000 + 1700 * s:,}"
            for s in range(1, 13)
        ]

    lines = ["Agreement between the Board and the Education Association", ""]
    lines += [*grid("2023-2024", 50000), "", *grid("2024-2025", 52000)]
    path = tmp_path / "contract.pdf"
    path.write_bytes(make_pdf(lines))
    answers = rd.read_pdf(path, [1])
    assert answers[0]["is_teacher_salary_schedule"]
    assert answers[0]["school_year"] == "2024-25"
    assert answers[0]["cells"][0][0] == 53500


def test_year_in_force_stops_at_next_school_year() -> None:
    # D-058: a Michigan contract through 2029-30 is read for next school year at the latest.
    import datetime as dt

    today = dt.date(2026, 11, 15)  # school year 2026-27
    years = {"2025-26", "2026-27", "2027-28", "2028-29", "2029-30", ""}
    assert rd.year_in_force(years, today) == "2027-28"
    assert rd.year_in_force({"2023-24", "2024-25"}, today) == "2024-25"
    assert rd.year_in_force({"2030-31", "2031-32"}, today) == "2031-32"  # all later: the latest


def test_side_figures_before_and_between_annual_amounts() -> None:
    # Fulton: a semi-monthly figure before each annual one; Northside: a "$0" increase column;
    # Duval: an hourly rate with five decimals after the annual one (D-054).
    fulton = rd.parse_row(L("0", "$2,521", "$60,506", "$2,771", "$66,514", step=12.0), 0)
    assert fulton is not None and fulton.label == "0"
    assert [a[2] for a in fulton.amounts] == [60506.0, 66514.0]
    northside = rd.parse_row(L("3", "$1,200", "$63,155", step=12.0), 0)
    assert northside is not None and [a[2] for a in northside.amounts] == [63155.0]
    zero = rd.parse_row(L("1", "$0", "$61,285", step=12.0), 0)
    assert zero is not None and [a[2] for a in zero.amounts] == [61285.0]
    duval = rd.parse_row(L("01", "52,888", "25.32960", step=12.0), 0)
    assert duval is not None and [a[2] for a in duval.amounts] == [52888.0]
    assert rd.lane_label("T5 - Masters SEMI-MONTHLY") == "T5 - Masters"
