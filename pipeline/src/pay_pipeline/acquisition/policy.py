"""Collection policy: what we are allowed to fetch, and how politely.

No network I/O lives here. Copied from travienphi (docs/REUSE_AUDIT.md §8: "Giữ").
Defaults stay conservative: 5 seconds between requests to one host (PLAN allows at
most one per second); robots.txt can never be switched off.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from pay_pipeline.acquisition.robots import is_allowed


@dataclass(frozen=True)
class CrawlPolicy:
    user_agent: str
    min_delay_seconds: float = 5.0
    max_requests_per_host_per_run: int = 200
    respect_robots_txt: bool = True
    allowed_schemes: tuple[str, ...] = ("https", "http")

    def __post_init__(self) -> None:
        if not self.user_agent.strip():
            raise ValueError("Cần user_agent định danh dự án và cách liên hệ")
        if self.min_delay_seconds < 1.0:
            raise ValueError("min_delay_seconds phải >= 1 giây")
        if not self.respect_robots_txt:
            raise ValueError("Không được tắt tôn trọng robots.txt")


def robots_allows(robots_txt: str, url: str, user_agent: str) -> bool:
    """Evaluate a robots.txt body (already fetched) for ``url`` (RFC 9309)."""
    return is_allowed(robots_txt, url, user_agent)


def is_url_in_scope(url: str, policy: CrawlPolicy) -> bool:
    parts = urlsplit(url)
    return parts.scheme in policy.allowed_schemes and bool(parts.netloc)
