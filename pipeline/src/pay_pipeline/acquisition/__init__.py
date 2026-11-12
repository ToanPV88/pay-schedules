"""Polite document fetching. Only robots.txt-permitted URLs, rate limited per host."""

from pay_pipeline.acquisition.policy import CrawlPolicy, is_url_in_scope, robots_allows

__all__ = ["CrawlPolicy", "is_url_in_scope", "robots_allows"]
