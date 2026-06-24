"""Run live queries to probe relevance, typo tolerance, NL and zero-results.

We derive a plausible query term from the site's own navigation/product text,
then issue: (1) the term, (2) a misspelled variant, (3) a natural-language
variant. Comparing results exposes concrete, demonstrable gaps.
"""

from __future__ import annotations

import re
from collections import Counter

from bs4 import BeautifulSoup

from .base import Detector, ScanContext
from ..models import Finding, PageSnapshot, Severity

NO_RESULTS_MARKERS = (
    "no results", "no result", "0 results", "did not match", "no matches",
    "couldn't find", "could not find", "nothing found", "no products found",
    "we couldn't find", "sorry, no", "0 items", "no items found",
)

# Product-card-ish selectors used to estimate result count.
PRODUCT_HINTS = (
    "product", "item", "card", "tile", "grid__item", "result",
)

STOPWORDS = set(
    "the and for with your you our all new shop home page sale shipping free "
    "off get more best top from this that are has have was were will can use "
    "about help cart account sign menu search products product collection".split()
)


def _derive_terms(pages: list[PageSnapshot]) -> list[str]:
    words: Counter[str] = Counter()
    for p in pages:
        if not p.ok:
            continue
        soup = BeautifulSoup(p.html, "html.parser")
        # Prefer nav / link / heading text — closer to catalog vocabulary.
        chunks = []
        for tag in soup.find_all(["a", "h1", "h2", "h3", "li"]):
            chunks.append(tag.get_text(" ", strip=True))
        text = " ".join(chunks).lower()
        for w in re.findall(r"[a-z]{4,15}", text):
            if w not in STOPWORDS:
                words[w] += 1
    return [w for w, _ in words.most_common(8)]


def _typo(term: str) -> str:
    """Make a believable misspelling by swapping two adjacent letters."""
    if len(term) < 4:
        return term + term[-1]  # double last letter
    i = len(term) // 2
    chars = list(term)
    chars[i], chars[i - 1] = chars[i - 1], chars[i]
    return "".join(chars)


def _estimate_results(snap: PageSnapshot) -> tuple[int, bool]:
    """Return (approx_product_count, zero_results_flag)."""
    low = snap.text_lower()
    zero = any(m in low for m in NO_RESULTS_MARKERS)
    soup = BeautifulSoup(snap.html, "html.parser")
    count = 0
    for el in soup.find_all(attrs={"class": True}):
        cls = " ".join(el.get("class", [])).lower()
        if any(h in cls for h in PRODUCT_HINTS) and (el.find("img") or el.find("a")):
            count += 1
    # de-noise: a handful of accidental matches shouldn't read as "results"
    approx = count if count >= 3 else 0
    return approx, zero


class SearchQualityDetector(Detector):
    name = "search_quality"

    def run(self, ctx: ScanContext) -> list[Finding]:
        findings: list[Finding] = []
        prof = ctx.profile
        if not prof.has_search or not prof.search_endpoint:
            return findings

        terms = _derive_terms(ctx.any_ok())
        if not terms:
            return findings
        term = terms[0]
        typo = _typo(term)
        nl_term = f"{term} under $50"

        base_snap = ctx.crawler.fetch(
            ctx.crawler.search_url(prof.search_endpoint, term), role="search"
        )
        if not base_snap.ok:
            return findings
        ctx.pages.append(base_snap)
        base_count, base_zero = _estimate_results(base_snap)

        ev_base = f'Query "{term}" → ~{base_count} results' + (" (zero-results page)" if base_zero else "")

        # Relevance / baseline: a head term returning zero is a red flag.
        if base_zero or base_count == 0:
            findings.append(
                Finding(
                    code="head_term_zero_results",
                    title=f'Common term "{term}" returns no results',
                    capability="search",
                    severity=Severity.CRITICAL,
                    detail=(
                        f'A frequent term from the site\'s own navigation ("{term}") '
                        "returned a zero/empty results page. Head-term misses are the "
                        "most expensive search failures — high-intent shoppers bounce."
                    ),
                    recommendation=(
                        "Constructor Search ranks on behavioral relevance and never "
                        "dead-ends a query; zero-results recovery surfaces fallbacks."
                    ),
                    evidence=[ev_base, base_snap.final_url],
                    confidence=0.55,
                )
            )

        # Typo tolerance: typo'd variant goes empty while base had results.
        typo_snap = ctx.crawler.fetch(
            ctx.crawler.search_url(prof.search_endpoint, typo), role="search"
        )
        if typo_snap.ok:
            typo_count, typo_zero = _estimate_results(typo_snap)
            if base_count > 0 and (typo_zero or typo_count == 0):
                findings.append(
                    Finding(
                        code="no_typo_tolerance",
                        title="Search has no typo tolerance",
                        capability="typo_tolerance",
                        severity=Severity.HIGH,
                        detail=(
                            f'"{term}" returns results but the misspelling "{typo}" '
                            "returns nothing. Roughly 1 in 10 search queries contain a "
                            "typo; today those shoppers hit a dead end."
                        ),
                        recommendation=(
                            "Constructor applies typo tolerance, plurals and synonyms "
                            f'automatically so "{typo}" resolves to the same products as '
                            f'"{term}".'
                        ),
                        evidence=[
                            ev_base,
                            f'Query "{typo}" → ~{typo_count} results'
                            + (" (zero-results page)" if typo_zero else ""),
                            typo_snap.final_url,
                        ],
                        confidence=0.7,
                    )
                )

        # Natural-language / semantic search probe.
        nl_snap = ctx.crawler.fetch(
            ctx.crawler.search_url(prof.search_endpoint, nl_term), role="search"
        )
        if nl_snap.ok:
            nl_count, nl_zero = _estimate_results(nl_snap)
            if base_count > 0 and (nl_zero or nl_count == 0):
                findings.append(
                    Finding(
                        code="no_nl_search",
                        title="No natural-language / intent understanding",
                        capability="nl_search",
                        severity=Severity.MEDIUM,
                        detail=(
                            f'"{term}" returns results, but the natural-language query '
                            f'"{nl_term}" returns nothing — the engine keyword-matches '
                            "the price phrase instead of understanding intent."
                        ),
                        recommendation=(
                            "Constructor's NL/semantic search parses attributes and "
                            "price intent so conversational queries return the right "
                            "products."
                        ),
                        evidence=[
                            ev_base,
                            f'Query "{nl_term}" → ~{nl_count} results'
                            + (" (zero-results page)" if nl_zero else ""),
                            nl_snap.final_url,
                        ],
                        confidence=0.5,
                    )
                )
        return findings
