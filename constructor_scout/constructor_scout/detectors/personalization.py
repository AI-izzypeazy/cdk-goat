"""Infer whether on-site personalization is in play (low-confidence heuristic)."""

from __future__ import annotations

from .base import Detector, ScanContext
from ..models import Finding, Severity

PERSONALIZATION_MARKERS = (
    "recommended for you", "picked for you", "based on your", "your recently",
    "just for you", "because you viewed", "personalized", "for you",
)


class PersonalizationDetector(Detector):
    name = "personalization"

    def run(self, ctx: ScanContext) -> list[Finding]:
        # If a personalization-capable vendor is present, assume covered.
        if ctx.profile.incumbent_vendor in ("nosto", "bloomreach", "salesforce_einstein"):
            return []
        blob = " ".join(p.text_lower() for p in ctx.any_ok())
        if any(m in blob for m in PERSONALIZATION_MARKERS):
            return []
        return [
            Finding(
                code="no_personalization",
                title="No visible personalization",
                capability="personalization",
                severity=Severity.LOW,
                detail=(
                    "No signs of personalized merchandising ('recommended for you', "
                    "'because you viewed'). Discovery is one-size-fits-all, so returning "
                    "shoppers see the same generic ranking as first-time visitors."
                ),
                recommendation=(
                    "Constructor Personalization reranks search, browse and recs per "
                    "shopper in real time off behavioral signals."
                ),
                evidence=["No personalization markers found across crawled pages"],
                confidence=0.35,
            )
        ]
