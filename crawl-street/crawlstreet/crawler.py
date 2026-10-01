"""The orchestrator: frontier management, bounded concurrency, dedupe, live
progress, and the query-testing phase. Designed to drive a dashboard, so it
keeps a thread-safe snapshot of state and an event log the UI can poll.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional, Set, Tuple
from urllib.parse import urlsplit

from .catalogue import Catalogue
from .config import CrawlConfig
from .extract import parse_page
from .fetcher import Fetcher
from .queries import generate_queries
from .robots import RobotsCache
from .search import discover_endpoint, run_queries, SearchReport


@dataclass
class CrawlState:
    status: str = "idle"          # idle|crawling|querying|done|error|stopped
    phase: str = "idle"
    start_url: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    pages_fetched: int = 0
    pages_ok: int = 0
    products_found: int = 0
    queued: int = 0
    error: Optional[str] = None
    events: Deque[dict] = field(default_factory=lambda: deque(maxlen=400))

    def log(self, level: str, msg: str) -> None:
        self.events.append({"t": round(time.time(), 3), "level": level, "msg": msg})

    def snapshot(self, fetcher_stats: dict, catalogue: Optional[dict],
                 search: Optional[dict]) -> dict:
        elapsed = (self.finished_at or time.time()) - self.started_at if self.started_at else 0
        rate = round(self.pages_fetched / elapsed, 2) if elapsed > 0 else 0
        return {
            "status": self.status,
            "phase": self.phase,
            "start_url": self.start_url,
            "elapsed": round(elapsed, 1),
            "pages_fetched": self.pages_fetched,
            "pages_ok": self.pages_ok,
            "products_found": self.products_found,
            "queued": self.queued,
            "pages_per_sec": rate,
            "fetcher": fetcher_stats,
            "catalogue": catalogue,
            "search": search,
            "error": self.error,
            "events": list(self.events)[-80:],
        }


class Crawler:
    def __init__(self, cfg: CrawlConfig, transport=None) -> None:
        self.cfg = cfg.sanitized()
        self._transport = transport
        self.state = CrawlState(start_url=self.cfg.start_url)
        self.catalogue = Catalogue()
        self.search_report: Optional[SearchReport] = None
        self._fetcher: Optional[Fetcher] = None
        self._seen: Set[str] = set()
        self._stop = asyncio.Event()
        self._base_host = urlsplit(self.cfg.start_url).netloc

    def stop(self) -> None:
        self._stop.set()

    def snapshot(self) -> dict:
        fstats = self._fetcher.stats if self._fetcher else {}
        cat = self.catalogue.summary() if self.catalogue.products else None
        search = self._search_snapshot()
        return self.state.snapshot(fstats, cat, search)

    def _search_snapshot(self) -> Optional[dict]:
        if not self.search_report:
            return None
        return {
            "endpoint": self.search_report.endpoint,
            "param": self.search_report.param,
            "discovered_via": self.search_report.discovered_via,
            "score": self.search_report.score(),
            "results": [r.__dict__ for r in self.search_report.results],
        }

    def full_report(self) -> dict:
        snap = self.snapshot()
        snap["catalogue_sample"] = self.catalogue.sample(100)
        snap["config"] = self.cfg.to_dict()
        return snap

    # --- main entry -------------------------------------------------------
    async def run(self) -> None:
        self.state.status = "crawling"
        self.state.phase = "crawl"
        self.state.started_at = time.time()
        self.state.log("info", f"Starting crawl of {self.cfg.start_url}")
        try:
            async with Fetcher(self.cfg, transport=self._transport) as fetcher:
                self._fetcher = fetcher
                robots = RobotsCache(fetcher._client, enabled=self.cfg.respect_robots)
                await self._crawl(fetcher, robots)
                if self._stop.is_set():
                    self.state.status = "stopped"
                    self.state.log("warn", "Crawl stopped by operator")
                elif self.cfg.run_queries and self.catalogue.products:
                    await self._query_phase(fetcher)
                self.state.status = "done" if not self._stop.is_set() else "stopped"
        except Exception as e:  # pragma: no cover
            self.state.status = "error"
            self.state.error = f"{type(e).__name__}: {e}"
            self.state.log("error", self.state.error)
        finally:
            self.state.finished_at = time.time()
            if self.state.status == "done":
                self.state.phase = "complete"
                self.state.log("info",
                    f"Done. {self.state.pages_ok} pages, "
                    f"{len(self.catalogue.products)} products.")

    # --- crawl phase ------------------------------------------------------
    async def _crawl(self, fetcher: Fetcher, robots: RobotsCache) -> None:
        # frontier holds (url, depth, referer)
        frontier: asyncio.Queue[Tuple[str, int, Optional[str]]] = asyncio.Queue()
        await frontier.put((self.cfg.start_url, 0, None))
        self._seen.add(_norm(self.cfg.start_url))
        self.state.queued = 1
        all_forms = []

        # `outstanding` = items enqueued but not yet fully processed. The crawl
        # is finished exactly when it reaches zero. This avoids the classic
        # get()-vs-inflight race in a naive worker pool.
        outstanding = 1
        done = asyncio.Event()
        lock = asyncio.Lock()

        async def enqueue(url, depth, referer):
            nonlocal outstanding
            async with lock:
                outstanding += 1
            await frontier.put((url, depth, referer))

        async def finish_one():
            nonlocal outstanding
            async with lock:
                outstanding -= 1
                self.state.queued = frontier.qsize()
                if outstanding == 0:
                    done.set()

        async def worker():
            while not done.is_set():
                try:
                    url, depth, referer = await asyncio.wait_for(frontier.get(), timeout=0.3)
                except asyncio.TimeoutError:
                    continue
                try:
                    if (not self._stop.is_set()
                            and self.state.pages_fetched < self.cfg.max_pages):
                        await self._process(url, depth, referer, fetcher, robots,
                                            enqueue, all_forms)
                finally:
                    frontier.task_done()
                    await finish_one()

        workers = [asyncio.create_task(worker()) for _ in range(self.cfg.concurrency)]
        await done.wait()
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

        # Keep forms for the query phase.
        self._search_forms = _dedupe_forms(all_forms)

    async def _process(self, url, depth, referer, fetcher, robots, enqueue, all_forms):
        if self.cfg.respect_robots and not await robots.allowed(url):
            self.state.log("warn", f"robots.txt disallows {url}")
            return
        crawl_delay = (await robots.crawl_delay(url)) or 0.0
        res = await fetcher.fetch(url, referer=referer, crawl_delay=crawl_delay)
        self.state.pages_fetched += 1
        if res.error or res.status >= 400 or res.status == 0:
            self.state.log("warn", f"[{res.status}] {url} {res.error or ''}".strip())
            return
        if "html" not in res.content_type and "<html" not in res.text[:500].lower():
            return
        self.state.pages_ok += 1

        page = parse_page(res.url, res.text)
        all_forms.extend(page.search_forms)

        for prod in page.products:
            if not prod.url:
                prod.url = res.url
            self.catalogue.add(prod)
        if page.products:
            self.state.products_found = len(self.catalogue.products)
            self.state.log("hit",
                f"+{len(page.products)} product(s) on {_short(res.url)} "
                f"[{page.products[0].source}]")

        # enqueue children
        if depth >= self.cfg.max_depth:
            return
        for link in page.links:
            if not self._in_scope(link):
                continue
            nl = _norm(link)
            if nl in self._seen:
                continue
            if len(self._seen) >= self.cfg.max_pages * 3:
                continue  # cap frontier memory
            self._seen.add(nl)
            await enqueue(link, depth + 1, res.url)

    def _in_scope(self, url: str) -> bool:
        if not self.cfg.same_host_only:
            return True
        host = urlsplit(url).netloc
        if host == self._base_host:
            return True
        if self.cfg.include_subdomains:
            base = self._base_host.split(":")[0]
            reg = ".".join(base.split(".")[-2:])
            return host.split(":")[0].endswith(reg)
        return False

    # --- query phase ------------------------------------------------------
    async def _query_phase(self, fetcher: Fetcher) -> None:
        self.state.status = "querying"
        self.state.phase = "query"
        self.state.log("info", "Discovering search endpoint…")
        forms = getattr(self, "_search_forms", [])
        report = await discover_endpoint(fetcher, self.cfg.start_url, forms, self.catalogue)
        if report is None:
            self.state.log("warn", "No working search endpoint found; skipping queries.")
            return
        self.search_report = report
        self.state.log("info",
            f"Search endpoint: {report.endpoint}?{report.param}= (via {report.discovered_via})")

        queries = generate_queries(self.catalogue, self.cfg.max_queries)
        self.state.log("info", f"Generated {len(queries)} catalogue-aware queries.")
        await run_queries(fetcher, report, queries, self.catalogue, self.cfg.start_url)
        s = report.score()
        self.state.log("info",
            f"Query test complete. Search health: {s['health']}% "
            f"(pass={s['pass']} weak={s['weak']} fail={s['fail']} blocked={s['blocked']})")


# --- helpers ---------------------------------------------------------------
def _norm(url: str) -> str:
    p = urlsplit(url)
    path = p.path.rstrip("/") or "/"
    return f"{p.scheme}://{p.netloc}{path}?{p.query}"


def _short(url: str) -> str:
    p = urlsplit(url)
    return (p.path or "/")[:48]


def _dedupe_forms(forms):
    seen = set()
    out = []
    for f in forms:
        k = f"{f.action}|{f.param}"
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out
