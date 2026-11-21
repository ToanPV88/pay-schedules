"""Tìm tài liệu phụ cấp HLV trên website GIẢ LẬP (httpx.MockTransport), không mạng."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from pay_pipeline.discover.crawl import Link
from pay_pipeline.extra_pay.crawl import crawl, score_doc
from tests.test_pdf_pipeline import make_pdf

SITE = "https://stipend.example.invalid"
HTML = {"content-type": "text/html"}
STIPENDS = make_pdf(
    ["2026-2027 Extra Duty Stipend Schedule"]
    + [f"Head {s} Coach   ${3000 + 100 * i:,}" for i, s in
       enumerate(["Football", "Basketball", "Volleyball", "Baseball", "Softball", "Soccer"])]
)  # fmt: skip
MENU = make_pdf(["Lunch menu", "Pizza   $3.50"])


def _transport(seen: list[str]) -> httpx.MockTransport:
    routes = {
        f"{SITE}/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /private/\n"),
        f"{SITE}/sitemap.xml": httpx.Response(404),
        f"{SITE}/": httpx.Response(200, headers=HTML, html=(
            f'<a href="{SITE}/hr">Human Resources</a><a href="{SITE}/menu.pdf">Lunch Menu</a>'
            f'<a href="{SITE}/private/stipends.pdf">Stipends</a>')),
        f"{SITE}/hr": httpx.Response(200, headers=HTML, html=(
            f'<a href="{SITE}/files/stipends.pdf">2026-27 Extra Duty Stipend Schedule</a>'
            f'<a href="{SITE}/files/old.pdf">Supplemental Pay 2026-27</a>')),
        f"{SITE}/files/stipends.pdf": httpx.Response(200, content=STIPENDS),
        f"{SITE}/files/old.pdf": httpx.Response(200, content=STIPENDS),
        f"{SITE}/menu.pdf": httpx.Response(200, content=MENU),
    }  # fmt: skip

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return routes.get(str(request.url), httpx.Response(404))

    return httpx.MockTransport(handler)


def test_score_prefers_stipend_documents() -> None:
    assert score_doc(Link("https://x/a.pdf", "2026-27 Coaching Stipends")) >= 4
    assert score_doc(Link("https://x/b.pdf", "Athletic game schedule")) < 2
    assert score_doc(Link("https://x/c.pdf", "Negotiated Agreement 2025-2028")) >= 2


def test_crawl_keeps_stipend_pdfs_and_respects_robots(tmp_path: Path) -> None:
    seen: list[str] = []
    queue = [{"nces_id": "9900001", "website": f"{SITE}/"}, {"nces_id": "9900002", "website": None}]
    known = {f"{SITE}/files/old.pdf"}
    results = crawl(queue, tmp_path, known, "test-agent", workers=1,
                    transport=_transport(seen), sleep=lambda _: None)  # fmt: skip
    by = {r.nces_id: r for r in results}
    assert by["9900001"].status == "ok" and by["9900002"].status == "no_website"
    assert [f["url"] for f in by["9900001"].files] == [f"{SITE}/files/stipends.pdf"]
    assert not any("/private/" in u for u in seen)
    assert f"{SITE}/files/old.pdf" not in seen  # already in D1
    manifest = json.loads((tmp_path / "docs" / "manifest.json").read_text())
    names = [f["name"] for f in manifest["files"]]
    assert names == [by["9900001"].files[0]["name"]]
    assert sorted(p.name for p in (tmp_path / "docs").iterdir()) == sorted(
        [*names, "manifest.json"]
    )
