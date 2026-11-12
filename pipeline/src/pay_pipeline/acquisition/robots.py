"""robots.txt evaluation following RFC 9309 (Robots Exclusion Protocol).

Why not ``urllib.robotparser``: it applies the *first* matching rule, while RFC 9309
requires the *longest* match (ties go to Allow). With ``Allow: /`` followed by
``Disallow: /private/``, the stdlib parser would wrongly allow ``/private/x``.

Retrieval outcomes (RFC 9309 §2.3.1), decided by :func:`decide_from_fetch`:

* 2xx  -> parse and apply the rules
* 4xx  -> "unavailable": crawling is allowed
* 5xx or network error -> "unreachable": assume complete disallow
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class Rule:
    allow: bool
    pattern: str


@dataclass(frozen=True)
class RobotsDecision:
    allowed: bool
    reason: str
    robots_url: str
    reachable: bool = True
    """False when robots.txt could not be retrieved (5xx or network): disallowed by RFC."""


def product_token(user_agent: str) -> str:
    """'pay-schedules/0.1 (+url)' -> 'pay-schedules' (lowercase)."""
    token = user_agent.strip().split()[0] if user_agent.strip() else ""
    return token.split("/")[0].lower()


def parse_robots(text: str) -> dict[str, list[Rule]]:
    """Group rules by user-agent (lowercase). Groups with the same agent are merged."""
    groups: dict[str, list[Rule]] = {}
    current_agents: list[str] = []
    last_was_agent = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if not last_was_agent:
                current_agents = []
            agent = value.split()[0].lower() if value else ""
            current_agents.append(agent)
            groups.setdefault(agent, [])
            last_was_agent = True
        elif key in {"allow", "disallow"}:
            last_was_agent = False
            if not current_agents:
                continue  # rule outside any group: ignored per RFC
            if not value:
                continue  # empty pattern matches nothing
            rule = Rule(allow=(key == "allow"), pattern=value)
            for agent in current_agents:
                groups[agent].append(rule)
        else:
            last_was_agent = False  # sitemap, crawl-delay, etc. do not end the group
    return groups


def _pattern_regex(pattern: str) -> re.Pattern[str]:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = "".join(".*" if ch == "*" else re.escape(ch) for ch in body)
    return re.compile(regex + ("$" if anchored else ""))


def _path_of(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path or "/"
    return f"{path}?{parts.query}" if parts.query else path


def is_allowed(robots_text: str, url: str, user_agent: str) -> bool:
    path = _path_of(url)
    if path == "/robots.txt":
        return True
    groups = parse_robots(robots_text)
    token = product_token(user_agent)
    rules = groups.get(token)
    if rules is None:
        rules = groups.get("*")
    if not rules:
        return True
    best: Rule | None = None
    for rule in rules:
        if not _pattern_regex(rule.pattern).match(path):
            continue
        longer = best is None or len(rule.pattern) > len(best.pattern)
        tie_allow = best is not None and len(rule.pattern) == len(best.pattern) and rule.allow
        if longer or tie_allow:
            best = rule
    return True if best is None else best.allow


def robots_url_for(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))


def decide_from_fetch(
    status_code: int | None, body: str, url: str, user_agent: str, robots_url: str
) -> RobotsDecision:
    if status_code is None:
        return RobotsDecision(
            False, "không truy cập được robots.txt (lỗi mạng): coi như cấm", robots_url, False
        )
    if 200 <= status_code < 300:
        allowed = is_allowed(body, url, user_agent)
        verdict = "cho phép" if allowed else "không cho phép"
        return RobotsDecision(allowed, f"robots.txt (HTTP {status_code}) {verdict}", robots_url)
    if 400 <= status_code < 500:
        return RobotsDecision(
            True, f"robots.txt không có (HTTP {status_code}): RFC 9309 cho phép", robots_url
        )
    return RobotsDecision(
        False, f"robots.txt lỗi máy chủ (HTTP {status_code}): coi như cấm", robots_url, False
    )


class RobotsCache:
    """Fetch each origin's robots.txt once per run and answer allow/deny questions."""

    def __init__(self, fetch: Callable[[str], tuple[int | None, str]], user_agent: str) -> None:
        self._fetch = fetch
        self._user_agent = user_agent
        self._cache: dict[str, tuple[int | None, str]] = {}

    def check(self, url: str) -> RobotsDecision:
        robots_url = robots_url_for(url)
        if robots_url not in self._cache:
            self._cache[robots_url] = self._fetch(robots_url)
        status, body = self._cache[robots_url]
        return decide_from_fetch(status, body, url, self._user_agent, robots_url)
