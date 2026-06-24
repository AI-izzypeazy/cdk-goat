"""Auto-discover ecommerce prospects from a vertical / keyword query.

Uses DuckDuckGo's HTML endpoint (no API key required). Best-effort: results
depend on DDG availability and should be reviewed before outreach.
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse

import requests

from .config import Config

DDG_HTML = "https://html.duckduckgo.com/html/"

# Domains that are marketplaces / not net-new SaaS prospects — filtered out.
EXCLUDE = (
    "amazon.", "ebay.", "etsy.", "walmart.", "aliexpress.", "wikipedia.",
    "facebook.", "instagram.", "pinterest.", "youtube.", "reddit.",
    "google.", "bing.", "duckduckgo.", "linkedin.", "tiktok.", "twitter.",
    "x.com", "shopify.com", "yelp.", "tripadvisor.", "quora.", "medium.",
)


def _clean_domain(url: str) -> str | None:
    try:
        # DDG wraps links: /l/?uddg=<encoded>
        if "uddg=" in url:
            q = parse_qs(urlparse(url).query)
            if "uddg" in q:
                url = unquote(q["uddg"][0])
        netloc = urlparse(url if url.startswith("http") else "https://" + url).netloc.lower()
        netloc = netloc.split(":")[0]
        if not netloc or "." not in netloc:
            return None
        if any(netloc == e.rstrip(".") or netloc.endswith(e) or e in netloc for e in EXCLUDE):
            return None
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return None


def discover(query: str, limit: int, config: Config) -> list[str]:
    """Return a deduped list of candidate ecommerce domains for `query`."""
    headers = {"User-Agent": config.user_agent}
    found: list[str] = []
    seen: set[str] = set()
    try:
        resp = requests.post(
            DDG_HTML, data={"q": query}, headers=headers, timeout=config.timeout
        )
        resp.raise_for_status()
    except requests.RequestException:
        return found

    # Pull href targets from result anchors.
    for raw in re.findall(r'href="([^"]+)"', resp.text):
        url = unescape(raw)
        if "uddg=" not in url and not url.startswith("http"):
            continue
        dom = _clean_domain(url)
        if dom and dom not in seen:
            seen.add(dom)
            found.append(dom)
            if len(found) >= limit:
                break
    return found


def discover_many(queries: list[str], limit_per: int, config: Config) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        for dom in discover(q, limit_per, config):
            if dom not in seen:
                seen.add(dom)
                out.append(dom)
    return out
