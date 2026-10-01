"""Optional headless-browser renderer (Playwright).

This is a *soft* dependency. If Playwright isn't installed the crawler simply
runs HTTP-only; render_js just becomes a no-op. When present, it handles
JS-rendered catalogues and clears many soft bot walls that gate on JS execution.
"""
from __future__ import annotations

from typing import Optional

from .config import CrawlConfig
from .useragents import UserAgentRotator


class PlaywrightRenderer:
    def __init__(self, cfg: CrawlConfig, ua: UserAgentRotator) -> None:
        self.cfg = cfg
        self.ua = ua
        self._pw = None
        self._browser = None
        self._context = None

    async def start(self) -> None:
        from playwright.async_api import async_playwright  # raises if missing
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        profile = self.ua.profile()
        self._context = await self._browser.new_context(
            user_agent=profile["ua"],
            locale="en-US",
            viewport={"width": 1366, "height": 900},
        )
        # Strip the obvious webdriver tell that bot-walls look for.
        await self._context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )

    async def render(self, url: str, referer: Optional[str]) -> Optional[str]:
        if self._context is None:
            return None
        page = await self._context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded",
                            timeout=int(self.cfg.timeout * 1000),
                            referer=referer or None)
            await page.wait_for_timeout(int(self.cfg.render_wait * 1000))
            return await page.content()
        except Exception:
            return None
        finally:
            await page.close()

    async def close(self) -> None:
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
