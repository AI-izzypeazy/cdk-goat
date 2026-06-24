"""Is there site search at all, and can we reach it?"""

from __future__ import annotations

from .base import Detector, ScanContext
from ..models import Finding, Severity


class SearchPresenceDetector(Detector):
    name = "search_presence"

    def run(self, ctx: ScanContext) -> list[Finding]:
        findings: list[Finding] = []
        if not ctx.profile.has_search:
            findings.append(
                Finding(
                    code="no_search_box",
                    title="No usable site search detected",
                    capability="search",
                    severity=Severity.CRITICAL,
                    detail=(
                        "We could not find a working search box / endpoint on the "
                        "homepage. On a retail catalog, shoppers who search convert "
                        "at multiples of those who don't — a missing or hidden search "
                        "bar leaves revenue on the table."
                    ),
                    recommendation=(
                        "Deploy Constructor Search + Autosuggest with a prominent "
                        "search bar; typical lift comes from making search the "
                        "primary discovery path."
                    ),
                    evidence=[f"Homepage scanned: {ctx.profile.homepage_url}"],
                    confidence=0.6,
                )
            )
        return findings
