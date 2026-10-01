"""Tiny robots.txt fetcher + cache.

Uses the stdlib parser, but fetches through our own polite client so the
robots request carries the same realistic headers as everything else.
"""
from __future__ import annotations

import urllib.robotparser
from typing import Dict, Optional
from urllib.parse import urlsplit, urlunsplit

import httpx


class RobotsCache:
    def __init__(self, client: httpx.AsyncClient, enabled: bool = True) -> None:
        self._client = client
        self._enabled = enabled
        self._cache: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}

    @staticmethod
    def _origin(url: str) -> str:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))

    async def allowed(self, url: str, user_agent: str = "*") -> bool:
        if not self._enabled:
            return True
        origin = self._origin(url)
        if origin not in self._cache:
            self._cache[origin] = await self._load(origin)
        rp = self._cache[origin]
        if rp is None:  # couldn't fetch -> fail open (standard crawler behaviour)
            return True
        try:
            return rp.can_fetch(user_agent, url)
        except Exception:
            return True

    async def crawl_delay(self, url: str, user_agent: str = "*") -> Optional[float]:
        rp = self._cache.get(self._origin(url))
        if rp is None:
            return None
        try:
            d = rp.crawl_delay(user_agent)
            return float(d) if d is not None else None
        except Exception:
            return None

    async def _load(self, origin: str) -> Optional[urllib.robotparser.RobotFileParser]:
        try:
            resp = await self._client.get(origin, timeout=10.0)
            if resp.status_code >= 400:
                return None
            rp = urllib.robotparser.RobotFileParser()
            rp.parse(resp.text.splitlines())
            return rp
        except Exception:
            return None
