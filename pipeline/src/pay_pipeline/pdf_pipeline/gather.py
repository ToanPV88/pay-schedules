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
from pay_pipeline.discover.crawl import Candidate, discover
from pay_pipeline.documents.classify import Classification, classify, detect_kind

MAX_DOCS_PER_DISTRICT = 4
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


def gather_one(
    item: QueueItem,
    fetcher: PoliteFetcher,
    docs_dir: Path,
    known: dict[str, set[str]],
    max_pages: int = 20,
) -> DistrictWork:
    work = DistrictWork(item.district_id, item.nces_id, item.name, item.state, item.website, "")
    found = discover(fetcher, item.nces_id, item.website, max_pages=max_pages)
    work.pages_fetched = found.pages_fetched
    work.candidates = [asdict(c) for c in found.candidates[:KEEP_CANDIDATES]]
    if found.status != "ok":
        work.status = found.status
        work.detail = "; ".join(found.errors[:2])[:500]
        return work
    picked: list[Candidate] = [c for c in found.candidates if c.score >= MIN_CANDIDATE_SCORE]
    if not picked:
        work.status = "no_candidates"
        work.detail = f"Đã đọc {found.pages_fetched} trang, không thấy tài liệu bảng lương"
        return work
    errors = []
    for cand in picked[:MAX_DOCS_PER_DISTRICT]:
        try:
            response = fetcher.get(cand.url)
        except FetchError as exc:
            errors.append(f"{cand.url}: {exc}"[:200])
            continue
        data = response.content
        kind = detect_kind(data)
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
