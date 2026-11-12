"""Command line: ``pay-pipeline <command>``."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from pay_pipeline import __version__
from pay_pipeline.acquisition.http import PoliteFetcher
from pay_pipeline.acquisition.policy import CrawlPolicy
from pay_pipeline.sources import fetch_sources, load_manifest, required_failures

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pay-pipeline")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("fetch-sources", help="Tải các tệp nguồn kê khai trong một tệp JSON")
    p.add_argument("manifest", help="Tệp kê khai, vd. pipeline/sources/nces-ccd-2425.json")
    p.add_argument("--out", required=True, help="Thư mục đầu ra (phải trống)")
    p.set_defaults(func=_cmd_fetch_sources)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
