"""Find coaching / extra-duty stipend documents on district websites (PLAN 11, D-126).

The teacher-salary crawl (``discover.crawl``) skips links with "coach", "athletic" or "extra
duty" on purpose. This search reuses the same polite crawler (robots.txt, per-host delay, size
limit) with its own scores: it looks for stipend, supplemental-pay and extra-duty schedules and
for negotiated agreements, which often carry the stipend appendix. A downloaded PDF is kept only
when the survey finds a stipend page in it; documents already in D1 (same URL) are not fetched
again. Nothing here calls a model.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

from pay_pipeline.acquisition.http import FetchError, PoliteFetcher
from pay_pipeline.acquisition.policy import CrawlPolicy
from pay_pipeline.acquisition.shared import SharedPoliteFetcher, SharedThrottle
from pay_pipeline.discover.crawl import CONTRACT_WORDS, NAV_WORDS, YEAR_RE, Link, discover
from pay_pipeline.documents.classify import detect_kind
from pay_pipeline.extra_pay.survey import survey_file
from pay_pipeline.pdf_pipeline.gather import (
    MAX_DOC_BYTES,
    export_url,
    fetch_headers,
    landing_target,
    reachable_website,
)

STIPEND_WORDS = ("stipend", "supplement", "extra duty", "extra-duty", "extraduty",
                 "extracurricular", "extra-curricular", "co-curricular", "cocurricular",
                 "coaching", "coach", "athletic", "activity pay", "activities pay",
                 "additional pay", "addendum", "extended duty")  # fmt: skip
PAY_WORDS = ("salary", "salaries", "pay", "schedule", "scale", "compensation", "rates")
NEGATIVE = ("calendar", "menu", "lunch", "bus ", "transportation", "nutrition", "roster",
            "physical", "concussion", "eligibility", "handbook for parents", "game schedule",
            "tickets", "booster", "camp", "registration", "forms", "permission")  # fmt: skip
PAGE_WORDS = ("athletic", "activities", "coach", "stipend", "supplement", "extra duty",
              "salary", "compensation", "negotiated", "bargaining", "board policy",
              "policies")  # fmt: skip

MAX_PAGES = 30
MAX_DOCS = 6
MIN_SCORE = 2.0


def _text(link: Link) -> str:
    return f"{link.text} {link.url}".lower().replace("%20", " ").replace("_", " ")


def _has(text: str, words: tuple[str, ...]) -> int:
    return sum(1 for w in words if w in text)


def score_doc(link: Link) -> float:
    """Higher = more likely a stipend schedule (or an agreement that holds one)."""
    t = _text(link)
    score = 3.0 * bool(_has(t, STIPEND_WORDS)) + 1.0 * bool(_has(t, PAY_WORDS))
    score += 2.0 * bool(_has(t, CONTRACT_WORDS))
    score += 1.0 * bool(YEAR_RE.search(t))
    return score - 3.0 * _has(t, NEGATIVE)


def score_page(link: Link) -> float:
    t = _text(link)
    score = 2.0 * bool(_has(t, PAGE_WORDS)) + 1.0 * bool(_has(t, NAV_WORDS))
    return score - 1.0 * bool(_has(t, NEGATIVE))


@dataclass
class CrawlResult:
    nces_id: str
    website: str | None
    status: str  # ok | no_website | unreachable | no_candidates | no_stipend | error
    pages: int = 0
    tried: int = 0
    files: list[dict[str, Any]] = field(default_factory=list)
    detail: str = ""
    candidates: list[str] = field(default_factory=list)
    """Best candidates, "score url", to see why a district gave nothing."""
    outcomes: list[str] = field(default_factory=list)
    """What each tried candidate turned out to be: "kept", "not pdf", "no stipend page"..."""


def crawl_one(
    nces_id: str,
    website: str | None,
    fetcher: PoliteFetcher,
    docs: Path,
    known: set[str],
    seeds: list[str] | None = None,
) -> CrawlResult:
    site = reachable_website(fetcher, website)
    if not site and not seeds:
        return CrawlResult(nces_id, website, "no_website" if not website else "unreachable")
    found = discover(
        fetcher, nces_id, site or (seeds or [""])[0], max_pages=MAX_PAGES,
        doc_score=score_doc, page_score=score_page, table_pages=False, seeds=seeds or (),
    )  # fmt: skip
    result = CrawlResult(nces_id, site, found.status, pages=found.pages_fetched)
    result.candidates = [f"{c.score:g} {c.url}"[:200] for c in found.candidates[:10]]
    if found.status != "ok":
        result.detail = "; ".join(found.errors[:2])[:300]
        return result
    picked = [c for c in found.candidates if c.score >= MIN_SCORE and c.url not in known]
    if not picked:
        result.status = "no_candidates"
        return result
    errors = []
    for cand in picked[:MAX_DOCS]:
        result.tried += 1
        try:
            url = export_url(cand.url)
            response = fetcher.get(url, headers=fetch_headers(url))
            data = response.content
            if detect_kind(data) != "pdf":
                inner = landing_target(data, response.final_url, cand.anchor_text)
                if inner is None or inner in known:
                    result.outcomes.append(f"{detect_kind(data)}: {cand.url}"[:200])
                    continue
                response = fetcher.get(export_url(inner), headers=fetch_headers(inner))
                data = response.content
            if detect_kind(data) != "pdf":
                result.outcomes.append(f"{detect_kind(data)}: {cand.url}"[:200])
                continue
        except FetchError as exc:
            errors.append(f"{cand.url}: {exc}"[:200])
            result.outcomes.append(f"error: {cand.url}"[:200])
            continue
        sha = hashlib.sha256(data).hexdigest()
        name = f"{nces_id}-{sha[:12]}.pdf"
        path = docs / name
        if any(f["sha256"] == sha for f in result.files):
            continue
        path.write_bytes(data)
        s = survey_file(path)
        if s is None or s.scanned or not s.stipend_pages:
            why = "scanned" if s is not None and s.scanned else "no stipend page"
            result.outcomes.append(f"{why}: {cand.url}"[:200])
            path.unlink()
            continue
        result.outcomes.append(f"kept: {cand.url}"[:200])
        result.files.append({
            "name": name, "url": cand.url, "final_url": response.final_url, "sha256": sha,
            "bytes": len(data),
            "fetched_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "content_type": response.headers.get("content-type"),
        })  # fmt: skip
    result.status = "ok" if result.files else "no_stipend"
    result.detail = "; ".join(errors[:2])[:300]
    return result


def crawl(
    queue: list[dict[str, Any]],
    out: Path,
    known: set[str],
    user_agent: str,
    *,
    seeds: dict[str, list[str]] | None = None,
    workers: int = 16,
    deadline_seconds: float = 300 * 60,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[CrawlResult]:
    docs = out / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    throttle = SharedThrottle(
        CrawlPolicy(user_agent=user_agent, min_delay_seconds=2.0), sleep=sleep
    )
    start = time.monotonic()
    results: dict[str, CrawlResult] = {}
    lock = threading.Lock()

    def run(row: dict[str, Any]) -> None:
        nces = str(row["nces_id"])
        if time.monotonic() - start > deadline_seconds:
            return
        with SharedPoliteFetcher(
            throttle, transport=transport, sleep=sleep, max_bytes=MAX_DOC_BYTES, max_retries=1
        ) as fetcher:
            try:
                r = crawl_one(
                    nces, row.get("website") or None, fetcher, docs, known,
                    (seeds or {}).get(nces),
                )  # fmt: skip
            except Exception as exc:  # one district must not stop the batch
                r = CrawlResult(nces, row.get("website"), "error", detail=f"{exc}"[:300])
        with lock:
            results[nces] = r

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(run, queue))
    ordered = [results[str(r["nces_id"])] for r in queue if str(r["nces_id"]) in results]
    files = [f for r in ordered for f in r.files]
    manifest = {"release_prefix": "docs-stipend", "description": "Tài liệu phụ cấp HLV (PLAN 11)",
                "files": files, "failed": []}  # fmt: skip
    (docs / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    (out / "crawl.json").write_text(
        json.dumps([asdict(r) for r in ordered], indent=1) + "\n", encoding="utf-8"
    )
    return ordered


def seeds_from_work(paths: list[Path], per_district: int = 3) -> dict[str, list[str]]:
    """Pages where the teacher crawl found salary documents (``work.json`` in the docs Releases):
    a district's stipend schedule is often listed on the same HR page."""
    out: dict[str, list[str]] = {}
    for path in paths:
        try:
            works = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for w in works:
            pages = out.setdefault(str(w["nces_id"]), [])
            for c in w.get("candidates", []):
                page = str(c.get("found_on", ""))
                good = c.get("score", 0) >= 2 and page.startswith("http")
                if good and not page.endswith("sitemap.xml") and page not in pages:
                    pages.append(page)
    return {k: v[:per_district] for k, v in out.items() if v}
