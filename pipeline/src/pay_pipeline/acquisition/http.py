"""Polite HTTP fetching. Copied from travienphi (docs/REUSE_AUDIT.md §8, "Sửa").

Guarantees for every request made through :class:`PoliteFetcher`:

* robots.txt is checked (RFC 9309) for the URL and for every redirect hop;
* at least ``policy.min_delay_seconds`` between requests to the same host;
* at most ``policy.max_requests_per_host_per_run`` requests per host;
* bounded retries for transient failures, honouring ``Retry-After`` (capped);
* bodies larger than ``max_bytes`` are aborted, never stored.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit

import httpx

from pay_pipeline.acquisition.policy import CrawlPolicy, is_url_in_scope
from pay_pipeline.acquisition.robots import RobotsCache, RobotsDecision

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
ROBOTS_MAX_BYTES = 512 * 1024


class FetchError(Exception):
    code = "fetch_error"

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RobotsDisallowedError(FetchError):
    code = "robots_disallowed"

    def __init__(self, decision: RobotsDecision, url: str) -> None:
        super().__init__(f"{url}: {decision.reason}")
        self.decision = decision


class OutOfScopeError(FetchError):
    code = "out_of_scope"


class BudgetExceededError(FetchError):
    code = "budget_exceeded"


class TooLargeError(FetchError):
    code = "too_large"


class HttpStatusError(FetchError):
    code = "http_error"


class NetworkError(FetchError):
    code = "network_error"


@dataclass(frozen=True)
class FetchedResponse:
    requested_url: str
    final_url: str
    status_code: int
    headers: Mapping[str, str]
    content: bytes
    redirects: tuple[str, ...] = ()
    robots: RobotsDecision | None = None

    @property
    def not_modified(self) -> bool:
        return self.status_code == 304


@dataclass
class _HostState:
    last_request: dict[str, float] = field(default_factory=dict)
    count: Counter[str] = field(default_factory=Counter)


class PoliteFetcher:
    def __init__(
        self,
        policy: CrawlPolicy,
        *,
        transport: httpx.BaseTransport | None = None,
        max_bytes: int = 100 * 1024 * 1024,  # ADR-0003, raised 2026-10-25
        max_redirects: int = 5,
        max_retries: int = 2,
        backoff_seconds: float = 5.0,
        max_retry_after_seconds: float = 60.0,
        timeout_seconds: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.policy = policy
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.max_retry_after_seconds = max_retry_after_seconds
        self._sleep = sleep
        self._clock = clock
        self._hosts = _HostState()
        self._client = httpx.Client(
            transport=transport,
            timeout=timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": policy.user_agent},
        )
        self.robots = RobotsCache(self._fetch_robots, policy.user_agent)
        # Last network error per robots.txt URL (diagnostics: DNS, TLS, timeout, ...).
        self.robots_errors: dict[str, str] = {}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PoliteFetcher:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------ public

    def get(self, url: str, headers: Mapping[str, str] | None = None) -> FetchedResponse:
        """GET ``url`` politely, following redirects manually with robots checks."""
        current = url
        redirects: list[str] = []
        first_decision: RobotsDecision | None = None
        for _hop in range(self.max_redirects + 1):
            if not is_url_in_scope(current, self.policy):
                raise OutOfScopeError(f"URL ngoài phạm vi cho phép: {current}")
            decision = self.robots.check(current)
            if first_decision is None:
                first_decision = decision
            if not decision.allowed:
                raise RobotsDisallowedError(decision, current)
            body, response = self._send_with_retries(current, headers or {}, self.max_bytes)
            if response.status_code in REDIRECT_STATUSES and "location" in response.headers:
                current = urljoin(current, response.headers["location"])
                redirects.append(current)
                continue
            if response.status_code == 304:
                body = b""
            elif response.status_code >= 400:
                raise HttpStatusError(
                    f"HTTP {response.status_code} cho {current}", status_code=response.status_code
                )
            return FetchedResponse(
                requested_url=url,
                final_url=current,
                status_code=response.status_code,
                headers={k.lower(): v for k, v in response.headers.items()},
                content=body,
                redirects=tuple(redirects),
                robots=first_decision,
            )
        raise HttpStatusError(f"Quá {self.max_redirects} lần chuyển hướng: {url}")

    # ----------------------------------------------------------------- helpers

    def _throttle(self, host: str) -> None:
        if self._hosts.count[host] >= self.policy.max_requests_per_host_per_run:
            raise BudgetExceededError(f"Đã đạt giới hạn yêu cầu cho {host} trong lần chạy này")
        last = self._hosts.last_request.get(host)
        if last is not None:
            wait = self.policy.min_delay_seconds - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._hosts.last_request[host] = self._clock()
        self._hosts.count[host] += 1

    def _retry_delay(self, response: httpx.Response | None, attempt: int) -> float:
        delay = self.backoff_seconds * (2**attempt)
        if response is not None and "retry-after" in response.headers:
            value = response.headers["retry-after"].strip()
            try:
                delay = float(value)
            except ValueError:
                try:
                    when = parsedate_to_datetime(value)
                    delay = max(0.0, when.timestamp() - time.time())
                except (TypeError, ValueError):
                    pass
        return float(min(max(delay, 0.0), self.max_retry_after_seconds))

    def _send_with_retries(
        self, url: str, headers: Mapping[str, str], max_bytes: int
    ) -> tuple[bytes, httpx.Response]:
        host = (urlsplit(url).hostname or "").lower()
        for attempt in range(self.max_retries + 1):
            self._throttle(host)
            try:
                request = self._client.build_request("GET", url, headers=dict(headers))
                response = self._client.send(request, stream=True)
            except httpx.TransportError as exc:
                if attempt < self.max_retries:
                    self._sleep(self._retry_delay(None, attempt))
                    continue
                raise NetworkError(f"Lỗi mạng khi tải {url}: {exc}") from exc
            try:
                if response.status_code in RETRY_STATUSES and attempt < self.max_retries:
                    delay = self._retry_delay(response, attempt)
                    response.close()
                    self._sleep(delay)
                    continue
                body = self._read_limited(response, url, max_bytes)
            finally:
                response.close()
            return body, response
        raise NetworkError(f"Hết số lần thử cho {url}")  # pragma: no cover - loop always returns

    @staticmethod
    def _read_limited(response: httpx.Response, url: str, max_bytes: int) -> bytes:
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            raise TooLargeError(f"{url}: Content-Length {declared} vượt giới hạn {max_bytes} byte")
        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise TooLargeError(f"{url}: vượt giới hạn {max_bytes} byte")
                chunks.append(chunk)
        except httpx.TransportError as exc:
            raise NetworkError(f"Lỗi mạng khi đọc {url}: {exc}") from exc
        return b"".join(chunks)

    def _fetch_robots(self, robots_url: str) -> tuple[int | None, str]:
        """Fetch robots.txt following up to 5 redirects (RFC 9309 §2.3.1.2)."""
        current = robots_url
        try:
            for _ in range(6):
                body, response = self._send_with_retries(current, {}, ROBOTS_MAX_BYTES)
                if response.status_code in REDIRECT_STATUSES and "location" in response.headers:
                    current = urljoin(current, response.headers["location"])
                    continue
                return response.status_code, body.decode("utf-8", errors="replace")
        except TooLargeError:
            return None, ""
        except (NetworkError, BudgetExceededError) as exc:
            self.robots_errors[robots_url] = str(exc)[:300]
            return None, ""
        return None, ""  # too many redirects: treat as unreachable
