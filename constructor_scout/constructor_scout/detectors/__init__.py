"""Detector registry."""

from __future__ import annotations

from .autosuggest import AutosuggestDetector
from .base import Detector, ScanContext
from .facets import FacetsDetector
from .incumbent_vendor import IncumbentVendorDetector
from .personalization import PersonalizationDetector
from .recommendations import RecommendationsDetector
from .search_presence import SearchPresenceDetector
from .search_quality import SearchQualityDetector

ALL_DETECTORS: list[Detector] = [
    IncumbentVendorDetector(),
    SearchPresenceDetector(),
    SearchQualityDetector(),
    AutosuggestDetector(),
    FacetsDetector(),
    RecommendationsDetector(),
    PersonalizationDetector(),
]

__all__ = ["ALL_DETECTORS", "Detector", "ScanContext"]
