"""Realistic header construction + user-agent rotation.

Sites fingerprint on more than the UA string: they check header *ordering*,
Accept values, Sec-Fetch metadata, and whether a browser-shaped Accept-Language
is present. Sending a full, coherent header set is the single biggest win for
staying unblocked without doing anything adversarial.
"""
from __future__ import annotations

import itertools
import random
from typing import Dict, Iterator

# A small pool of current, real desktop UAs. Paired with matching Sec-CH-UA
# hints so the header set is internally consistent (mismatches get flagged).
_UA_PROFILES = [
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "ch_ua": '"Chromium";v="125", "Google Chrome";v="125", "Not.A/Brand";v="24"',
        "platform": '"Windows"',
    },
    {
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "ch_ua": '"Chromium";v="125", "Google Chrome";v="125", "Not.A/Brand";v="24"',
        "platform": '"macOS"',
    },
    {
        "ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "ch_ua": '"Chromium";v="124", "Google Chrome";v="124", "Not.A/Brand";v="24"',
        "platform": '"Linux"',
    },
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) "
              "Gecko/20100101 Firefox/126.0",
        "ch_ua": "",  # Firefox doesn't send client hints
        "platform": '"Windows"',
    },
    {
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
              "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "ch_ua": "",
        "platform": '"macOS"',
    },
]

_ACCEPT_LANG = "en-US,en;q=0.9"


class UserAgentRotator:
    """Hands out coherent header sets, cycling through the profile pool."""

    def __init__(self, rotate: bool = True) -> None:
        self._rotate = rotate
        self._cycle: Iterator[dict] = itertools.cycle(_UA_PROFILES)
        self._fixed = random.choice(_UA_PROFILES)

    def profile(self) -> dict:
        return next(self._cycle) if self._rotate else self._fixed

    def headers(self, *, referer: str | None = None, is_document: bool = True) -> Dict[str, str]:
        p = self.profile()
        h: Dict[str, str] = {
            "User-Agent": p["ua"],
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
                if is_document
                else "application/json,text/plain,*/*;q=0.8"
            ),
            "Accept-Language": _ACCEPT_LANG,
            "Accept-Encoding": "gzip, deflate, br",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document" if is_document else "empty",
            "Sec-Fetch-Mode": "navigate" if is_document else "cors",
            "Sec-Fetch-Site": "same-origin" if referer else "none",
            "Sec-Fetch-User": "?1",
            "Connection": "keep-alive",
        }
        if p["ch_ua"]:
            h["sec-ch-ua"] = p["ch_ua"]
            h["sec-ch-ua-mobile"] = "?0"
            h["sec-ch-ua-platform"] = p["platform"]
        if referer:
            h["Referer"] = referer
        return h
