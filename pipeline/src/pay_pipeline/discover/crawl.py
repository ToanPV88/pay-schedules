"""Discover (PLAN Công đoạn 5, bước 1): find salary-schedule documents on a district website.

For one district: fetch the home page, follow links whose text or URL points to human
resources, employment, salary or bargaining pages (same site only, depth ≤ 2, page budget), and
read ``/sitemap.xml``. Every link to a document (PDF, Excel, Word, or a known document host) is a
candidate with a score from its anchor text and URL. Nothing here calls a model; classification
of the downloaded file comes later (``documents.classify``).

All requests go through a polite fetcher: robots.txt, per-host delay, size limit.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit

from pay_pipeline.acquisition.http import FetchError, PoliteFetcher

DOC_EXTENSIONS = (".pdf", ".xlsx", ".xls", ".docx", ".doc")
# Hosts that serve uploaded district documents without a file extension in the URL.
DOC_HOSTS = (
    "files-backend.assets.thrillshare.com",
    "resources.finalsite.net",
    "core-docs.s3.amazonaws.com",
    "core-docs.s3.us-east-1.amazonaws.com",
    "content.myconnectsuite.com",
    "drive.google.com",
    "docs.google.com",
)
DOC_HOST_SUFFIXES = (".files.edl.io", ".cloudfront.net", ".ic-board.com", ".boardbook.org")

SALARY_WORDS = ("salary", "salaries", "pay scale", "payscale", "pay schedule", "wage",
                "compensation")  # fmt: skip
TEACHER_WORDS = ("teacher", "certificated", "certified", "licensed", "instructional",
                 "faculty")  # fmt: skip
CONTRACT_WORDS = ("negotiated agreement", "collective bargaining", "bargaining agreement",
                  "master agreement", "master contract", "teacher contract",
                  "association agreement",
                  "cba")  # fmt: skip
NAV_WORDS = ("human resources", "human-resources", "humanresources", "/hr", "hr ", "personnel",
             "employment", "employee", "careers", "jobs", "staff", "departments", "business",
             "finance", "transparency", "fiscal", "payroll", "benefits")  # fmt: skip
NEGATIVE_WORDS = ("classified", "administrat", "management", "substitute", "coach", "extra duty",
                  "extra-duty", "custod", "nutrition", "transportation", "confidential",
                  "supervisory", "calendar", "budget", "menu", "lunch", "athletic",
                  "bus ")  # fmt: skip
YEAR_RE = re.compile(r"20(2[3-9])\s*[-–/_ ]\s*(?:20)?(2[4-9]|30)")


@dataclass(frozen=True)
class Link:
    url: str
    text: str


@dataclass(frozen=True)
class Candidate:
    url: str
    found_on: str
    anchor_text: str
    method: str  # crawl | sitemap
    score: float


@dataclass
class Discovery:
    nces_id: str
    website: str | None
    status: str  # ok | no_website | unreachable
    pages_fetched: int = 0
    candidates: list[Candidate] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.base: str | None = None
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "base" and a.get("href") and self.base is None:
            self.base = a["href"]
        elif tag == "a" and a.get("href"):
            self._href = a["href"]
            self._text = [a.get("title", ""), a.get("aria-label", "")]
        elif tag in ("iframe", "embed") and a.get("src"):
            self.links.append((a["src"], a.get("title", "")))

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(" ".join(self._text).split())))
            self._href = None


def extract_links(html: str, page_url: str) -> list[Link]:
    parser = _LinkParser()
    try:
        parser.feed(html)
        parser.close()
    except (AssertionError, ValueError):
        parser.links.append(("", ""))  # malformed HTML: keep the links parsed so far
    base = urljoin(page_url, parser.base) if parser.base else page_url
    out: list[Link] = []
    seen: set[str] = set()
    for href, text in parser.links:
        href = href.strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
            continue
        url, _ = urldefrag(urljoin(base, href))
        if urlsplit(url).scheme not in ("http", "https") or url in seen:
            continue
        seen.add(url)
        out.append(Link(url, text[:300]))
    return out


def _host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def same_site(url: str, home: str) -> bool:
    a, b = _host(url), _host(home)
    return bool(a) and (a == b or a.endswith("." + b) or b.endswith("." + a))


def is_document_url(url: str) -> bool:
    parts = urlsplit(url)
    path = parts.path.lower()
    host = (parts.hostname or "").lower()
    if path.endswith(DOC_EXTENSIONS):
        return True
    if host in DOC_HOSTS or host.endswith(DOC_HOST_SUFFIXES):
        return True
    if "/documents/" in path and re.search(r"/\d{5,}$", path):
        return True
    return any(k in path for k in ("displayattachment", "browsefile", "/attachments/"))


def _has(text: str, words: Iterable[str]) -> int:
    return sum(1 for w in words if w in text)


def score_document(link: Link) -> float:
    """Higher = more likely a teacher salary schedule. Below 1 is not worth downloading."""
    text = f"{link.text} {link.url}".lower().replace("%20", " ").replace("_", " ")
    score = 0.0
    if _has(text, SALARY_WORDS):
        score += 3
    if "schedule" in text or "scale" in text:
        score += 1
    if _has(text, TEACHER_WORDS):
        score += 2
    if _has(text, CONTRACT_WORDS):
        score += 1.5
    if YEAR_RE.search(text):
        score += 1
    score -= 1.5 * _has(text, NEGATIVE_WORDS)
    return score


def score_page(link: Link) -> float:
    """Priority for following an HTML page link."""
    text = f"{link.text} {link.url}".lower()
    score = 3.0 * bool(_has(text, SALARY_WORDS)) + 2.0 * bool(_has(text, CONTRACT_WORDS))
    score += 1.0 * bool(_has(text, NAV_WORDS))
    score -= 1.0 * bool(_has(text, NEGATIVE_WORDS))
    return score


def _is_html(content_type: str) -> bool:
    return "html" in content_type or not content_type


def sitemap_links(xml: str, limit: int = 20000) -> list[Link]:
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml[:5_000_000])[:limit]
    return [Link(u.replace("&amp;", "&"), "") for u in locs]


def discover(
    fetcher: PoliteFetcher,
    nces_id: str,
    website: str | None,
    max_pages: int = 20,
    max_depth: int = 2,
) -> Discovery:
    if not website:
        return Discovery(nces_id, website, "no_website")
    result = Discovery(nces_id, website, "unreachable")
    candidates: dict[str, Candidate] = {}

    def add(link: Link, found_on: str, method: str) -> None:
        s = score_document(link)
        if s < 1:
            return
        old = candidates.get(link.url)
        if old is None or s > old.score:
            candidates[link.url] = Candidate(link.url, found_on, link.text, method, s)

    # Frontier of (priority, depth, url); best-first so salary pages are fetched early.
    frontier: list[tuple[float, int, str]] = [(10.0, 0, website)]
    seen: set[str] = {website}
    home = website
    while frontier and result.pages_fetched < max_pages:
        frontier.sort(key=lambda x: (-x[0], x[1]))
        _, depth, url = frontier.pop(0)
        try:
            response = fetcher.get(url)
        except FetchError as exc:
            result.errors.append(f"{url}: {exc}"[:300])
            continue
        result.pages_fetched += 1
        if depth == 0:
            result.status = "ok"
            home = response.final_url  # the site may redirect to another host
        if not _is_html(response.headers.get("content-type", "")):
            if response.final_url.lower().endswith(DOC_EXTENSIONS):
                add(Link(response.final_url, ""), url, "crawl")
            continue
        html = response.content.decode("utf-8", errors="replace")
        for link in extract_links(html, response.final_url):
            if is_document_url(link.url):
                add(link, response.final_url, "crawl")
            elif depth < max_depth and link.url not in seen and same_site(link.url, home):
                priority = score_page(link)
                if priority > 0:
                    seen.add(link.url)
                    frontier.append((priority, depth + 1, link.url))
    if result.status == "ok":
        sitemap = urljoin(home, "/sitemap.xml")
        try:
            response = fetcher.get(sitemap)
            ctype = response.headers.get("content-type", "")
            if "xml" in ctype or response.content[:5] == b"<?xml":
                for link in sitemap_links(response.content.decode("utf-8", errors="replace")):
                    if is_document_url(link.url):
                        add(Link(link.url, ""), sitemap, "sitemap")
        except FetchError as exc:
            result.errors.append(f"{sitemap}: {exc}"[:300])
    result.candidates = sorted(candidates.values(), key=lambda c: (-c.score, c.url))
    return result
