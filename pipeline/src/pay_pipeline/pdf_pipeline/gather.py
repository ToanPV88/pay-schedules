"""Steps 1-3 of the PDF pipeline for a batch of districts: Discover, Fetch, Classify.

Input: the work queue read from D1 (district id, NCES id, website), and the documents already
stored (URL → SHA-256), so an unchanged file is not processed again (PLAN: "File có sha256
không đổi thì bỏ qua"). Output, in a work directory:

* ``work.json``: per district, what was found, downloaded and how each file was classified;
* ``docs/``: downloaded files named ``<nces>-<sha12>.<ext>`` plus ``manifest.json``, ready to be
  attached to a GitHub Release (D-011).

Districts are processed in parallel; one shared throttle keeps every host polite. A deadline
stops new districts from starting: those not started keep their queue state and come back in
the next run (checkpoint = D1 ``district_pipeline``).
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import re
import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from pay_pipeline.acquisition.http import FetchError, PoliteFetcher
from pay_pipeline.acquisition.policy import CrawlPolicy
from pay_pipeline.acquisition.shared import SharedPoliteFetcher, SharedThrottle
from pay_pipeline.discover.crawl import (
    DOC_EXTENSIONS,
    Candidate,
    Link,
    discover,
    extract_links,
    is_document_url,
    same_site,
    score_document,
)
from pay_pipeline.documents.classify import Classification, classify, detect_kind
from pay_pipeline.pdf_pipeline.ocr import READERS as OCR_READERS
from pay_pipeline.pdf_pipeline.read import READERS as TEXT_READERS

MAX_DOCS_PER_DISTRICT = 4
MAX_FOLDER_DOCS = 2
"""Document pages taken from folder pages per district, on top of ``MAX_DOCS_PER_DISTRICT``."""
MIN_CANDIDATE_SCORE = 2.0
MAX_DOC_BYTES = 40 * 1024 * 1024
KEEP_CANDIDATES = 15
EXTENSIONS = {"pdf": "pdf", "docx": "docx", "xlsx": "xlsx"}


@dataclass(frozen=True)
class QueueItem:
    district_id: int
    nces_id: str
    name: str
    state: str
    website: str | None
    enrollment: int | None = None
    seeds: tuple[str, ...] = ()  # schedule URLs found by hand (D-038), tried before discovery


@dataclass
class DocWork:
    url: str
    final_url: str
    sha256: str
    bytes: int
    kind: str
    asset_name: str
    fetched_at: str
    content_type: str | None
    known: bool
    classification: dict[str, Any]


@dataclass
class DistrictWork:
    district_id: int
    nces_id: str
    name: str
    state: str
    website: str | None
    status: str
    detail: str = ""
    pages_fetched: int = 0
    candidates: list[dict[str, Any]] = field(default_factory=list)
    docs: list[DocWork] = field(default_factory=list)
    chosen: str | None = None
    """asset_name of the document picked for extraction."""


def _now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def choose(docs: list[DocWork]) -> DocWork | None:
    """Best schedule document: classified as a schedule, latest school year, highest score."""
    usable = [d for d in docs if d.classification.get("is_candidate")]
    if not usable:
        return None
    return max(
        usable,
        key=lambda d: (
            d.classification.get("best_year") or "",
            not d.classification.get("scanned"),
            d.classification.get("score") or 0.0,
        ),
    )


_DRIVE_FILE = re.compile(r"^https://drive\.google\.com/file/d/([\w-]{10,})")
_DOCS = re.compile(
    r"^https://docs\.google\.com/(spreadsheets|document|presentation)/d/([\w-]{10,})"
)


def export_url(url: str) -> str:
    """Google Drive / Docs links point at viewers; ask for the file itself."""
    m = _DRIVE_FILE.match(url)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    m = _DOCS.match(url)
    if m:
        fmt = {"spreadsheets": "xlsx", "document": "docx", "presentation": "pdf"}[m.group(1)]
        return f"https://docs.google.com/{m.group(1)}/d/{m.group(2)}/export?format={fmt}"
    return url


def _looks_html(content_type: str, data: bytes) -> bool:
    head = data[:2000].lower()
    return "html" in content_type or b"<html" in head or b"<!doctype html" in head


_LANDING_HINTS = (
    "resource-manager/view",
    "/fs/resource-manager",
    "download",
    "/files/",
    "attachment",
)


_URL_IN_PAGE = re.compile(r"https?:(?://|\\/\\/)[^\s\"'<>]+")


def _urls_in_scripts(html: str) -> list[Link]:
    """File URLs written in scripts or JSON (viewers that render the link with JavaScript)."""
    out = []
    for raw in _URL_IN_PAGE.findall(html):
        url = raw.replace("\\/", "/").replace("\\u002F", "/").replace("&amp;", "&").rstrip("\\")
        if urlsplit(url).path.lower().endswith(DOC_EXTENSIONS) or is_document_url(url):
            out.append(Link(url, ""))
    return out


def landing_target(data: bytes, page_url: str, anchor: str) -> str | None:
    """The file a document landing page points to, or None."""
    ranked = landing_targets(data, page_url, anchor)
    return ranked[0] if ranked else None


def landing_targets(data: bytes, page_url: str, anchor: str) -> list[str]:
    """Files a page links to, most salary-like first."""
    html = data.decode("utf-8", errors="replace")
    links = extract_links(html, page_url) + _urls_in_scripts(html)
    files = [
        ln
        for ln in links
        if urlsplit(ln.url).path.lower().endswith(DOC_EXTENSIONS)
        or any(h in ln.url.lower() for h in _LANDING_HINTS)
        or (is_document_url(ln.url) and not same_site(ln.url, page_url))
    ]
    ranked = sorted(files, key=lambda ln: -score_document(Link(ln.url, ln.text or anchor)))
    return list(dict.fromkeys(ln.url for ln in ranked))


def folder_documents(data: bytes, page_url: str) -> list[Link]:
    """Same-site document pages listed on a folder page, most salary-like first."""
    html = data.decode("utf-8", errors="replace")
    links = [
        ln
        for ln in extract_links(html, page_url)
        if ln.url != page_url
        and same_site(ln.url, page_url)
        and is_document_url(ln.url)
        and score_document(ln) >= MIN_CANDIDATE_SCORE
    ]
    return sorted(links, key=lambda ln: (-score_document(ln), ln.url))


def known_documents(rows: Iterable[dict[str, Any]]) -> dict[str, set[str]]:
    """URL -> SHA-256 of documents already read by the current readers.

    A document read only by an older reader version is left out, so it is read again even if the
    file has not changed.
    """
    known: dict[str, set[str]] = {}
    for r in rows:
        if r.get("model") is not None and r["model"] not in TEXT_READERS | OCR_READERS:
            continue
        if r.get("scanned") and r.get("model") not in OCR_READERS:
            continue  # a scan set aside before OCR existed (D-036): read it again
        known.setdefault(str(r["url"]), set()).add(str(r["sha256"]))
    return known


MAX_SHARDS = 20  # GitHub Free runs at most 20 jobs at once
SEED_SCORE = 100.0
SEED_SOURCE = "schedule-urls.csv"
MAX_SEED_PAGE_DOCS = 6  # files tried from one hand-found page
SEED_CRAWL_PAGES = 8  # pages crawled from a hand-found page that links to no file


def load_seeds(path: Path | None) -> dict[str, tuple[str, ...]]:
    """``schedule-urls.csv`` (nces_id,url,note): NCES id -> schedule URLs, in file order (D-038)."""
    if path is None or not path.exists():
        return {}
    seeds: dict[str, list[str]] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            nces, url = (r.get("nces_id") or "").strip(), (r.get("url") or "").strip()
            if re.fullmatch(r"\d{7}", nces) and url.startswith(("https://", "http://")):
                seeds.setdefault(nces, []).append(url)
    return {k: tuple(v) for k, v in seeds.items()}


def website_host(website: str | None) -> str | None:
    """Host of a district website without ``www.``; None when there is no usable URL."""
    if not website:
        return None
    url = website if "://" in website else f"https://{website}"
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.") or None


def shard_queue(rows: list[dict[str, Any]], shards: int) -> list[list[dict[str, Any]]]:
    """Split the queue into ``shards`` parts that can run in parallel jobs.

    Every district on one website host goes to the same part, so the per-host throttle inside
    one job still covers every request to that host (no two jobs hit one site at once). Parts
    are filled greedily, smallest first, in queue order (largest districts first).
    """
    if not 1 <= shards <= MAX_SHARDS:
        raise ValueError(f"shards must be 1-{MAX_SHARDS}")
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        host = website_host(str(row["website"]) if row.get("website") else None)
        groups.setdefault(host or f"nces:{row['nces_id']}", []).append(row)
    parts: list[list[dict[str, Any]]] = [[] for _ in range(shards)]
    for group in groups.values():
        min(parts, key=len).extend(group)
    return parts


def website_variants(website: str) -> list[str]:
    """The listed address, then https and with/without "www." (NCES still lists many old
    ``http://www.`` addresses whose server no longer answers)."""
    parts = urlsplit(website if "://" in website else f"https://{website}")
    host = parts.netloc
    other = host[4:] if host.startswith("www.") else f"www.{host}"
    out = [website]
    for scheme, netloc in (("https", host), ("https", other), (parts.scheme, other)):
        url = urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))
        if url not in out:
            out.append(url)
    return out


