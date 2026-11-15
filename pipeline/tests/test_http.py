"""Polite fetcher tests, copied from travienphi. Offline: httpx.MockTransport + fake clock.

All hosts are under example.invalid; all content is synthetic.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from pay_pipeline.acquisition.http import (
    BudgetExceededError,
    HttpStatusError,
    NetworkError,
    PoliteFetcher,
    RobotsDisallowedError,
    TooLargeError,
)
from pay_pipeline.acquisition.policy import CrawlPolicy

UA = "pay-schedules/0.1 (+https://example.invalid/about)"
HOST = "https://district-a.example.invalid"
ALLOW_ALL = "User-agent: *\nAllow: /\n"

Handler = Callable[[httpx.Request], httpx.Response]


class FakeWeb:
    """Routes keyed by full URL (scheme+host+path[+query]); records every request."""

    def __init__(self, routes: dict[str, Handler | httpx.Response]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = str(request.url)
        route = self.routes.get(key)
        if route is None:
            return httpx.Response(404, text="not found")
        return route(request) if callable(route) else route

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def urls(self) -> list[str]:
        return [str(r.url) for r in self.requests]


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


def make_fetcher(web: FakeWeb, clock: FakeClock | None = None, **kw: Any) -> PoliteFetcher:
    c = clock or FakeClock()
    policy = CrawlPolicy(
        user_agent=UA,
        min_delay_seconds=kw.pop("min_delay", 5.0),
        max_requests_per_host_per_run=kw.pop("budget", 200),
    )
    return PoliteFetcher(policy, transport=web.transport, sleep=c.sleep, clock=c.clock, **kw)


class TestPoliteFetcher:
    def test_checks_robots_before_fetching_and_caches_it(self) -> None:
        web = FakeWeb(
            {
                f"{HOST}/robots.txt": httpx.Response(200, text=ALLOW_ALL),
                f"{HOST}/a": httpx.Response(200, content=b"A"),
                f"{HOST}/b": httpx.Response(200, content=b"B"),
            }
        )
        with make_fetcher(web) as f:
            assert f.get(f"{HOST}/a").content == b"A"
            assert f.get(f"{HOST}/b").content == b"B"
        assert web.urls() == [f"{HOST}/robots.txt", f"{HOST}/a", f"{HOST}/b"]
        assert all(r.headers["user-agent"] == UA for r in web.requests)

    def test_disallowed_url_is_never_requested(self) -> None:
        web = FakeWeb(
            {
                f"{HOST}/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /\n"),
                f"{HOST}/a": httpx.Response(200, content=b"A"),
            }
        )
        with make_fetcher(web) as f, pytest.raises(RobotsDisallowedError):
            f.get(f"{HOST}/a")
        assert f"{HOST}/a" not in web.urls()

    def test_robots_server_error_means_disallow(self) -> None:
        web = FakeWeb({f"{HOST}/robots.txt": httpx.Response(503)})
        with make_fetcher(web, max_retries=0) as f, pytest.raises(RobotsDisallowedError):
            f.get(f"{HOST}/a")

    def test_missing_robots_means_allow(self) -> None:
        web = FakeWeb({f"{HOST}/a": httpx.Response(200, content=b"A")})
        with make_fetcher(web) as f:
            r = f.get(f"{HOST}/a")
        assert r.robots is not None and "404" in r.robots.reason

    def test_rate_limit_per_host(self) -> None:
        clock = FakeClock()
        web = FakeWeb(
            {
                f"{HOST}/robots.txt": httpx.Response(200, text=ALLOW_ALL),
                f"{HOST}/a": httpx.Response(200, content=b"A"),
                f"{HOST}/b": httpx.Response(200, content=b"B"),
            }
        )
        with make_fetcher(web, clock, min_delay=5.0) as f:
            f.get(f"{HOST}/a")
            f.get(f"{HOST}/b")
        assert clock.sleeps == [5.0, 5.0]  # robots->a, a->b

    def test_request_budget_per_host(self) -> None:
        web = FakeWeb({f"{HOST}/a": httpx.Response(200, content=b"A")})
        with make_fetcher(web, budget=2) as f:
            f.get(f"{HOST}/a")  # robots (404) + a = 2 requests
            with pytest.raises(BudgetExceededError):
                f.get(f"{HOST}/a")

    def test_retries_on_503_and_honours_retry_after(self) -> None:
        clock = FakeClock()
        calls = {"n": 0}

        def flaky(_: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(503, headers={"Retry-After": "7"})
            return httpx.Response(200, content=b"ok")

        web = FakeWeb(
            {f"{HOST}/robots.txt": httpx.Response(200, text=ALLOW_ALL), f"{HOST}/a": flaky}
        )
        with make_fetcher(web, clock, min_delay=1.0) as f:
            assert f.get(f"{HOST}/a").content == b"ok"
        assert 7.0 in clock.sleeps

    def test_retry_after_is_capped(self) -> None:
        clock = FakeClock()
        web = FakeWeb(
            {
                f"{HOST}/robots.txt": httpx.Response(200, text=ALLOW_ALL),
                f"{HOST}/a": httpx.Response(429, headers={"Retry-After": "99999"}),
            }
        )
        with make_fetcher(web, clock, max_retries=1) as f, pytest.raises(HttpStatusError):
            f.get(f"{HOST}/a")
        assert max(clock.sleeps) == 60.0

    def test_gives_up_after_max_retries(self) -> None:
        web = FakeWeb(
            {
                f"{HOST}/robots.txt": httpx.Response(200, text=ALLOW_ALL),
                f"{HOST}/a": httpx.Response(500),
            }
        )
        with make_fetcher(web, max_retries=2) as f, pytest.raises(HttpStatusError) as exc:
            f.get(f"{HOST}/a")
        assert exc.value.status_code == 500
        assert web.urls().count(f"{HOST}/a") == 3

    def test_network_error_after_retries(self) -> None:
        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        web = FakeWeb(
            {f"{HOST}/robots.txt": httpx.Response(200, text=ALLOW_ALL), f"{HOST}/a": boom}
        )
        with make_fetcher(web, max_retries=1) as f, pytest.raises(NetworkError):
            f.get(f"{HOST}/a")

    def test_size_limit_by_header_and_by_stream(self) -> None:
        web = FakeWeb(
            {
                f"{HOST}/robots.txt": httpx.Response(200, text=ALLOW_ALL),
                f"{HOST}/big": httpx.Response(200, content=b"x" * 2000),
            }
        )
        with make_fetcher(web, max_bytes=1000) as f, pytest.raises(TooLargeError):
            f.get(f"{HOST}/big")

    def test_redirect_is_robots_checked_on_each_hop(self) -> None:
        other = "https://cdn.example.invalid"
        web = FakeWeb(
            {
                f"{HOST}/robots.txt": httpx.Response(200, text=ALLOW_ALL),
                f"{HOST}/a": httpx.Response(302, headers={"Location": f"{other}/private/a.pdf"}),
                f"{other}/robots.txt": httpx.Response(
                    200, text="User-agent: *\nDisallow: /private/\n"
                ),
            }
        )
        with make_fetcher(web) as f, pytest.raises(RobotsDisallowedError):
            f.get(f"{HOST}/a")
        assert f"{other}/private/a.pdf" not in web.urls()

    def test_redirect_followed_and_recorded(self) -> None:
        web = FakeWeb(
            {
                f"{HOST}/robots.txt": httpx.Response(200, text=ALLOW_ALL),
                f"{HOST}/a": httpx.Response(301, headers={"Location": "/b"}),
                f"{HOST}/b": httpx.Response(200, content=b"B"),
            }
        )
        with make_fetcher(web) as f:
            r = f.get(f"{HOST}/a")
        assert r.final_url == f"{HOST}/b" and r.redirects == (f"{HOST}/b",)

    def test_credential_header_dropped_on_redirect_to_another_host(self) -> None:
        other = "https://cdn.example.invalid"
        seen: dict[str, str | None] = {}

        def capture(name: str, response: httpx.Response):  # type: ignore[no-untyped-def]
            def handler(request: httpx.Request) -> httpx.Response:
                seen[name] = request.headers.get("x-goog-api-key")
                return response

            return handler

        web = FakeWeb(
            {
                f"{HOST}/robots.txt": httpx.Response(200, text=ALLOW_ALL),
                f"{HOST}/a": capture("a", httpx.Response(302, headers={"Location": f"{HOST}/b"})),
                f"{HOST}/b": capture(
                    "b", httpx.Response(302, headers={"Location": f"{other}/c.pdf"})
                ),
                f"{other}/robots.txt": httpx.Response(200, text=ALLOW_ALL),
                f"{other}/c.pdf": capture("c", httpx.Response(200, content=b"%PDF")),
            }
        )
        with make_fetcher(web) as f:
            f.get(f"{HOST}/a", headers={"X-goog-api-key": "k"})
        assert seen == {"a": "k", "b": "k", "c": None}

    def test_too_many_redirects(self) -> None:
        web = FakeWeb(
            {
                f"{HOST}/robots.txt": httpx.Response(200, text=ALLOW_ALL),
                f"{HOST}/a": httpx.Response(302, headers={"Location": "/a"}),
            }
        )
        with make_fetcher(web, max_redirects=2) as f, pytest.raises(HttpStatusError):
            f.get(f"{HOST}/a")

    def test_http_404_is_an_error(self) -> None:
        web = FakeWeb({f"{HOST}/robots.txt": httpx.Response(200, text=ALLOW_ALL)})
        with make_fetcher(web) as f, pytest.raises(HttpStatusError) as exc:
            f.get(f"{HOST}/missing")
        assert exc.value.status_code == 404
