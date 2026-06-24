"""Detector framework: shared context and base class."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import Config
from ..crawler import Crawler
from ..models import Finding, PageSnapshot, SiteProfile


@dataclass
class ScanContext:
    config: Config
    crawler: Crawler
    profile: SiteProfile
    pages: list[PageSnapshot] = field(default_factory=list)

    def page(self, role: str) -> PageSnapshot | None:
        for p in self.pages:
            if p.role == role and p.ok:
                return p
        return None

    def any_ok(self) -> list[PageSnapshot]:
        return [p for p in self.pages if p.ok]


class Detector:
    """Subclasses implement run() and return a list of Findings."""

    name = "detector"

    def run(self, ctx: ScanContext) -> list[Finding]:  # pragma: no cover
        raise NotImplementedError