def reachable_website(fetcher: PoliteFetcher, website: str | None) -> str | None:
    """First variant of ``website`` whose robots.txt can be retrieved.

    A robots.txt that cannot be fetched (network error, 5xx) means "disallowed" (RFC 9309), so
    the listed address is kept when no variant answers; the check is still the fetcher's.
    """
    if not website:
        return website
    for url in website_variants(website):
        if fetcher.robots.check(url).reachable:
            return url
    return website


def gather_one(
    item: QueueItem,
    fetcher: PoliteFetcher,
    docs_dir: Path,
    known: dict[str, set[str]],
    max_pages: int = 25,
) -> DistrictWork:
    work = DistrictWork(item.district_id, item.nces_id, item.name, item.state, item.website, "")
    picked: list[Candidate]
    if item.seeds:
        # A schedule URL found by hand: no crawl, so a home page that blocks bots or a website
        # that moved does not matter; the fetcher still obeys the document host's robots.txt.
        picked = [Candidate(u, SEED_SOURCE, "", "manual", SEED_SCORE) for u in item.seeds]
        work.candidates = [asdict(c) for c in picked]
    else:
        website = reachable_website(fetcher, item.website)
        if website != item.website:
            work.website = website
        found = discover(fetcher, item.nces_id, website, max_pages=max_pages)
        work.pages_fetched = found.pages_fetched
        work.candidates = [asdict(c) for c in found.candidates[:KEEP_CANDIDATES]]
        if found.status != "ok":
            work.status = found.status
            work.detail = "; ".join(found.errors[:2])[:500]
            return work
        picked = [c for c in found.candidates if c.score >= MIN_CANDIDATE_SCORE]
    if not picked:
        work.status = "no_candidates"
        work.detail = f"Đã đọc {found.pages_fetched} trang, không thấy tài liệu bảng lương"
        return work
    errors = []
    pending = list(picked[:MAX_DOCS_PER_DISTRICT])
    folder_budget = MAX_FOLDER_DOCS
    seed_budget = MAX_SEED_PAGE_DOCS
    while pending:
        cand = pending.pop(0)
        url = export_url(cand.url)
        try:
            response = fetcher.get(url)
            data = response.content
            kind = detect_kind(data)
            if kind not in EXTENSIONS and _looks_html(
                response.headers.get("content-type", ""), data
            ):
                if cand.found_on == SEED_SOURCE and seed_budget > 0:
                    # A page found by hand (an HR "Salary Schedules" page): its links carry the
                    # labels, so its most salary-like files are tried in turn, not only the first.
                    files = landing_targets(data, response.final_url, "")[:seed_budget]
                    seed_budget -= len(files)
                    pending[0:0] = [
                        Candidate(u, response.final_url, "", "manual", SEED_SCORE) for u in files
                    ]
                    if files:
                        continue
                    # No file on the page itself (Fairfax, Loudoun: the schedules sit on pages it
                    # links to): crawl a few pages from it, like a district website.
                    seed_budget = 0
                    found = discover(
                        fetcher, item.nces_id, response.final_url, max_pages=SEED_CRAWL_PAGES
                    )
                    work.pages_fetched += found.pages_fetched
                    deeper = [c for c in found.candidates if c.score >= MIN_CANDIDATE_SCORE]
                    pending[0:0] = deeper[:MAX_SEED_PAGE_DOCS]
                    if deeper:
                        continue
                # A document landing page (Finalsite "/documents/.../123456", viewers): follow the
                # best file link on it, one hop only.
                inner = landing_target(data, response.final_url, cand.anchor_text)
                if inner is not None:
                    response = fetcher.get(export_url(inner))
                    data = response.content
                    kind = detect_kind(data)
                elif folder_budget > 0:
                    # A folder of documents (Thrillshare "/documents/.../salary-schedules/826164"):
                    # its best document pages are tried next (D-027).
                    kids = folder_documents(data, response.final_url)[:folder_budget]
                    folder_budget -= len(kids)
                    pending[0:0] = [
                        Candidate(k.url, response.final_url, k.text, "folder", score_document(k))
                        for k in kids
                    ]
                    if kids:
                        continue
        except FetchError as exc:
            errors.append(f"{cand.url}: {exc}"[:200])
            continue
        if kind not in EXTENSIONS:
            errors.append(f"{cand.url}: không phải PDF/DOCX/XLSX")
            continue
        sha = hashlib.sha256(data).hexdigest()
        if any(d.sha256 == sha for d in work.docs):
            continue
        asset = f"{item.nces_id}-{sha[:12]}.{EXTENSIONS[kind]}"
        path = docs_dir / asset
        path.write_bytes(data)
        result: Classification = classify(path, data)
        work.docs.append(
            DocWork(
                url=cand.url,
                final_url=response.final_url,
                sha256=sha,
                bytes=len(data),
                kind=kind,
                asset_name=asset,
                fetched_at=_now(),
                content_type=response.headers.get("content-type"),
                known=sha in known.get(cand.url, set()),
                classification=asdict(result),
            )
        )
    best = choose(work.docs)
    if best is None:
        work.status = "no_schedule"
        work.detail = (
            f"Tải {len(work.docs)} tệp, không tệp nào giống bảng lương giáo viên. "
            + "; ".join(errors[:2])
        )[:500]
    elif best.known:
        work.status = "unchanged"
        work.chosen = best.asset_name
        work.detail = "Tài liệu đã xử lý trước đây, nội dung không đổi"
    else:
        work.status = "found"
        work.chosen = best.asset_name
        c = best.classification
        work.detail = f"{best.url} (năm {c.get('best_year')}, trang {c.get('schedule_pages')})"
    return work


