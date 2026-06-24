"""Command-line interface for Constructor Scout.

Two ways in:
  scan    — directly audit a URL / list / discovery query (deep, with briefs)
  region  — phase-1: discover + shallow-scan an entire country, rank by gaps,
            let you pick a prospect; phase-2: deep-scan it into a
            problem → Constructor.io-solution brief
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

from .config import DEFAULT_MODEL, Config
from .discovery import discover_many
from .pipeline import scan_many, scan_site
from .regions import region_queries
from .reporting import (
    actionable_findings,
    rank_by_discrepancies,
    render_shortlist,
    write_deep_brief,
    write_leaderboard,
    write_shortlist,
    write_site_report,
)


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #
def _read_targets_file(path: str) -> list[str]:
    with open(path, newline="", encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    targets: list[str] = []
    if any("," in ln for ln in lines):
        for row in csv.reader(lines):
            if row and row[0].strip() and not row[0].lower().startswith(("domain", "url", "#")):
                targets.append(row[0].strip())
    else:
        for ln in lines:
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                targets.append(ln)
    return targets


def _config_from(args) -> Config:
    return Config(
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


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--out", default="scout_output", help="Output directory (default scout_output).")
    p.add_argument("--max-pages", type=int, default=6, help="Max pages per site on deep scans (default 6).")
    p.add_argument("--delay", type=float, default=1.0, help="Politeness delay between requests (default 1.0s).")
    p.add_argument("--timeout", type=float, default=15.0, help="Per-request timeout seconds (default 15).")
    p.add_argument("--no-robots", action="store_true", help="Do not honor robots.txt (not recommended).")
    p.add_argument("--no-llm", action="store_true", help="Disable Claude enrichment; use templates.")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"Claude model (default {DEFAULT_MODEL}).")
    p.add_argument("--api-key", default=None, help="Anthropic API key (else uses ANTHROPIC_API_KEY).")
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose progress to stderr.")


def _parse_selection(raw: str, n: int) -> list[int]:
    """Parse '1,3,5' or '1-3' (1-based) into 0-based indices within range."""
    picked: list[int] = []
    for chunk in raw.replace(" ", "").split(","):
        if not chunk:
            continue
        if "-" in chunk:
            a, b = chunk.split("-", 1)
            if a.isdigit() and b.isdigit():
                picked.extend(range(int(a), int(b) + 1))
        elif chunk.isdigit():
            picked.append(int(chunk))
    return [i - 1 for i in picked if 1 <= i <= n]


def _llm_note(config: Config) -> None:
    if config.use_llm and not config.resolved_api_key():
        print("Note: no ANTHROPIC_API_KEY found — using templated copy "
              "(pass --api-key or set the env var for tailored examples).", file=sys.stderr)


# --------------------------------------------------------------------------- #
# `scan` command
# --------------------------------------------------------------------------- #
def cmd_scan(args) -> int:
    config = _config_from(args)
    targets: list[str] = list(args.url)
    if args.targets:
        targets.extend(_read_targets_file(args.targets))
    if args.discover:
        print(f"Discovering prospects for {len(args.discover)} query(ies)...", file=sys.stderr)
        targets.extend(discover_many(args.discover, args.discover_limit, config))

    seen: set[str] = set()
    targets = [t for t in targets if not (t in seen or seen.add(t))]
    if not targets:
        print("No targets. Use --url, --targets FILE, or --discover QUERY.", file=sys.stderr)
        return 2

    _llm_note(config)
    print(f"Scanning {len(targets)} site(s) → {config.out_dir}/", file=sys.stderr)
    reports = scan_many(targets, config, depth="deep")

    os.makedirs(config.out_dir, exist_ok=True)
    for r in reports:
        paths = write_site_report(r, config.out_dir)
        flag = "" if r.priority != "EXISTING" else " (existing customer)"
        print(f"  [{r.priority}] {r.domain}  fit={r.fit_score:.0f} opp={r.opportunity_score:.0f}"
              f"  → {paths['brief']}{flag}")
    board = write_leaderboard(reports, config.out_dir)
    print(f"\nLeaderboard: {board['md']}\nCSV:         {board['csv']}")
    return 0


# --------------------------------------------------------------------------- #
# `region` command — the interactive two-phase workflow
# --------------------------------------------------------------------------- #
def cmd_region(args) -> int:
    config = _config_from(args)
    verticals = [v.strip() for v in args.verticals.split(",")] if args.verticals else None

    # Phase 1a: discover sites in the region.
    queries = region_queries(args.country, verticals)
    print(f"Discovering retail/ecommerce sites in '{args.country}' "
          f"({len(queries)} queries)...", file=sys.stderr)
    domains = discover_many(queries, args.per_vertical, config)
    if args.max_sites:
        domains = domains[: args.max_sites]
    if not domains:
        print("No sites discovered. Discovery needs open outbound HTTPS; try "
              "again or use `scan --targets` with your own list.", file=sys.stderr)
        return 1
    print(f"Found {len(domains)} candidate sites. Shallow-scanning for gaps...", file=sys.stderr)

    # Phase 1b: shallow scan + rank.
    reports = scan_many(domains, config, depth="shallow")
    os.makedirs(config.out_dir, exist_ok=True)
    ranked = rank_by_discrepancies(reports)
    write_shortlist(reports, config.out_dir, region=args.country)
    print()
    print(render_shortlist(reports, region=args.country))

    if args.no_deep:
        print(f"Shortlist written to {os.path.join(config.out_dir, 'shortlist.md')}")
        print("Re-run with --select N (or --top N) to deep-scan a prospect.")
        return 0

    # Phase 1c: selection.
    if args.select:
        idx = _parse_selection(args.select, len(ranked))
    elif args.top:
        idx = list(range(min(args.top, len(ranked))))
    elif sys.stdin.isatty():
        try:
            raw = input("\nSelect prospect number(s) to deep-scan (e.g. 1 or 1,3) or Enter to skip: ")
        except EOFError:
            raw = ""
        idx = _parse_selection(raw, len(ranked)) if raw.strip() else []
    else:
        print(f"\nShortlist written to {os.path.join(config.out_dir, 'shortlist.md')}")
        print("Non-interactive: re-run with --select N (or --top N) to deep-scan.")
        return 0

    if not idx:
        print("No prospect selected; stopping after shortlist.")
        return 0

    # Phase 2: deep scan selected prospect(s).
    _llm_note(config)
    selected = [ranked[i] for i in idx]
    print(f"\nDeep-scanning {len(selected)} selected prospect(s)...", file=sys.stderr)
    for r in selected:
        deep = scan_site(r.domain, config, depth="deep")
        paths = write_deep_brief(deep, config.out_dir)
        gaps = len(actionable_findings(deep))
        print(f"  {deep.domain}: {gaps} problem(s) → {paths['brief']}")
    return 0


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="constructor-scout",
        description="Scan retail/ecommerce sites for product-discovery gaps "
        "Constructor.io can solve, and produce prospect briefs.",
    )
    sub = p.add_subparsers(dest="command")

    # scan
    sp = sub.add_parser("scan", help="Audit a URL / list / discovery query directly (deep).")
    sp.add_argument("--url", action="append", default=[], metavar="URL", help="A site to scan (repeatable).")
    sp.add_argument("--targets", metavar="FILE", help="Text/CSV file of domains/URLs.")
    sp.add_argument("--discover", action="append", default=[], metavar="QUERY",
                    help="Auto-discover prospects via web search (repeatable).")
    sp.add_argument("--discover-limit", type=int, default=8, help="Max prospects per discovery query (default 8).")
    _add_common(sp)
    sp.set_defaults(func=cmd_scan)

    # region
    rp = sub.add_parser("region", help="Discover + rank a whole country, then deep-scan a pick.")
    rp.add_argument("--country", required=True, help="Country/region to prospect (e.g. 'United Kingdom').")
    rp.add_argument("--verticals", default=None, help="Comma-separated verticals (default: a broad retail sweep).")
    rp.add_argument("--per-vertical", type=int, default=5, help="Max sites discovered per query (default 5).")
    rp.add_argument("--max-sites", type=int, default=25, help="Cap total sites shallow-scanned (default 25).")
    rp.add_argument("--top", type=int, default=0, help="Auto deep-scan the top N ranked prospects (skip prompt).")
    rp.add_argument("--select", default=None, help="Deep-scan these shortlist rows, e.g. '1,3' (skip prompt).")
    rp.add_argument("--no-deep", action="store_true", help="Stop after the ranked shortlist.")
    _add_common(rp)
    rp.set_defaults(func=cmd_region)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Back-compat / convenience: bare flags default to the `scan` command.
    if argv and argv[0] not in ("scan", "region", "-h", "--help"):
        argv = ["scan"] + argv
    args = build_parser().parse_args(argv)
    if not getattr(args, "func", None):
        build_parser().print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
