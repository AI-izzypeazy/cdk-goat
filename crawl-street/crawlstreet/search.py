"""Run generated queries against the site's own search and score the results.

Endpoint discovery, in order:
  1. a <form> with a search input found during the crawl
  2. common query params on common paths  (/search?q=, /?s=, /catalogsearch/result/?q=)
Relevance scoring is deliberately simple and transparent: we count how many
query terms appear in the result page and whether known product names surface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlencode, urlsplit, urlunsplit

from .catalogue import Catalogue
from .extract import SearchForm, parse_page
from .fetcher import Fetcher
from .queries import GeneratedQuery

_COMMON_ENDPOINTS = [
    ("/search", "q"),
    ("/search", "query"),
    ("/", "s"),
    ("/", "q"),
    ("/catalogsearch/result/", "q"),   # Magento
    ("/search", "keyword"),
]


@dataclass
class QueryResult:
    query: str
    intent: str
    url: str
    status: int
    expected_results: bool
    term_hits: int
    term_total: int
    result_signal: bool          # did the page look like it had results?
    relevance: float             # 0..1
    verdict: str                 # pass | weak | fail | blocked | error
    rationale: str
    elapsed: float = 0.0


@dataclass
class SearchReport:
    endpoint: Optional[str] = None
    param: Optional[str] = None
    method: str = "get"
    discovered_via: str = "none"
    results: List[QueryResult] = field(default_factory=list)

    def score(self) -> dict:
        if not self.results:
            return {"health": None, "pass": 0, "weak": 0, "fail": 0,
                    "blocked": 0, "error": 0, "total": 0}
        tally = {"pass": 0, "weak": 0, "fail": 0, "blocked": 0, "error": 0}
        for r in self.results:
            tally[r.verdict] = tally.get(r.verdict, 0) + 1
        graded = [r for r in self.results if r.verdict in ("pass", "weak", "fail")]
        health = round(100 * sum(
            1.0 if r.verdict == "pass" else 0.5 if r.verdict == "weak" else 0.0
            for r in graded) / len(graded), 1) if graded else None
        return {"health": health, "total": len(self.results), **tally}


async def discover_endpoint(
    fetcher: Fetcher, base_url: str, forms: List[SearchForm],
    cat: Optional[Catalogue] = None,
) -> Optional[SearchReport]:
    hit_term, known = _probe_terms(cat)

    # 1. Prefer a real form found on the site.
    for f in forms:
        report = SearchReport(endpoint=f.action, param=f.param, method=f.method,
                              discovered_via="form")
        if await _probe(fetcher, report, base_url, hit_term, known):
            return report

    # 2. Fall back to probing common endpoints.
    origin = _origin(base_url)
    for path, param in _COMMON_ENDPOINTS:
        action = origin + path
        report = SearchReport(endpoint=action, param=param, method="get",
                              discovered_via="probe")
        if await _probe(fetcher, report, base_url, hit_term, known):
            return report
    return None


def _probe_terms(cat: Optional[Catalogue]):
    """Pick a term that *should* match (from the catalogue) for the hit probe."""
    known = {p.name.lower() for p in cat.products if p.name} if cat else set()
    if cat:
        kws = cat.top_keywords(1) or cat.top_brands(1)
        if kws:
            return kws[0], known
    return "shirt", known


async def _probe(fetcher: Fetcher, report: SearchReport, referer: str,
                 hit_term: str, known_names) -> bool:
    """A working endpoint returns *results* for a real term and *none* for a
    nonsense term. An endpoint that ignores the query (e.g. the homepage) fails
    because both probes come back identical."""
    r_hit = await fetcher.fetch(_build_url(report, hit_term), referer=referer, allow_render=False)
    if r_hit.status != 200 or r_hit.error:
        return False
    r_miss = await fetcher.fetch(_build_url(report, "zxqwv0000nope"), referer=referer,
                                 allow_render=False)
    if r_miss.status != 200:
        return False
    # Query-ignoring endpoints return byte-identical pages -> not a search.
    if r_hit.text == r_miss.text:
        return False
    hit_has = _result_signal(r_hit.text, known_names)
    miss_has = _result_signal(r_miss.text, known_names)
    return hit_has and not miss_has


def _build_url(report: SearchReport, query: str) -> str:
    parts = urlsplit(report.endpoint or "")
    existing = parts.query
    qs = urlencode({report.param: query})
    new_q = f"{existing}&{qs}" if existing else qs
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_q, ""))


async def run_queries(
    fetcher: Fetcher,
    report: SearchReport,
    queries: List[GeneratedQuery],
    cat: Catalogue,
    referer: str,
) -> None:
    known_names = {p.name.lower() for p in cat.products if p.name}
    for gq in queries:
        url = _build_url(report, gq.text)
        res = await fetcher.fetch(url, referer=referer, allow_render=False)
        qr = _grade(gq, url, res, known_names)
        report.results.append(qr)


def _grade(gq: GeneratedQuery, url: str, res, known_names) -> QueryResult:
    if res.error and res.status in (0,):
        return QueryResult(gq.text, gq.intent, url, res.status, gq.expect_results,
                           0, 0, False, 0.0, "error", f"fetch error: {res.error}",
                           res.elapsed)
    if res.status in (403, 429):
        return QueryResult(gq.text, gq.intent, url, res.status, gq.expect_results,
                           0, 0, False, 0.0, "blocked",
                           "search endpoint blocked the request", res.elapsed)

    terms = [t for t in gq.text.lower().split() if len(t) > 2]
    body = res.text.lower()
    term_hits = sum(1 for t in terms if t in body)
    term_total = max(1, len(terms))

    result_signal = _result_signal(res.text, known_names, terms)
    relevance = round(term_hits / term_total, 2)

    # Verdict logic, split by whether we *expected* results.
    if gq.expect_results:
        if result_signal and relevance >= 0.5:
            verdict, why = "pass", "returned relevant results for an expected-hit query"
        elif result_signal:
            verdict, why = "weak", "returned results but relevance to query terms is low"
        else:
            verdict, why = "fail", "expected results but search returned none/irrelevant"
    else:  # nonsense control: a healthy search returns nothing
        if not result_signal:
            verdict, why = "pass", "correctly returned no results for a nonsense query"
        else:
            verdict, why = "fail", "returned results for a query that should match nothing"

    return QueryResult(gq.text, gq.intent, url, res.status, gq.expect_results,
                       term_hits, term_total, result_signal, relevance, verdict, why,
                       res.elapsed)


_NO_RESULTS_PHRASES = (
    "no results", "no products", "0 results", "did not match", "nothing found",
    "no matches", "couldn't find", "could not find", "no items", "0 items",
)


def _result_signal(html: str, known_names, terms=None) -> bool:
    """Does this page look like it returned search results?

    True when product markup / known product names are present and the page
    doesn't declare an empty result set.
    """
    body = html.lower()
    if any(p in body for p in _NO_RESULTS_PHRASES):
        return False
    page = parse_page("", html)
    if page.products:
        return True
    if any(n in body for n in list(known_names)[:60]):
        return True
    if terms:
        hits = sum(1 for t in terms if t in body)
        return hits >= max(1, len(terms) - 1)
    return False


def _origin(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"
