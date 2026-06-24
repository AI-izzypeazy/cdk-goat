"""Core data models shared across the pipeline."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def weight(self) -> float:
        return {
            "critical": 10.0,
            "high": 6.0,
            "medium": 3.0,
            "low": 1.0,
            "info": 0.0,
        }[self.value]


@dataclass
class Finding:
    """A single discrepancy that Constructor.io can address."""

    code: str                 # stable id, e.g. "no_search_box"
    title: str
    capability: str           # CAPABILITIES key this maps to
    severity: Severity
    detail: str               # what we observed and why it matters
    recommendation: str       # the Constructor fix
    evidence: list[str] = field(default_factory=list)
    example: str = ""         # concrete, site-specific example (LLM-enriched)
    confidence: float = 0.7   # 0..1 — how sure the heuristic is

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


@dataclass
class PageSnapshot:
    url: str
    final_url: str = ""
    status: int = 0
    html: str = ""
    ok: bool = False
    error: str = ""
    role: str = "page"   # homepage | category | product | search | page

    def text_lower(self) -> str:
        return self.html.lower()


@dataclass
class SiteProfile:
    domain: str
    homepage_url: str
    platform: str = "unknown"
    platform_name: str = "Unknown"
    incumbent_vendor: str = "none"
    incumbent_vendor_name: str = "None detected"
    is_existing_constructor: bool = False
    has_search: bool = False
    search_endpoint: str = ""     # resolved search URL template w/ {q}
    search_param: str = ""
    looks_ecommerce: bool = False
    catalog_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Outreach:
    subject: str = ""
    body: str = ""


@dataclass
class SiteReport:
    domain: str
    profile: SiteProfile
    findings: list[Finding] = field(default_factory=list)
    fit_score: float = 0.0          # 0..100 — is this a real retail/ecom prospect
    opportunity_score: float = 0.0  # 0..100 — how much room Constructor has
    priority: str = "C"             # A | B | C
    summary: str = ""
    outreach: Outreach = field(default_factory=Outreach)
    generated_at: float = field(default_factory=time.time)
    pages_crawled: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "generated_at": self.generated_at,
            "fit_score": round(self.fit_score, 1),
            "opportunity_score": round(self.opportunity_score, 1),
            "priority": self.priority,
            "pages_crawled": self.pages_crawled,
            "profile": self.profile.to_dict(),
            "summary": self.summary,
            "findings": [f.to_dict() for f in self.findings],
            "outreach": asdict(self.outreach),
            "notes": self.notes,
        }
