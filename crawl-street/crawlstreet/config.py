"""Crawl configuration."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List


@dataclass
class CrawlConfig:
    """Tunable knobs for a crawl + query-test run.

    Defaults are chosen to be *efficient but polite*: enough concurrency to be
    fast, enough backoff and jitter to stay unblocked on real sites.
    """

    # --- Target ---
    start_url: str = ""

    # --- Scope ---
    max_pages: int = 200            # hard ceiling on fetched pages
    max_depth: int = 4              # link depth from the start URL
    same_host_only: bool = True     # don't wander off the target domain
    include_subdomains: bool = True # shop.example.com counts as example.com

    # --- Throughput / politeness ---
    concurrency: int = 8            # global in-flight requests
    per_host_concurrency: int = 4   # simultaneous requests to one host
    min_delay: float = 0.25         # min seconds between requests to a host
    max_delay: float = 0.75         # max; actual delay is random in [min, max]
    timeout: float = 20.0           # per-request timeout (seconds)

    # --- Anti-block hygiene (used by respectful crawlers to avoid bans) ---
    rotate_user_agents: bool = True
    http2: bool = True
    respect_robots: bool = True     # operator override; you own the consequences
    max_retries: int = 4            # retries on 429 / 5xx / transport errors
    backoff_base: float = 1.5       # exponential backoff base (seconds)
    proxies: List[str] = field(default_factory=list)  # optional rotating pool
    render_js: bool = False         # use a headless browser when available
    render_wait: float = 2.0        # seconds to let JS settle before scraping

    # --- Query testing ---
    run_queries: bool = True
    max_queries: int = 25           # how many auto-generated queries to run
    query_timeout: float = 15.0

    def sanitized(self) -> "CrawlConfig":
        """Clamp values into safe ranges so the UI can't push nonsense in."""
        c = CrawlConfig(**{**asdict(self)})
        c.max_pages = max(1, min(c.max_pages, 5000))
        c.max_depth = max(0, min(c.max_depth, 12))
        c.concurrency = max(1, min(c.concurrency, 64))
        c.per_host_concurrency = max(1, min(c.per_host_concurrency, c.concurrency))
        c.min_delay = max(0.0, c.min_delay)
        c.max_delay = max(c.min_delay, c.max_delay)
        c.max_retries = max(0, min(c.max_retries, 10))
        c.max_queries = max(0, min(c.max_queries, 200))
        return c

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CrawlConfig":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in (data or {}).items() if k in known})
