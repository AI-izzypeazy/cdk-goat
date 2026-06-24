"""Command-line interface for Constructor Scout."""

from __future__ import annotations

import argparse
import csv
import os
import sys

from .config import DEFAULT_MODEL, Config
from .discovery import discover_many
from .pipeline import scan_many
from .reporting import write_leaderboard, write_site_report


def _read_targets_file(path: str) -> list[str]:
    targets: list[str] = []
    with open(path, newline="", encoding="utf-8") as fh:
        sample = fh.read()
    fh_lines = sample.splitlines()
    # Support both plain-text (one per line) and CSV (first column).
    if any("," in ln for ln in fh_lines):
        reader = csv.reader(fh_lines)
        for row in reader:
            if row and row[0].strip() and not row[0].lower().startswith(("domain", "url", "#")):
                targets.append(row[0].strip())
    else:
        for ln in fh_lines:
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                targets.append(ln)
    return targets


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="constructor-scout",
        description="Scan retail/ecommerce sites for product-discovery gaps "
        "Constructor.io can solve, and produce prospect briefs.",
    )
    src = p.add_argument_group("targets (choose at least one)")
    src.add_argument("--url", action="append", default=[], metavar="URL",
                     help="A single site to scan (repeatable).")
    src.add_argument("--targets", metavar="FILE",
                     help="Text/CSV file of domains or URLs (one per line / first column).")
    src.add_argument("--discover", metavar="QUERY", action="append", default=[],
                     help="Auto-discover prospects via web search for this query/vertical (repeatable).")
    src.add_argument("--discover-limit", type=int, default=8,
                     help="Max prospects to discover per query (default 8).")

    out = p.add_argument_group("output")
    out.add_argument("--out", default="scout_output", help="Output directory (default scout_output).")

    crawl = p.add_argument_group("crawl behavior")
    crawl.add_argument("--max-pages", type=int, default=6, help="Max pages per site (default 6).")
    crawl.add_argument("--delay", type=float, default=1.0, help="Politeness delay between requests (default 1.0s).")
    crawl.add_argument("--timeout", type=float, default=15.0, help="Per-request timeout seconds (default 15).")
    crawl.add_argument("--no-robots", action="store_true", help="Do not honor robots.txt (not recommended).")

    llm = p.add_argument_group("llm")
    llm.add_argument("--no-llm", action="store_true", help="Disable Claude enrichment; use templates.")
    llm.add_argument("--model", default=DEFAULT_MODEL, help=f"Claude model (default {DEFAULT_MODEL}).")
    llm.add_argument("--api-key", default=None, help="Anthropic API key (else uses ANTHROPIC_API_KEY).")

    p.add_argument("-v", "--verbose", action="store_true", help="Verbose progress to stderr.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    config = Config(
        out_dir=args.out,
        timeout=args.timeout,
        delay=args.delay,
        max_pages=args.max_pages,
        respect_robots=not args.no_robots,
        use_llm=not args.no_llm,
        model=args.model,
        api_key=args.api_key,
        verbose=args.verbose,
    )

    targets: list[str] = list(args.url)
    if args.targets:
        targets.extend(_read_targets_file(args.targets))
    if args.discover:
        print(f"Discovering prospects for {len(args.discover)} query(ies)...", file=sys.stderr)
        discovered = discover_many(args.discover, args.discover_limit, config)
        print(f"  found {len(discovered)} candidate domains", file=sys.stderr)
        targets.extend(discovered)

    # de-dupe, preserve order
    seen: set[str] = set()
    targets = [t for t in targets if not (t in seen or seen.add(t))]

    if not targets:
        print("No targets. Use --url, --targets FILE, or --discover QUERY.", file=sys.stderr)
        return 2

    if config.use_llm and not config.resolved_api_key():
        print("Note: no ANTHROPIC_API_KEY found — using templated copy "
              "(pass --api-key or set the env var for tailored examples).", file=sys.stderr)

    print(f"Scanning {len(targets)} site(s) → {config.out_dir}/", file=sys.stderr)
    reports = scan_many(targets, config)

    os.makedirs(config.out_dir, exist_ok=True)
    for r in reports:
        paths = write_site_report(r, config.out_dir)
        flag = "" if r.priority != "EXISTING" else " (existing customer)"
        print(f"  [{r.priority}] {r.domain}  fit={r.fit_score:.0f} opp={r.opportunity_score:.0f}"
              f"  → {paths['brief']}{flag}")

    board = write_leaderboard(reports, config.out_dir)
    print(f"\nLeaderboard: {board['md']}")
    print(f"CSV:         {board['csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
