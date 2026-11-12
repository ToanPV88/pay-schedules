"""Command line: ``pay-pipeline <command>``."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from pay_pipeline import __version__
from pay_pipeline.acquisition.http import PoliteFetcher
from pay_pipeline.acquisition.policy import CrawlPolicy
from pay_pipeline.catalog.d1sql import catalog_sql, render_sql
from pay_pipeline.catalog.districts import build_catalog, render_report
from pay_pipeline.pdf_pipeline import gather as pdf_gather
from pay_pipeline.pdf_pipeline import run as pdf_run
from pay_pipeline.schedules import state_import
from pay_pipeline.schedules.d1sql import schedules_sql
from pay_pipeline.sources import fetch_sources, load_manifest, required_failures, verify_sources

DEFAULT_USER_AGENT = f"pay-schedules/{__version__} (+https://github.com/ToanPV88/pay-schedules)"


def user_agent() -> str:
    return os.environ.get("PAY_USER_AGENT") or DEFAULT_USER_AGENT


def _cmd_fetch_sources(args: argparse.Namespace) -> int:
    manifest = load_manifest(Path(args.manifest))
    policy = CrawlPolicy(user_agent=user_agent())
    with PoliteFetcher(policy) as fetcher:
        fetched, failed = fetch_sources(manifest, Path(args.out), fetcher)
    for ok in fetched:
        print(f"OK   {ok.name}  {ok.bytes:>12,} B  sha256={ok.sha256}")
    for bad in failed:
        tag = "SKIP" if bad.optional else "FAIL"
        print(f"{tag} {bad.name}  {bad.error}")
    return 1 if required_failures(failed) else 0


def _cmd_verify_sources(args: argparse.Namespace) -> int:
    problems = verify_sources(Path(args.directory))
    for problem in problems:
        print(problem)
    if not problems:
        print("Mọi tệp khớp SHA-256 trong manifest.json")
    return 1 if problems else 0


def load_existing_slugs(path: Path | None) -> dict[str, tuple[str, str]]:
    """Read ``SELECT nces_id, state, slug`` output of ``wrangler d1 execute --json``."""
    if path is None:
        return {}
    if not path.exists():
        raise FileNotFoundError(f"Không thấy tệp slug hiện có: {path}")
    data = json.loads(path.read_text(encoding="utf-8") or "[]")
    rows: list[dict[str, object]] = []
    for item in data if isinstance(data, list) else [data]:
        if isinstance(item, dict) and "results" in item:
            rows.extend(item["results"])
        elif isinstance(item, dict):
            rows.append(item)
    return {str(r["nces_id"]): (str(r["state"]), str(r["slug"])) for r in rows if r.get("nces_id")}


def _cmd_districts_build(args: argparse.Namespace) -> int:
    sources = Path(args.sources)
    catalog = build_catalog(
        sources, load_existing_slugs(Path(args.existing) if args.existing else None)
    )
    provenance = []
    manifest = sources / "manifest.json"
    if manifest.exists():
        provenance = json.loads(manifest.read_text(encoding="utf-8")).get("files", [])
    Path(args.sql).write_text(render_sql(catalog_sql(catalog)), encoding="utf-8")
    Path(args.report).write_text(render_report(catalog, provenance), encoding="utf-8")
    print(f"{len(catalog.districts):,} học khu, {len(catalog.neighbors):,} cặp lân cận")
    return 0


def _cmd_schedules_build(args: argparse.Namespace) -> int:
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(dt.UTC).date()
    result = state_import.build_import(
        sources=Path(args.sources),
        ccd_dir=Path(args.ccd),
        catalog=state_import.load_catalog(Path(args.catalog)),
        published=state_import.load_published(Path(args.published) if args.published else None),
        release_tag=args.release_tag,
        today=today,
        ky_years=args.ky_years,
        holds=state_import.load_holds(Path(args.holds) if args.holds else None),
    )
    Path(args.sql).write_text(render_sql(schedules_sql(result)), encoding="utf-8")
    Path(args.report).write_text(state_import.render_report(result), encoding="utf-8")
    published = sum(p.status == "published" for p in result.prepared)
    print(
        f"{len(result.prepared):,} bảng lương ({published:,} published,"
        f" {len(result.prepared) - published:,} chờ xem tay), {len(result.skipped):,} bỏ qua"
    )
    return 0


def _wrangler_rows(path: Path) -> list[dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8") or "[]")
    rows: list[dict[str, object]] = []
    for item in data if isinstance(data, list) else [data]:
        if isinstance(item, dict) and "results" in item:
            rows.extend(item["results"])
        elif isinstance(item, dict):
            rows.append(item)
    return rows


def _cmd_pdf_gather(args: argparse.Namespace) -> int:
    queue = [
        pdf_gather.QueueItem(
            district_id=int(str(r["district_id"])),
            nces_id=str(r["nces_id"]),
            name=str(r["name"]),
            state=str(r["state"]),
            website=str(r["website"]) if r.get("website") else None,
            enrollment=int(str(r["enrollment"])) if r.get("enrollment") is not None else None,
        )
        for r in _wrangler_rows(Path(args.queue))
    ]
    known = pdf_gather.known_documents(_wrangler_rows(Path(args.known)) if args.known else [])
    works = pdf_gather.gather(
        queue, Path(args.out), known, user_agent(), workers=args.workers,
        deadline_seconds=args.deadline_minutes * 60,
    )  # fmt: skip
    counts: dict[str, int] = {}
    for w in works:
        counts[w.status] = counts.get(w.status, 0) + 1
    print(f"{len(works)}/{len(queue)} học khu: {counts}")
    return 0


def _cmd_pdf_extract(args: argparse.Namespace) -> int:
    work_dir = Path(args.work)
    results = pdf_run.read_all(pdf_gather.load_work(work_dir), work_dir)
    ok = sum(
        1 for v in results.values()
        if json.loads(v["runs"][0]["raw_output"]).get("is_teacher_salary_schedule")
    )  # fmt: skip
    print(f"Đã đọc {len(results)} tài liệu, {ok} có bảng bậc × lane")
    return 0


def _cmd_pdf_build(args: argparse.Namespace) -> int:
    work_dir = Path(args.work)
    works = pdf_gather.load_work(work_dir)
    path = work_dir / "extractions.json"
    extractions = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    now = dt.datetime.now(dt.UTC)
    result, outcomes = pdf_run.prepare(
        works,
        extractions,
        state_import.load_catalog(Path(args.catalog)),
        state_import.load_published(Path(args.published) if args.published else None),
        args.release_tag,
        now.date(),
    )
    statements = schedules_sql(result, now) + pdf_run.pipeline_sql(
        works, outcomes, args.run_key, now
    )
    Path(args.sql).write_text(render_sql(statements), encoding="utf-8")
    Path(args.report).write_text(
        pdf_run.render_report(works, outcomes, args.run_key), encoding="utf-8"
    )
    print(f"{len(outcomes)} học khu, {len(result.prepared)} bảng lương")
    return 0


def _cmd_pdf_eval(args: argparse.Namespace) -> int:
    from pay_pipeline.pdf_pipeline import gold

    golds = gold.load_gold(Path(args.gold))
    results = gold.evaluate(golds, Path(args.docs), today=dt.datetime.now(dt.UTC).date())
    report = gold.render(results)
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(report, encoding="utf-8")
    print(report.split("\n\n")[1])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pay-pipeline")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("fetch-sources", help="Tải các tệp nguồn kê khai trong một tệp JSON")
    p.add_argument("manifest", help="Tệp kê khai, vd. pipeline/sources/nces-ccd-2425.json")
    p.add_argument("--out", required=True, help="Thư mục đầu ra (phải trống)")
    p.set_defaults(func=_cmd_fetch_sources)

    p = sub.add_parser("verify-sources", help="Kiểm SHA-256 các tệp theo manifest.json")
    p.add_argument("directory")
    p.set_defaults(func=_cmd_verify_sources)

    p = sub.add_parser("districts-build", help="Dựng danh mục học khu từ tệp NCES CCD")
    p.add_argument("--sources", required=True, help="Thư mục chứa tệp của Release nguồn")
    p.add_argument("--existing", help="JSON slug hiện có trong D1 (wrangler d1 execute --json)")
    p.add_argument("--sql", required=True, help="Tệp SQL đầu ra để nạp vào D1")
    p.add_argument("--report", required=True, help="Báo cáo Markdown đầu ra")
    p.set_defaults(func=_cmd_districts_build)

    p = sub.add_parser("schedules-build", help="Nhập bảng lương do bang công bố (CA J-90, KY)")
    p.add_argument("--sources", required=True, help="Thư mục tệp của Release src-state-salaries-*")
    p.add_argument("--ccd", required=True, help="Thư mục tệp của Release src-nces-ccd-*")
    p.add_argument("--catalog", required=True, help="JSON học khu trong D1 (wrangler --json)")
    p.add_argument("--published", help="JSON bảng lương đang published trong D1")
    p.add_argument("--release-tag", required=True, help="Tag Release chứa tệp nguồn")
    p.add_argument("--ky-years", type=int, default=state_import.KY_YEARS)
    p.add_argument("--holds", help="JSON các bảng giữ lại để xem tay (kiểm tra chéo phát hiện sai)")
    p.add_argument("--today", help="Ngày chạy (YYYY-MM-DD), mặc định hôm nay theo UTC")
    p.add_argument("--sql", required=True, help="Tệp SQL đầu ra")
    p.add_argument("--report", required=True, help="Báo cáo Markdown đầu ra")
    p.set_defaults(func=_cmd_schedules_build)

    p = sub.add_parser("pdf-gather", help="Pipeline PDF: Discover, Fetch, Classify một lô")
    p.add_argument("--queue", required=True, help="JSON hàng đợi từ D1 (wrangler --json)")
    p.add_argument("--known", help="JSON tài liệu đã xử lý (url, sha256, model)")
    p.add_argument("--out", required=True, help="Thư mục làm việc")
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--deadline-minutes", type=float, default=40)
    p.set_defaults(func=_cmd_pdf_gather)

    p = sub.add_parser("pdf-extract", help="Pipeline PDF: đọc bảng lương (tất định, không API)")
    p.add_argument("--work", required=True)
    p.set_defaults(func=_cmd_pdf_extract)

    p = sub.add_parser("pdf-build", help="Pipeline PDF: Validate, SQL cho D1, báo cáo")
    p.add_argument("--work", required=True)
    p.add_argument("--catalog", required=True)
    p.add_argument("--published")
    p.add_argument("--release-tag", required=True)
    p.add_argument("--run-key", required=True)
    p.add_argument("--sql", required=True)
    p.add_argument("--report", required=True)
    p.set_defaults(func=_cmd_pdf_build)

    p = sub.add_parser("pdf-eval", help="Chạy pipeline trên bộ chuẩn và đo độ chính xác")
    p.add_argument("--gold", required=True, help="Thư mục pipeline/gold")
    p.add_argument("--docs", required=True, help="Thư mục chứa tài liệu của bộ chuẩn")
    p.add_argument("--report", required=True)
    p.set_defaults(func=_cmd_pdf_eval)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
