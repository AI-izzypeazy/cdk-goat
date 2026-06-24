"""Detect recommendation widgets on homepage and product pages."""

from __future__ import annotations

from .base import Detector, ScanContext
from ..models import Finding, Severity

REC_MARKERS = (
    "you may also like", "recommended for you", "related products",
    "customers also", "you might also", "complete the look", "frequently bought",
    "people also bought", "similar products", "more like this", "trending now",
    "recently viewed", "shop the look", "pairs well with", "recommendations",
)


class RecommendationsDetector(Detector):
    name = "recommendations"

    def run(self, ctx: ScanContext) -> list[Finding]:
        pages = [p for p in ctx.pages if p.role in ("homepage", "product") and p.ok]
        if not pages:
            return []
        hits = set()
        for p in pages:
            low = p.text_lower()
            for m in REC_MARKERS:
                if m in low:
                    hits.add(m)
        if hits:
            return []
        pdp = ctx.page("product")
        sev = Severity.HIGH if pdp else Severity.MEDIUM
        return [
            Finding(
                code="no_recommendations",
                title="No recommendation pods detected",
                capability="recommendations",
                severity=sev,
                detail=(
                    "We found no recommendation modules ('you may also like', "
                    "'customers also bought', 'complete the look') on the homepage"
                    + (" or product page" if pdp else "")
                    + ". Recs are one of the highest-ROI discovery surfaces for AOV."
                ),
                recommendation=(
                    "Constructor Recommendations adds revenue-optimized pods to PDP, "
                    "cart and homepage, driving units-per-order and AOV lift."
                ),
                evidence=[f"Pages checked: {', '.join(p.role for p in pages)}"],
                confidence=0.5,
            )
        ]
