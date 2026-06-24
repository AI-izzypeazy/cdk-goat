"""Detect whether the site has meaningful autosuggest/autocomplete."""

from __future__ import annotations

from bs4 import BeautifulSoup

from .base import Detector, ScanContext
from ..models import Finding, Severity

AUTOSUGGEST_SIGNATURES = (
    "autocomplete", "autosuggest", "typeahead", "predictive-search",
    "predictive_search", "instant-search", "instantsearch", "aa-",
    "ac.cnstrc", "algolia-autocomplete", "search-suggestions", "suggestion",
)


class AutosuggestDetector(Detector):
    name = "autosuggest"

    def run(self, ctx: ScanContext) -> list[Finding]:
        if not ctx.profile.has_search:
            return []
        home = ctx.page("homepage")
        if not home:
            return []
        blob = home.text_lower()
        has_signature = any(s in blob for s in AUTOSUGGEST_SIGNATURES)

        # Also check the search input itself for autocomplete wiring.
        soup = BeautifulSoup(home.html, "html.parser")
        wired = False
        for inp in soup.find_all("input"):
            attrs = " ".join(str(v) for v in inp.attrs.values()).lower()
            if "search" in attrs and ("autocomplete" in attrs or "aria-autocomplete" in attrs
                                      or inp.get("list")):
                wired = True
                break

        if has_signature or wired:
            return []

        sev = Severity.HIGH if ctx.profile.incumbent_vendor == "none" else Severity.MEDIUM
        return [
            Finding(
                code="weak_or_no_autosuggest",
                title="No autosuggest / typeahead detected",
                capability="autosuggest",
                severity=sev,
                detail=(
                    "We found no autosuggest/typeahead wiring on the search box. "
                    "Autosuggest is where a large share of search revenue is captured — "
                    "shoppers convert on suggested products and terms before submitting."
                ),
                recommendation=(
                    "Constructor Autosuggest adds product previews, trending and "
                    "recovery suggestions in the typeahead, typically lifting "
                    "search-led conversion."
                ),
                evidence=[f"Homepage: {ctx.profile.homepage_url}"],
                confidence=0.5,
            )
        ]
