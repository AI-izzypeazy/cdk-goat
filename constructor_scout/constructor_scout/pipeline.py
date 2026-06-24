"""Orchestration: crawl → fingerprint → detect → score → enrich → report."""

from __future__ import annotations

import sys

from .config import Config
from .crawler import Crawler, domain_of, normalize_url
from .detectors import ALL_DETECTORS, ScanContext
from .llm import LLMEnricher
from .models import SiteProfile, SiteReport
from .platform_fingerprint import fingerprint
from .scoring import fit_score, opportunity_score, priority_tier


def _log(config: Config, msg: str) -> None:
    if config.verbose:
        print(f"  [scout] {msg}", file=sys.stderr)


def scan_site(
    target: str,
    config: Config,
    enricher: LLMEnricher | None = None,
    depth: str = "deep",
) -> SiteReport:
    url = normalize_url(target)
    domain = domain_of(url)
    crawler = Crawler(config)
    enricher = enricher or LLMEnricher(config)

    _log(config, f"crawling {domain} ({depth})")
    home = crawler.fetch(url, role="homepage")
    profile = SiteProfile(domain=domain, homepage_url=url)

    if not home.ok:
        report = SiteReport(domain=domain, profile=profile)
        report.notes.append(f"Homepage fetch failed: {home.error or 'status ' + str(home.status)}")
        report.summary = f"Could not crawl {domain} ({home.error or home.status})."
        report.priority = "C"
        return report

    pages = [home]

    # Search form discovery
    form = Crawler.find_search_form(home)
    if form:
        profile.has_search = True
        profile.search_endpoint, profile.search_param = form
        _log(config, f"search endpoint: {profile.search_endpoint}")

    # Crawl a few category / product pages (deep scans only)
    if depth == "deep":
        for link, role in Crawler.find_category_and_product_links(home, limit=2):
            if len([p for p in pages if p.ok]) >= config.max_pages:
                break
            snap = crawler.fetch(link, role=role)
            if snap.ok:
                pages.append(snap)

    # Fingerprint platform + incumbent vendor + ecommerce-ness
    profile = fingerprint(pages, profile)
    _log(config, f"platform={profile.platform_name} incumbent={profile.incumbent_vendor_name}")

    # Run detectors
    ctx = ScanContext(config=config, crawler=crawler, profile=profile, pages=pages, depth=depth)
    findings = []
    for det in ALL_DETECTORS:
        try:
            findings.extend(det.run(ctx))
        except Exception as exc:  # one detector must never sink the scan
            _log(config, f"detector {det.name} failed: {exc}")

    # Score
    fit = fit_score(profile)
    opp = opportunity_score(findings, profile)
    tier = priority_tier(fit, opp, profile)

    report = SiteReport(
        domain=domain,
        profile=profile,
        findings=findings,
        fit_score=fit,
        opportunity_score=opp,
        priority=tier,
        pages_crawled=len([p for p in ctx.pages if p.ok]),
    )

    # LLM enrichment (concrete examples + summary + outreach).
    # Shallow scans stay cheap/fast with the deterministic template; deep scans
    # of a selected prospect get full Claude enrichment.
    if depth == "deep":
        _log(config, f"enriching ({'llm' if enricher.active else 'template'})")
        summary, outreach = enricher.enrich(profile, findings)
        if not enricher.active:
            report.notes.append(
                "LLM disabled — using templated copy. Set ANTHROPIC_API_KEY for tailored examples."
            )
    else:
        summary, outreach = enricher.template_brief(profile, findings)
    report.summary = summary
    report.outreach = outreach

    return report


def scan_many(targets: list[str], config: Config, depth: str = "deep") -> list[SiteReport]:
    enricher = LLMEnricher(config)
    reports: list[SiteReport] = []
    for i, t in enumerate(targets, 1):
        _log(config, f"=== [{i}/{len(targets)}] {t} ===")
        try:
            reports.append(scan_site(t, config, enricher, depth=depth))
        except Exception as exc:
            dom = domain_of(normalize_url(t))
            r = SiteReport(domain=dom, profile=SiteProfile(domain=dom, homepage_url=t))
            r.notes.append(f"Scan error: {exc}")
            r.summary = f"Scan failed for {dom}: {exc}"
            reports.append(r)
    return reports
