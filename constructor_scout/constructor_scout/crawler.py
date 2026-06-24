"""Polite HTTP crawler that gathers the handful of pages we need per site."""

from __future__ import annotations

import time
import urllib.robotparser
from urllib.parse import urljoin, urlparse, urlencode, urlsplit, parse_qsl

import requests
from bs4 import BeautifulSoup

from .config import Config
from .models import PageSnapshot


def normalize_url(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    return raw


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower().lstrip("www.") or urlparse(url).netloc.lower()


class Crawler:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.user_agent})
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._last_request = 0.0

    # -- politeness ---------------------------------------------------------
    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < self.config.delay:
            time.sleep(self.config.delay - elapsed)
        self._last_request = time.time()

    def _robots_for(self, url: str):
        if not self.config.respect_robots:
            return None
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(urljoin(base, "/robots.txt"))
            try:
                rp.read()
            except Exception:
                rp = None
            self._robots[base] = rp
        return self._robots[base]

    def allowed(self, url: str) -> bool:
        rp = self._robots_for(url)
        if rp is None:
            return True
        try:
            return rp.can_fetch(self.config.user_agent, url)
        except Exception:
            return True

    # -- fetching -----------------------------------------------------------
    def fetch(self, url: str, role: str = "page") -> PageSnapshot:
        url = normalize_url(url)
        snap = PageSnapshot(url=url, role=role)
        if not self.allowed(url):
            snap.error = "blocked by robots.txt"
            return snap
        last_err = ""
        for attempt in range(self.config.retries + 1):
            self._throttle()
            try:
                resp = self.session.get(
                    url, timeout=self.config.timeout, allow_redirects=True
                )
                snap.status = resp.status_code
                snap.final_url = resp.url
                ctype = resp.headers.get("content-type", "")
                if resp.ok and ("html" in ctype or not ctype):
                    snap.html = resp.text
                    snap.ok = True
                    return snap
                last_err = f"status {resp.status_code} ({ctype})"
            except requests.RequestException as exc:
                last_err = str(exc)
            time.sleep(min(2 ** attempt, 8) * 0.5)
        snap.error = last_err
        return snap

    # -- link discovery -----------------------------------------------------
    @staticmethod
    def find_category_and_product_links(home: PageSnapshot, limit: int = 3) -> list[tuple[str, str]]:
        """Return (url, role) guesses for category and product pages."""
        if not home.ok:
            return []
        soup = BeautifulSoup(home.html, "html.parser")
        base = home.final_url or home.url
        cat_keys = ("collection", "category", "/c/", "shop", "products", "catalog", "department")
        prod_keys = ("/product", "/p/", "/dp/", "/products/", "/item")
        cats: list[str] = []
        prods: list[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full = urljoin(base, href)
            if urlparse(full).netloc != urlparse(base).netloc:
                continue
            low = full.lower()
            if any(k in low for k in prod_keys) and full not in prods:
                prods.append(full)
            elif any(k in low for k in cat_keys) and full not in cats:
                cats.append(full)
        out: list[tuple[str, str]] = []
        for u in cats[:limit]:
            out.append((u, "category"))
        for u in prods[:limit]:
            out.append((u, "product"))
        return out

    @staticmethod
    def find_search_form(home: PageSnapshot) -> tuple[str, str] | None:
        """Locate the site search form -> (endpoint_template_with_{q}, param)."""
        if not home.ok:
            return None
        soup = BeautifulSoup(home.html, "html.parser")
        base = home.final_url or home.url
        candidate_inputs = []
        for inp in soup.find_all("input"):
            itype = (inp.get("type") or "").lower()
            name = (inp.get("name") or "").lower()
            attrs = " ".join(
                str(inp.get(k, "")) for k in ("name", "id", "placeholder", "aria-label", "class")
            ).lower()
            if itype == "search" or name in ("q", "query", "s", "search", "keyword", "term") \
                    or "search" in attrs:
                candidate_inputs.append(inp)
        for inp in candidate_inputs:
            form = inp.find_parent("form")
            param = inp.get("name") or "q"
            if form is not None:
                action = form.get("action") or base
                method = (form.get("method") or "get").lower()
                if method != "get":
                    continue
                action_url = urljoin(base, action)
                # Merge any existing hidden params.
                existing = dict(parse_qsl(urlsplit(action_url).query))
                existing[param] = "{q}"
                split = urlsplit(action_url)
                query = urlencode(existing).replace("%7Bq%7D", "{q}")
                endpoint = f"{split.scheme}://{split.netloc}{split.path}?{query}"
                return endpoint, param
        # Fall back to common search endpoints if an input exists but no form.
        if candidate_inputs:
            for guess in ("/search?q={q}", "/search?query={q}", "/catalogsearch/result/?q={q}"):
                return urljoin(base, guess), "q"
        return None

    def search_url(self, endpoint_template: str, term: str) -> str:
        return endpoint_template.replace("{q}", requests.utils.quote(term))
