"""robots.txt (RFC 9309) and crawl-policy tests, copied from travienphi. Offline only.

All hosts are under example.invalid.
"""

from __future__ import annotations

import pytest

from pay_pipeline.acquisition import CrawlPolicy, is_url_in_scope, robots_allows
from pay_pipeline.acquisition.robots import decide_from_fetch, is_allowed, product_token

UA = "pay-schedules/0.1 (+https://example.invalid/about)"
HOST = "https://district-a.example.invalid"
ALLOW_ALL = "User-agent: *\nAllow: /\n"


class TestRobotsRules:
    def test_longest_match_wins_unlike_stdlib(self) -> None:
        robots = "User-agent: *\nAllow: /\nDisallow: /oldimage/\n"
        assert is_allowed(robots, f"{HOST}/salary-schedule.pdf", UA)
        assert not is_allowed(robots, f"{HOST}/oldimage/a.png", UA)

    def test_allow_wins_tie(self) -> None:
        robots = "User-agent: *\nDisallow: /a\nAllow: /a\n"
        assert is_allowed(robots, f"{HOST}/a", UA)

    def test_specific_agent_group_overrides_star(self) -> None:
        robots = "User-agent: *\nDisallow: /\n\nUser-agent: pay-schedules\nAllow: /\n"
        assert is_allowed(robots, f"{HOST}/x", UA)

    def test_star_disallow_all_except_googlebot(self) -> None:
        robots = "User-agent: *\nDisallow: /\nUser-agent: Googlebot\nAllow: /\n"
        assert not is_allowed(robots, f"{HOST}/hr", UA)

    def test_wildcards_and_anchor(self) -> None:
        robots = "User-agent: *\nDisallow: /*.pdf$\nDisallow: /search/*\n"
        assert not is_allowed(robots, f"{HOST}/files/a.pdf", UA)
        assert is_allowed(robots, f"{HOST}/files/a.pdf?x=1", UA)
        assert not is_allowed(robots, f"{HOST}/search/q", UA)

    def test_query_is_part_of_path(self) -> None:
        robots = "User-agent: *\nDisallow: /?rest_route=\n"
        assert not is_allowed(robots, f"{HOST}/?rest_route=/wp/v2", UA)
        assert is_allowed(robots, f"{HOST}/?page_id=837", UA)

    def test_comments_only_file_allows(self) -> None:
        assert is_allowed("# comments only\n# search=\n", f"{HOST}/x", UA)

    def test_empty_disallow_allows(self) -> None:
        assert is_allowed("User-agent: *\nDisallow:\n", f"{HOST}/x", UA)

    def test_robots_txt_itself_always_allowed(self) -> None:
        assert is_allowed("User-agent: *\nDisallow: /\n", f"{HOST}/robots.txt", UA)

    def test_product_token(self) -> None:
        assert product_token(UA) == "pay-schedules"

    @pytest.mark.parametrize(
        ("status", "allowed"), [(200, True), (404, True), (403, True), (500, False), (None, False)]
    )
    def test_retrieval_outcomes(self, status: int | None, allowed: bool) -> None:
        d = decide_from_fetch(status, ALLOW_ALL, f"{HOST}/x", UA, f"{HOST}/robots.txt")
        assert d.allowed is allowed


class TestCrawlPolicy:
    def test_robots_allows(self) -> None:
        robots = "User-agent: *\nDisallow: /private/\n"
        assert robots_allows(robots, f"{HOST}/hr/salary.pdf", UA)
        assert not robots_allows(robots, f"{HOST}/private/x", UA)

    def test_refuses_unsafe_settings(self) -> None:
        with pytest.raises(ValueError):
            CrawlPolicy(user_agent="")
        with pytest.raises(ValueError):
            CrawlPolicy(user_agent=UA, min_delay_seconds=0.5)
        with pytest.raises(ValueError):
            CrawlPolicy(user_agent=UA, respect_robots_txt=False)

    def test_defaults_are_conservative(self) -> None:
        p = CrawlPolicy(user_agent=UA)
        assert p.min_delay_seconds >= 1.0
        assert p.respect_robots_txt

    def test_scope(self) -> None:
        p = CrawlPolicy(user_agent=UA)
        assert is_url_in_scope(f"{HOST}/a.pdf", p)
        assert not is_url_in_scope("ftp://district-a.example.invalid/a.pdf", p)
        assert not is_url_in_scope("/relative/a.pdf", p)
