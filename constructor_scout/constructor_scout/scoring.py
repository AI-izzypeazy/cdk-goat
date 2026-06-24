"""Fit and opportunity scoring, and priority tiering."""

from __future__ import annotations

from .models import Finding, Severity, SiteProfile


def fit_score(profile: SiteProfile) -> float:
    """0..100 — how likely this is a real retail/ecommerce prospect."""
    score = 0.0
    if profile.looks_ecommerce:
        score += 40
    if profile.platform != "unknown":
        score += 25
    score += min(len(profile.catalog_signals), 6) * 5  # up to 30
    if profile.has_search:
        score += 5
    return min(score, 100.0)


def opportunity_score(findings: list[Finding], profile: SiteProfile) -> float:
    """0..100 — how much room Constructor has to add value."""
    if profile.is_existing_constructor:
        return 0.0
    # Weight by severity * confidence.
    raw = sum(f.severity.weight * f.confidence for f in findings
              if f.severity != Severity.INFO)
    # Normalize: ~30 raw points is a saturated opportunity.
    score = min(raw / 30.0 * 100.0, 100.0)
    return score


def priority_tier(fit: float, opportunity: float, profile: SiteProfile) -> str:
    if profile.is_existing_constructor:
        return "EXISTING"
    if fit < 35:
        return "C"  # probably not ecommerce / weak fit
    combined = 0.45 * fit + 0.55 * opportunity
    if combined >= 65:
        return "A"
    if combined >= 40:
        return "B"
    return "C"
