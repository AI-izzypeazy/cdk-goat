"""End-to-end pipeline tests driven through an in-process httpx MockTransport.

No sockets, no network — the whole crawl → extract → catalogue → query-test
flow runs against a simulated shop.
"""
import json

import httpx
import pytest

from crawlstreet import CrawlConfig, Crawler
from crawlstreet.extract import parse_page
from crawlstreet.catalogue import Catalogue
from crawlstreet.queries import generate_queries

PRODUCTS = [
    {"name": "Aero Running Shoe", "brand": "Velocity", "category": "Shoes", "price": "89.99", "sku": "SH-1"},
    {"name": "Trail Running Shoe", "brand": "Velocity", "category": "Shoes", "price": "109.99", "sku": "SH-2"},
    {"name": "Classic Cotton T-Shirt", "brand": "Northwind", "category": "Apparel", "price": "24.50", "sku": "AP-1"},
    {"name": "Merino Wool Sweater", "brand": "Northwind", "category": "Apparel", "price": "74.00", "sku": "AP-2"},
    {"name": "Stainless Water Bottle", "brand": "HydroMax", "category": "Accessories", "price": "19.99", "sku": "AC-1"},
    {"name": "Leather Backpack", "brand": "Northwind", "category": "Accessories", "price": "139.00", "sku": "AC-2"},
]


def _page(title, body):
    return f"<!doctype html><html><head><title>{title}</title></head><body><h1>{title}</h1>{body}</body></html>"


def _product_html(p):
    ld = {"@context": "https://schema.org", "@type": "Product", "name": p["name"],
          "url": f"https://shop.test/product/{p['sku']}",
          "brand": {"@type": "Brand", "name": p["brand"]}, "category": p["category"],
          "sku": p["sku"], "offers": {"@type": "Offer", "price": p["price"],
          "priceCurrency": "USD", "availability": "https://schema.org/InStock"}}
    return _page(p["name"], f'<p>{p["name"]}</p><script type="application/ld+json">{json.dumps(ld)}</script>')


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")
    if path == "/":
        links = "".join(f'<a href="/product/{p["sku"]}">{p["name"]}</a>' for p in PRODUCTS)
        form = '<form action="/search"><input type="search" name="q"></form>'
        return httpx.Response(200, text=_page("Demo Shop", form + links),
                              headers={"content-type": "text/html"})
    if path.startswith("/product/"):
        sku = path.rsplit("/", 1)[-1]
        p = next((x for x in PRODUCTS if x["sku"] == sku), None)
        if not p:
            return httpx.Response(404, text="nope")
        return httpx.Response(200, text=_product_html(p), headers={"content-type": "text/html"})
    if path == "/search":
        term = (request.url.params.get("q") or "").lower()
        hits = [p for p in PRODUCTS if term and (
            term in p["name"].lower() or term in p["brand"].lower() or term in p["category"].lower())]
        if hits:
            body = "".join(f'<div class="product">{p["name"]}</div>' for p in hits)
            return httpx.Response(200, text=_page(f"Results {term}", f"<p>{len(hits)} results</p>{body}"),
                                  headers={"content-type": "text/html"})
        return httpx.Response(200, text=_page("No results", "<p>no results found</p>"),
                              headers={"content-type": "text/html"})
    return httpx.Response(404, text="not found")


def _run(cfg):
    import asyncio
    transport = httpx.MockTransport(_handler)
    crawler = Crawler(cfg, transport=transport)
    asyncio.run(crawler.run())
    return crawler


def test_crawl_finds_all_products():
    cfg = CrawlConfig(start_url="https://shop.test/", max_pages=50, max_queries=15,
                      min_delay=0.0, max_delay=0.0, http2=False)
    crawler = _run(cfg)
    assert crawler.state.status == "done"
    assert len(crawler.catalogue.products) == len(PRODUCTS)
    assert crawler.catalogue.brands["Velocity"] == 2
    assert crawler.catalogue.brands["Northwind"] == 3
    ps = crawler.catalogue.price_stats()
    assert ps["min"] == 19.99 and ps["max"] == 139.0


def test_search_endpoint_discovered_and_queries_graded():
    cfg = CrawlConfig(start_url="https://shop.test/", max_pages=50, max_queries=20,
                      min_delay=0.0, max_delay=0.0, http2=False)
    crawler = _run(cfg)
    rep = crawler.search_report
    assert rep is not None
    assert rep.param == "q"
    verdicts = {r.verdict for r in rep.results}
    # at least some queries should pass, and the nonsense control must pass
    assert any(r.verdict == "pass" for r in rep.results)
    nonsense = [r for r in rep.results if r.intent == "nonsense"]
    assert nonsense and nonsense[0].verdict == "pass"
    score = rep.score()
    assert score["health"] is not None


def test_jsonld_extraction_fields():
    html = _product_html(PRODUCTS[0])
    page = parse_page("https://shop.test/product/SH-1", html)
    assert page.products and page.products[0].source == "json-ld"
    p = page.products[0]
    assert p.name == "Aero Running Shoe" and p.brand == "Velocity"
    assert p.price == 89.99 and p.currency == "USD" and p.availability == "InStock"


def test_query_generation_is_catalogue_aware():
    cat = Catalogue()
    for p in PRODUCTS:
        from crawlstreet.extract import Product
        cat.add(Product(name=p["name"], brand=p["brand"], category=p["category"],
                        price=float(p["price"]), source="json-ld"))
    qs = generate_queries(cat, 20)
    intents = {q.intent for q in qs}
    assert "brand" in intents and "category" in intents and "nonsense" in intents
    texts = [q.text.lower() for q in qs]
    assert any("velocity" in t for t in texts)  # a real brand made it in


def test_search_form_detected():
    html = '<form action="/search"><input type="search" name="q"></form>'
    page = parse_page("https://shop.test/", html)
    assert page.search_forms and page.search_forms[0].param == "q"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