def gather(
    queue: list[QueueItem],
    out_dir: Path,
    known: dict[str, set[str]],
    user_agent: str,
    *,
    workers: int = 16,
    deadline_seconds: float = 40 * 60,
    min_delay_seconds: float = 2.0,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[DistrictWork]:
    docs_dir = out_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    policy = CrawlPolicy(user_agent=user_agent, min_delay_seconds=min_delay_seconds)
    throttle = SharedThrottle(policy, sleep=sleep)
    start = time.monotonic()
    results: dict[str, DistrictWork] = {}
    lock = threading.Lock()

    def run(item: QueueItem) -> None:
        if time.monotonic() - start > deadline_seconds:
            return  # not started: stays in the queue for the next run
        with SharedPoliteFetcher(
            throttle, transport=transport, sleep=sleep, max_bytes=MAX_DOC_BYTES, max_retries=1
        ) as fetcher:
            try:
                work = gather_one(item, fetcher, docs_dir, known)
            except Exception as exc:  # one district must not stop the batch
                work = DistrictWork(
                    item.district_id, item.nces_id, item.name, item.state, item.website,
                    "error", f"{type(exc).__name__}: {exc}"[:500],
                )  # fmt: skip
        with lock:
            results[item.nces_id] = work

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(run, queue))
    ordered = [results[i.nces_id] for i in queue if i.nces_id in results]
    write_outputs(out_dir, ordered)
    return ordered


def write_outputs(out_dir: Path, works: list[DistrictWork]) -> None:
    (out_dir / "work.json").write_text(
        json.dumps([asdict(w) for w in works], indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    files = [
        {"name": d.asset_name, "url": d.url, "final_url": d.final_url, "sha256": d.sha256,
         "bytes": d.bytes, "fetched_at": d.fetched_at, "content_type": d.content_type}
        for w in works for d in w.docs
    ]  # fmt: skip
    record = {"release_prefix": "docs", "description": "Tài liệu học khu tải bởi pipeline PDF",
              "files": files, "failed": []}  # fmt: skip
    (out_dir / "docs" / "manifest.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def load_work(out_dir: Path) -> list[DistrictWork]:
    raw = json.loads((out_dir / "work.json").read_text(encoding="utf-8"))
    works = []
    for w in raw:
        docs = [DocWork(**d) for d in w.pop("docs")]
        works.append(DistrictWork(**w, docs=docs))
    return works
