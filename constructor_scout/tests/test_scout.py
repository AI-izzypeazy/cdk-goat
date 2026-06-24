"""Offline tests: synthetic pages exercise detectors, scoring and reporting."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from constructor_scout.config import Config
from constructor_scout.crawler import Crawler
from constructor_scout.detectors import ALL_DETECTORS, ScanContext
from constructor_scout.knowledge import CAPABILITIES
from constructor_scout.models import PageSnapshot, SiteProfile
from constructor_scout.platform_fingerprint import fingerprint
from constructor_scout.reporting import render_brief
from constructor_scout.scoring import fit_score, opportunity_score, priority_tier
from constructor_scout import pipeline


SHOPIFY_HOME = """
<html><head><script src="https://cdn.shopify.com/s/files/theme.js"></script></head>
<body>
<form action="/search" method="get"><input type="search" name="q" placeholder="Search"></form>
<nav><a href="/collections/jackets">Jackets</a><a href="/collections/boots">Boots</a>
<a href="/products/red-jacket">Red Jacket</a></nav>
<button>Add to cart</button><span itemprop="price">$99</span>
</body></html>
"""

CATEGORY_HTML = """
<html><body><h1>Jackets</h1>
<div class="product-card"><a href="/products/a"><img src="a.jpg"></a></div>
<div class="product-card"><a href="/products/b"><img src="b.jpg"></a></div>
<div class="product-card"><a href="/products/c"><img src="c.jpg"></a></div>
</body></html>
"""

SEARCH_RESULTS = """<html><body>
<div class="product result"><a href="/p/1"><img src="1.jpg"></a></div>
<div class="product result"><a href="/p/2"><img src="2.jpg"></a></div>
<div class="product result"><a href="/p/3"><img src="3.jpg"></a></div>
</body></html>"""

SEARCH_EMPTY = "<html><body><h1>No results found</h1></body></html>"


class FakeCrawler(Crawler):
    """Serves canned HTML by URL pattern instead of hitting the network."""

    def fetch(self, url: str, role: str = "page") -> PageSnapshot:
        snap = PageSnapshot(url=url, final_url=url, status=200, ok=True, role=role)
        low = url.lower()
        if "/search" in low:
            # head term & NL → results; the misspelling → empty
            if "jacket" in low and "under" not in low and "jackte" not in low and "jacekt" not in low:
                snap.html = SEARCH_RESULTS
            elif "under" in low:
                snap.html = SEARCH_RESULTS
            else:
                snap.html = SEARCH_EMPTY
        elif "collections" in low:
            snap.html = CATEGORY_HTML
        else:
            snap.html = SHOPIFY_HOME
        return snap


class TestKnowledge(unittest.TestCase):
    def test_every_capability_has_pitch(self):
        for cap in CAPABILITIES.values():
            self.assertTrue(cap.name and cap.pitch)


class TestFingerprint(unittest.TestCase):
    def test_detects_shopify_and_ecommerce(self):
        home = PageSnapshot(url="https://x.com", final_url="https://x.com",
                            status=200, html=SHOPIFY_HOME, ok=True, role="homepage")
        prof = SiteProfile(domain="x.com", homepage_url="https://x.com")
        prof = fingerprint([home], prof)
        self.assertEqual(prof.platform, "shopify")
        self.assertTrue(prof.looks_ecommerce)


class TestSearchForm(unittest.TestCase):
    def test_finds_search_endpoint(self):
        home = PageSnapshot(url="https://x.com", final_url="https://x.com",
                            status=200, html=SHOPIFY_HOME, ok=True, role="homepage")
        form = Crawler.find_search_form(home)
        self.assertIsNotNone(form)
        endpoint, param = form
        self.assertIn("{q}", endpoint)
        self.assertEqual(param, "q")


class TestDetectorsEndToEnd(unittest.TestCase):
    def _build_ctx(self):
        config = Config(delay=0.0, respect_robots=False, use_llm=False)
        crawler = FakeCrawler(config)
        home = crawler.fetch("https://x.com", role="homepage")
        prof = SiteProfile(domain="x.com", homepage_url="https://x.com")
        form = Crawler.find_search_form(home)
        prof.has_search = True
        prof.search_endpoint, prof.search_param = form
        cat = crawler.fetch("https://x.com/collections/jackets", role="category")
        pages = [home, cat]
        prof = fingerprint(pages, prof)
        return ScanContext(config=config, crawler=crawler, profile=prof, pages=pages)

    def test_finds_typo_intolerance(self):
        ctx = self._build_ctx()
        findings = []
        for det in ALL_DETECTORS:
            findings.extend(det.run(ctx))
        codes = {f.code for f in findings}
        self.assertIn("no_typo_tolerance", codes)
        # recommendations + autosuggest should also flag on this bare theme
        self.assertIn("no_recommendations", codes)
        self.assertIn("weak_or_no_autosuggest", codes)

    def test_scoring_and_brief(self):
        ctx = self._build_ctx()
        findings = []
        for det in ALL_DETECTORS:
            findings.extend(det.run(ctx))
        fit = fit_score(ctx.profile)
        opp = opportunity_score(findings, ctx.profile)
        tier = priority_tier(fit, opp, ctx.profile)
        self.assertGreater(fit, 40)
        self.assertGreater(opp, 0)
        self.assertIn(tier, ("A", "B", "C"))

        from constructor_scout.models import SiteReport
        report = SiteReport(domain="x.com", profile=ctx.profile, findings=findings,
                            fit_score=fit, opportunity_score=opp, priority=tier)
        report.summary = "test"
        brief = render_brief(report)
        self.assertIn("Constructor.io Prospect Brief", brief)
        self.assertIn("Findings & fixes", brief)


class TestPipelineScan(unittest.TestCase):
    def test_scan_site_with_fake_crawler(self):
        config = Config(delay=0.0, respect_robots=False, use_llm=False)
        # Monkeypatch Crawler used inside scan_site
        orig = pipeline.Crawler
        pipeline.Crawler = FakeCrawler
        try:
            report = pipeline.scan_site("https://x.com", config)
        finally:
            pipeline.Crawler = orig
        self.assertEqual(report.domain, "x.com")
        self.assertTrue(report.profile.has_search)
        self.assertGreater(len(report.findings), 0)
        self.assertTrue(report.outreach.subject)  # templated fallback


class TestDepthModes(unittest.TestCase):
    def _scan(self, depth):
        config = Config(delay=0.0, respect_robots=False, use_llm=False)
        orig = pipeline.Crawler
        pipeline.Crawler = FakeCrawler
        try:
            return pipeline.scan_site("https://x.com", config, depth=depth)
        finally:
            pipeline.Crawler = orig

    def test_shallow_skips_live_query_probing(self):
        shallow = self._scan("shallow")
        deep = self._scan("deep")
        shallow_codes = {f.code for f in shallow.findings}
        deep_codes = {f.code for f in deep.findings}
        # Typo intolerance requires live probing -> deep only.
        self.assertNotIn("no_typo_tolerance", shallow_codes)
        self.assertIn("no_typo_tolerance", deep_codes)
        # Homepage-level gaps still surface in shallow.
        self.assertIn("weak_or_no_autosuggest", shallow_codes)


class TestRegions(unittest.TestCase):
    def test_region_queries(self):
        from constructor_scout.regions import region_queries
        qs = region_queries("United Kingdom", ["fashion", "beauty"])
        self.assertTrue(any("United Kingdom" in q for q in qs))
        self.assertEqual(len([q for q in qs if "fashion" in q]), 1)


class TestSelectionParsing(unittest.TestCase):
    def test_parse(self):
        from constructor_scout.cli import _parse_selection
        self.assertEqual(_parse_selection("1,3", 5), [0, 2])
        self.assertEqual(_parse_selection("1-3", 5), [0, 1, 2])
        self.assertEqual(_parse_selection("9", 5), [])  # out of range dropped


class TestRanking(unittest.TestCase):
    def test_rank_by_discrepancies(self):
        from constructor_scout.models import Finding, Severity, SiteProfile, SiteReport
        from constructor_scout.reporting import rank_by_discrepancies

        def mk(domain, n):
            f = [Finding(f"c{i}", "t", "search", Severity.HIGH, "d", "r") for i in range(n)]
            return SiteReport(domain=domain, profile=SiteProfile(domain=domain, homepage_url=""),
                              findings=f, opportunity_score=n * 10)

        ranked = rank_by_discrepancies([mk("a", 1), mk("b", 3), mk("c", 2)])
        self.assertEqual([r.domain for r in ranked], ["b", "c", "a"])


class TestRegionCommandEndToEnd(unittest.TestCase):
    def test_region_top_selection_writes_deep_brief(self):
        import tempfile
        from constructor_scout import cli
        from constructor_scout.cli import build_parser

        out = tempfile.mkdtemp()
        orig_disc = cli.discover_many
        orig_crawler = pipeline.Crawler
        cli.discover_many = lambda queries, per, config: ["shopa.com", "shopb.com"]
        pipeline.Crawler = FakeCrawler
        try:
            args = build_parser().parse_args(
                ["region", "--country", "Testland", "--top", "1",
                 "--no-llm", "--no-robots", "--delay", "0", "--out", out]
            )
            rc = args.func(args)
        finally:
            cli.discover_many = orig_disc
            pipeline.Crawler = orig_crawler

        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(os.path.join(out, "shortlist.md")))
        deep_briefs = [f for f in os.listdir(out) if f.endswith(".deep.md")]
        self.assertEqual(len(deep_briefs), 1)
        with open(os.path.join(out, deep_briefs[0])) as fh:
            content = fh.read()
        self.assertIn("Problems & Constructor.io solutions", content)
        self.assertIn("Solution (Constructor.io)", content)


class TestApi(unittest.TestCase):
    def setUp(self):
        try:
            import fastapi  # noqa: F401
            from fastapi.testclient import TestClient
        except Exception:
            self.skipTest("fastapi not installed")
        import constructor_scout.api as api
        self.api = api
        self._orig_crawler = pipeline.Crawler
        pipeline.Crawler = FakeCrawler
        self.client = TestClient(api.app)

    def tearDown(self):
        pipeline.Crawler = self._orig_crawler

    def _await(self, job_id):
        import time
        for _ in range(80):
            j = self.client.get(f"/api/job/{job_id}").json()
            if j["status"] in ("done", "error"):
                return j
            time.sleep(0.05)
        self.fail("job did not finish")

    def test_deep_endpoint(self):
        jid = self.client.post("/api/deep", json={"domain": "https://x.com", "use_llm": False}).json()["job_id"]
        j = self._await(jid)
        self.assertEqual(j["status"], "done")
        r = j["result"]
        self.assertTrue(r["findings"])
        self.assertIn("problem", r["findings"][0])
        self.assertIn("solution", r["findings"][0])

    def test_region_endpoint(self):
        self.api.discover_many = lambda queries, per, cfg: ["https://a.com", "https://b.com"]
        jid = self.client.post("/api/region", json={"country": "Testland", "use_llm": False}).json()["job_id"]
        j = self._await(jid)
        self.assertEqual(j["status"], "done")
        self.assertEqual(len(j["result"]["shortlist"]), 2)
        self.assertEqual(j["result"]["shortlist"][0]["rank"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
