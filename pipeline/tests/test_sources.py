"""Source manifest + fetch tests. Offline: httpx.MockTransport; hosts under example.invalid."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from pay_pipeline.acquisition.http import PoliteFetcher
from pay_pipeline.acquisition.policy import CrawlPolicy
from pay_pipeline.sources import fetch_sources, load_manifest, required_failures

UA = "pay-schedules/0.1 (+https://example.invalid/about)"
HOST = "https://stats.example.invalid"
NOW = dt.datetime(2026, 11, 12, 8, 0, tzinfo=dt.UTC)
REPO = Path(__file__).resolve().parents[2]


def write_manifest(tmp_path: Path, files: list[dict[str, object]]) -> Path:
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"release_prefix": "src-test", "files": files}), encoding="utf-8")
    return path


def fetcher(routes: dict[str, httpx.Response]) -> PoliteFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(str(request.url), httpx.Response(404))

    return PoliteFetcher(
        CrawlPolicy(user_agent=UA, min_delay_seconds=1.0),
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
        max_retries=0,
    )


class TestManifest:
    def test_committed_manifests_load(self) -> None:
        paths = sorted((REPO / "pipeline" / "sources").glob("*.json"))
        assert paths
        for path in paths:
            m = load_manifest(path)
            assert m.release_prefix.startswith("src-")
            assert all(f.url.startswith("https://") for f in m.files)

    def test_name_defaults_to_last_path_segment(self, tmp_path: Path) -> None:
        m = load_manifest(write_manifest(tmp_path, [{"url": f"{HOST}/data/a.zip"}]))
        assert m.files[0].name == "a.zip"

    @pytest.mark.parametrize(
        "files",
        [
            [{"url": "http://stats.example.invalid/a.zip"}],
            [{"url": f"{HOST}/a.zip"}, {"url": f"{HOST}/b/a.zip"}],
            [{"url": f"{HOST}/a.zip", "name": "../x"}],
            [],
        ],
    )
    def test_rejects_bad_manifests(self, tmp_path: Path, files: list[dict[str, object]]) -> None:
        with pytest.raises(ValueError):
            load_manifest(write_manifest(tmp_path, files))


class TestFetchSources:
    def test_writes_files_and_provenance(self, tmp_path: Path) -> None:
        m = load_manifest(
            write_manifest(
                tmp_path,
                [{"url": f"{HOST}/a.zip"}, {"url": f"{HOST}/t.asp", "name": "t.html"}],
            )
        )
        routes = {
            f"{HOST}/robots.txt": httpx.Response(200, text="User-agent: *\nAllow: /\n"),
            f"{HOST}/a.zip": httpx.Response(200, content=b"zip-bytes"),
            f"{HOST}/t.asp": httpx.Response(200, content=b"<table></table>"),
        }
        out = tmp_path / "out"
        with fetcher(routes) as f:
            fetched, failed = fetch_sources(m, out, f, now=NOW)
        assert not failed
        assert (out / "a.zip").read_bytes() == b"zip-bytes"
        assert (out / "t.html").read_bytes() == b"<table></table>"
        record = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        a = record["files"][0]
        assert a["sha256"] == hashlib.sha256(b"zip-bytes").hexdigest()
        assert a["fetched_at"] == "2026-11-12T08:00:00Z"
        assert a["url"] == f"{HOST}/a.zip"
        assert len(fetched) == 2

    def test_optional_missing_file_is_not_fatal(self, tmp_path: Path) -> None:
        m = load_manifest(
            write_manifest(
                tmp_path,
                [{"url": f"{HOST}/a.zip"}, {"url": f"{HOST}/later.asp", "optional": True}],
            )
        )
        routes = {f"{HOST}/a.zip": httpx.Response(200, content=b"A")}
        with fetcher(routes) as f:
            _, failed = fetch_sources(m, tmp_path / "out", f, now=NOW)
        assert [x.name for x in failed] == ["later.asp"]
        assert required_failures(failed) == []

    def test_required_missing_file_is_reported(self, tmp_path: Path) -> None:
        m = load_manifest(write_manifest(tmp_path, [{"url": f"{HOST}/gone.zip"}]))
        with fetcher({}) as f:
            _, failed = fetch_sources(m, tmp_path / "out", f, now=NOW)
        assert [x.name for x in required_failures(failed)] == ["gone.zip"]

    def test_refuses_non_empty_output(self, tmp_path: Path) -> None:
        m = load_manifest(write_manifest(tmp_path, [{"url": f"{HOST}/a.zip"}]))
        out = tmp_path / "out"
        out.mkdir()
        (out / "old").write_text("x")
        with fetcher({}) as f, pytest.raises(FileExistsError):
            fetch_sources(m, out, f, now=NOW)
