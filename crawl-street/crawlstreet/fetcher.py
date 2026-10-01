"""The polite, resilient fetch layer.

Responsibilities:
  * one shared HTTP/2 client (connection reuse = speed)
  * realistic rotating headers
  * per-host rate limiting with jitter
  * exponential backoff honouring Retry-After on 429 / 5xx
  * optional rotating proxy pool
  * optional headless-browser render fallback for JS-only pages
"""
from __future__ import annotations

import asyncio
import itertools
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from urllib.parse import urlsplit

import httpx

from .config import CrawlConfig
from .useragents import UserAgentRotator


@dataclass
class FetchResult:
    url: str              # final URL after redirects
    status: int
    text: str
    content_type: str
    elapsed: float
    rendered: bool = False
    error: Optional[str] = None
    from_cache: bool = False


@dataclass
class _HostState:
    """Per-host politeness gate."""
    semaphore: asyncio.Semaphore
    next_allowed: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class Fetcher:
    def __init__(self, cfg: CrawlConfig, transport=None) -> None:
        self.cfg = cfg
        self._transport = transport  # test seam: inject an httpx transport
        self.ua = UserAgentRotator(rotate=cfg.rotate_user_agents)
        self._global_sem = asyncio.Semaphore(cfg.concurrency)
        self._hosts: Dict[str, _HostState] = {}
        self._hosts_lock = asyncio.Lock()
        self._clients: List[httpx.AsyncClient] = []
        self._client_cycle = None
        self._client: Optional[httpx.AsyncClient] = None  # default/first client
        self._renderer = None  # lazy headless browser
        self.stats = {
            "requests": 0, "ok": 0, "blocked": 0, "errors": 0,
            "retries": 0, "rendered": 0, "bytes": 0,
        }

    async def __aenter__(self) -> "Fetcher":
        limits = httpx.Limits(
            max_connections=self.cfg.concurrency * 2,
            max_keepalive_connections=self.cfg.concurrency,
        )
        http2 = self.cfg.http2 and _h2_available()
        common = dict(http2=http2, follow_redirects=True,
                      timeout=self.cfg.timeout, limits=limits)
        if self._transport is not None:
            self._clients = [httpx.AsyncClient(transport=self._transport, **common)]
        elif self.cfg.proxies:
            # one client per proxy so we can rotate egress IPs across requests
            self._clients = [httpx.AsyncClient(proxy=p, **common) for p in self.cfg.proxies]
        else:
            self._clients = [httpx.AsyncClient(**common)]
        self._client = self._clients[0]
        self._client_cycle = itertools.cycle(self._clients)
        self.stats["http2"] = http2
        return self

    async def __aexit__(self, *exc) -> None:
        for c in self._clients:
            await c.aclose()
        if self._renderer:
            await self._renderer.close()

    def _pick_client(self) -> httpx.AsyncClient:
        return next(self._client_cycle) if self._client_cycle else self._client  # type: ignore

    async def _host_state(self, host: str) -> _HostState:
        async with self._hosts_lock:
            st = self._hosts.get(host)
            if st is None:
                st = _HostState(asyncio.Semaphore(self.cfg.per_host_concurrency))
                self._hosts[host] = st
            return st

    async def _respect_delay(self, st: _HostState, extra_delay: float = 0.0) -> None:
        async with st.lock:
            now = time.monotonic()
            wait = st.next_allowed - now
            if wait > 0:
                await asyncio.sleep(wait)
            jitter = random.uniform(self.cfg.min_delay, self.cfg.max_delay)
            st.next_allowed = time.monotonic() + max(jitter, extra_delay)

    async def fetch(
        self,
        url: str,
        *,
        referer: str | None = None,
        is_document: bool = True,
        crawl_delay: float = 0.0,
        allow_render: bool = True,
    ) -> FetchResult:
        assert self._clients, "use Fetcher as an async context manager"
        host = urlsplit(url).netloc
        st = await self._host_state(host)

        attempt = 0
        last_err = "unknown"
        while attempt <= self.cfg.max_retries:
            async with self._global_sem, st.semaphore:
                await self._respect_delay(st, crawl_delay)
                headers = self.ua.headers(referer=referer, is_document=is_document)
                start = time.monotonic()
                self.stats["requests"] += 1
                try:
                    resp = await self._pick_client().get(url, headers=headers)
                except (httpx.TransportError, httpx.HTTPError) as e:
                    last_err = f"{type(e).__name__}: {e}"
                    self.stats["errors"] += 1
                    await self._backoff(attempt)
                    attempt += 1
                    self.stats["retries"] += 1
                    continue

            elapsed = time.monotonic() - start
            ctype = resp.headers.get("content-type", "")

            if resp.status_code in (429, 503) or 500 <= resp.status_code < 600:
                last_err = f"HTTP {resp.status_code}"
                if resp.status_code in (429, 403):
                    self.stats["blocked"] += 1
                retry_after = _parse_retry_after(resp.headers.get("retry-after"))
                await self._backoff(attempt, retry_after)
                attempt += 1
                self.stats["retries"] += 1
                continue

            if resp.status_code == 403:
                # Often a soft bot wall. One render-fallback shot can clear it.
                self.stats["blocked"] += 1
                if allow_render and self.cfg.render_js:
                    r = await self._render(url, referer)
                    if r is not None:
                        return r
                last_err = "HTTP 403"
                return FetchResult(str(resp.url), 403, resp.text, ctype, elapsed,
                                   error="blocked (403)")

            text = resp.text
            self.stats["ok"] += 1
            self.stats["bytes"] += len(resp.content)

            # Detect JS-only shells (near-empty <body>) and render if allowed.
            if (allow_render and self.cfg.render_js and is_document
                    and _looks_like_js_shell(text)):
                r = await self._render(url, referer)
                if r is not None:
                    return r

            return FetchResult(str(resp.url), resp.status_code, text, ctype, elapsed)

        return FetchResult(url, 0, "", "", 0.0, error=f"gave up after retries: {last_err}")

    async def _backoff(self, attempt: int, retry_after: Optional[float] = None) -> None:
        if retry_after is not None:
            delay = min(retry_after, 60.0)
        else:
            delay = (self.cfg.backoff_base ** attempt) + random.uniform(0, 1)
        await asyncio.sleep(min(delay, 60.0))

    # --- Optional headless render fallback (Playwright if present) ---------
    async def _render(self, url: str, referer: str | None) -> Optional[FetchResult]:
        try:
            if self._renderer is None:
                from .render import PlaywrightRenderer  # local import; optional dep
                self._renderer = PlaywrightRenderer(self.cfg, self.ua)
                await self._renderer.start()
            html = await self._renderer.render(url, referer)
            if html:
                self.stats["rendered"] += 1
                return FetchResult(url, 200, html, "text/html", 0.0, rendered=True)
        except Exception:
            return None
        return None


def _h2_available() -> bool:
    try:
        import h2  # noqa: F401
        return True
    except Exception:
        return False


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(value)
            return max(0.0, dt.timestamp() - time.time())
        except Exception:
            return None


def _looks_like_js_shell(html: str) -> bool:
    """Heuristic: lots of script, almost no text in <body>."""
    if len(html) > 4000:
        return False
    low = html.lower()
    has_root = ('id="root"' in low or 'id="app"' in low or "__next" in low)
    return has_root and low.count("<p") < 2 and low.count("<h1") < 2
