"""Detect faceted navigation / filtering on category & search pages."""

from __future__ import annotations

from bs4 import BeautifulSoup

from .base import Detector, ScanContext
from ..models import Finding, PageSnapshot, Severity

FACET_SIGNATURES = (
    "facet", "refine", "refinement", "filter-", "filters", "filterby",
    "filter-by", "filter_by", "narrow", "aria-label=\"filter", "data-facet",
)


def _facet_score(snap: PageSnapshot) -> int:
    soup = BeautifulSoup(snap.html, "html.parser")
    score = 0
    for el in soup.find_all(attrs={"class": True}):
        cls = " ".join(el.get("class", [])).lower()
        if any(sig in cls for sig in FACET_SIGNATURES):
            score += 1
    # checkboxes in a sidebar are a strong facet signal
    score += min(len(soup.find_all("input", attrs={"type": "checkbox"})), 10) // 2
    low = snap.text_lower()
    score += sum(1 for sig in ("price", "color", "size", "brand", "sort by") if sig in low) // 2
    return score


class FacetsDetector(Detector):
    name = "facets"

    def run(self, ctx: ScanContext) -> list[Finding]:
        page = ctx.page("category") or ctx.page("search")
        if not page:
            return []
        score = _facet_score(page)
        if score >= 3:
            return []
        return [
            Finding(
                code="weak_faceting",
                title="Thin or missing faceted navigation",
                capability="facets",
                severity=Severity.MEDIUM,
                detail=(
                    "The category/search listing shows little or no faceted filtering "
                    "(price, color, size, brand). On large catalogs, weak facets force "
                    "shoppers to scroll endlessly and abandon."
                ),
                recommendation=(
                    "Constructor Browse auto-enriches product attributes into rich, "
                    "rankable facets so shoppers can narrow large catalogs instantly."
                ),
                evidence=[f"Listing page: {page.final_url or page.url}", f"facet signal score={score}"],
                confidence=0.45,
            )
        ]
