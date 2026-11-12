"""Download a declared list of public source files and record their provenance.

A *source manifest* (JSON, committed under ``pipeline/sources/``) names the files: only URLs
listed there are fetched, through :class:`PoliteFetcher` (robots.txt, rate limit). Each run
writes the files plus ``manifest.json`` (URL, final URL, fetch time, SHA-256, size) into an
output directory; the workflow then attaches that directory to a GitHub Release (D-011).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pay_pipeline.acquisition.http import FetchError, PoliteFetcher


@dataclass(frozen=True)
class SourceFile:
    url: str
    name: str
    """File name to store under (defaults to the last URL path segment)."""
    optional: bool = False
    """An optional file may be missing (e.g. a table not yet published); others must succeed."""
    note: str = ""


@dataclass(frozen=True)
class SourceManifest:
    release_prefix: str
    description: str
    files: tuple[SourceFile, ...]


@dataclass(frozen=True)
class FetchedFile:
    name: str
    url: str
    final_url: str
    fetched_at: str
    sha256: str
    bytes: int
    content_type: str | None


@dataclass(frozen=True)
class FailedFile:
    name: str
    url: str
    optional: bool
    error: str


def load_manifest(path: Path) -> SourceManifest:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    files = []
    names: set[str] = set()
    for entry in data["files"]:
        url = str(entry["url"])
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.netloc:
            raise ValueError(f"Chỉ nhận URL https đầy đủ: {url}")
        name = str(entry.get("name") or parts.path.rsplit("/", 1)[-1])
        if not name or "/" in name or name.startswith("."):
            raise ValueError(f"Tên tệp không hợp lệ cho {url}: {name!r}")
        if name in names:
            raise ValueError(f"Tên tệp trùng: {name}")
        names.add(name)
        files.append(
            SourceFile(
                url=url,
                name=name,
                optional=bool(entry.get("optional", False)),
                note=str(entry.get("note", "")),
            )
        )
    if not files:
        raise ValueError("Tệp kê khai không có tệp nào")
    return SourceManifest(
        release_prefix=str(data["release_prefix"]),
        description=str(data.get("description", "")),
        files=tuple(files),
    )


def fetch_sources(
    manifest: SourceManifest,
    out_dir: Path,
    fetcher: PoliteFetcher,
    now: dt.datetime | None = None,
) -> tuple[list[FetchedFile], list[FailedFile]]:
    """Fetch every file of ``manifest`` into ``out_dir`` (must be empty or absent)."""
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(f"Thư mục đầu ra phải trống: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    fetched: list[FetchedFile] = []
    failed: list[FailedFile] = []
    for source in manifest.files:
        try:
            response = fetcher.get(source.url)
        except FetchError as exc:
            failed.append(FailedFile(source.name, source.url, source.optional, str(exc)))
            continue
        content = response.content
        (out_dir / source.name).write_bytes(content)
        when = now or dt.datetime.now(dt.UTC)
        fetched.append(
            FetchedFile(
                name=source.name,
                url=source.url,
                final_url=response.final_url,
                fetched_at=when.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                sha256=hashlib.sha256(content).hexdigest(),
                bytes=len(content),
                content_type=response.headers.get("content-type"),
            )
        )
    record = {
        "release_prefix": manifest.release_prefix,
        "description": manifest.description,
        "files": [asdict(f) for f in fetched],
        "failed": [asdict(f) for f in failed],
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return fetched, failed


def required_failures(failed: list[FailedFile]) -> list[FailedFile]:
    return [f for f in failed if not f.optional]
