"""Turn the incumbent-vendor fingerprint into a positioning finding."""

from __future__ import annotations

from .base import Detector, ScanContext
from ..knowledge import INCUMBENT_VENDORS
from ..models import Finding, Severity


class IncumbentVendorDetector(Detector):
    name = "incumbent_vendor"

    def run(self, ctx: ScanContext) -> list[Finding]:
        prof = ctx.profile
        vendor = next((v for v in INCUMBENT_VENDORS if v.id == prof.incumbent_vendor), None)
        if vendor is None:
            return []

        if vendor.is_constructor:
            return [
                Finding(
                    code="existing_constructor_customer",
                    title="Already running Constructor.io",
                    capability="search",
                    severity=Severity.INFO,
                    detail=(
                        "Constructor signatures were detected on this site — this is an "
                        "existing customer, not a new-logo prospect. Route to Customer "
                        "Success / expansion."
                    ),
                    recommendation="Check for un-adopted modules (recs, personalization, collections) for expansion.",
                    evidence=[f"Detected vendor: {vendor.name}"],
                    confidence=0.8,
                )
            ]

        return [
            Finding(
                code="incumbent_vendor_present",
                title=f"Incumbent discovery vendor: {vendor.name}",
                capability="search",
                severity=Severity.INFO,
                detail=(
                    f"This site runs {vendor.name} for discovery. That means a "
                    "displacement motion rather than greenfield — but also a budget "
                    "line already exists."
                ),
                recommendation=vendor.angle,
                evidence=[f"Detected vendor: {vendor.name}"],
                confidence=0.75,
            )
        ]
