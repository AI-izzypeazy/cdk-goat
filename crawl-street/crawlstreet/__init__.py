"""Crawl Street — a mega-efficient, polite e-commerce crawler and query tester.

Public surface:
    from crawlstreet import Crawler, CrawlConfig
"""
from .config import CrawlConfig
from .crawler import Crawler

__all__ = ["Crawler", "CrawlConfig"]
__version__ = "1.0.0"
