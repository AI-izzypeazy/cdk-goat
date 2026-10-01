"""CLI entrypoint.

  python -m crawlstreet                      # launch the dashboard (default)
  python -m crawlstreet serve --port 8787    # dashboard on a chosen port
  python -m crawlstreet crawl URL [opts]     # headless one-shot, prints JSON
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .config import CrawlConfig
from .crawler import Crawler
from .server import serve


def _add_crawl_opts(p: argparse.ArgumentParser) -> None:
    p.add_argument("--max-pages", type=int, default=150)
    p.add_argument("--max-depth", type=int, default=4)
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--max-queries", type=int, default=25)
    p.add_argument("--no-robots", action="store_true", help="ignore robots.txt (you own this)")
    p.add_argument("--no-queries", action="store_true", help="crawl only, skip search test")
    p.add_argument("--render", action="store_true", help="enable JS render fallback (needs playwright)")


def _cfg_from_args(args) -> CrawlConfig:
    return CrawlConfig(
        start_url=args.url,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        concurrency=args.concurrency,
        max_queries=args.max_queries,
        respect_robots=not args.no_robots,
        run_queries=not args.no_queries,
        render_js=args.render,
    )


async def _run_headless(cfg: CrawlConfig) -> dict:
    crawler = Crawler(cfg)
    await crawler.run()
    return crawler.full_report()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="crawlstreet", description="Crawl Street")
    sub = parser.add_subparsers(dest="cmd")

    s = sub.add_parser("serve", help="launch the dashboard (default)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8787)

    c = sub.add_parser("crawl", help="headless one-shot crawl, prints JSON report")
    c.add_argument("url")
    _add_crawl_opts(c)
    c.add_argument("-o", "--output", help="write JSON report to this file")

    args = parser.parse_args(argv)

    if args.cmd == "crawl":
        cfg = _cfg_from_args(args)
        report = asyncio.run(_run_headless(cfg))
        text = json.dumps(report, indent=2, default=str)
        if args.output:
            with open(args.output, "w") as f:
                f.write(text)
            print(f"Report written to {args.output}", file=sys.stderr)
        else:
            print(text)
        return 0

    # default: serve
    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8787)
    serve(host, port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
