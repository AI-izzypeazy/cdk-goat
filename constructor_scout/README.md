# Constructor Scout

An agent that scans retail/ecommerce websites for **product-discovery gaps that
Constructor.io can solve**, scores them as sales prospects, and produces a
ready-to-send brief with **concrete examples and fixes** for each site.

It exists to do one job: point a salesperson at a list of (or a whole vertical
of) ecommerce sites and get back a ranked pipeline of prospects, each with
specific, demonstrable reasons to reach out.

## The regional prospecting workflow (primary flow)

```
You enter a country  ─►  agent discovers retail/ecommerce sites there
                     ─►  shallow-scans all of them
                     ─►  ranks a shortlist by # of discovery gaps
                     ─►  you pick a target prospect
                     ─►  agent deep-scans it and returns, per gap:
                            1) the Problem   2) the Constructor.io solution/fix
```

```bash
# Interactive: discover UK sites, rank them, prompt you to pick, deep-scan the pick
python -m constructor_scout region --country "United Kingdom" -v

# Non-interactive: auto deep-scan the top 3 most-gap-ridden prospects
python -m constructor_scout region --country "Germany" --top 3 --out out

# Pick specific rows from the ranked shortlist
python -m constructor_scout region --country "Australia" --select 1,4 --out out

# Just the ranked shortlist, no deep scan
python -m constructor_scout region --country "Canada" --no-deep --out out
```

Phase 1 writes `shortlist.md` / `shortlist.csv` (ranked, most gaps first). Phase 2
writes `<domain>.deep.md` — a Problem → Constructor.io-solution brief — plus
`<domain>.deep.json`. See [`examples/sample_output/demo-storefront.deep.md`](examples/sample_output/demo-storefront.deep.md).

---

## What it detects

For each site it crawls the homepage plus a few category/product/search pages and
runs deterministic detectors, then (optionally) has Claude turn the findings into
site-specific examples and outreach copy.

| Gap | How it's detected | Constructor capability |
|---|---|---|
| **No / hidden site search** | No search form or endpoint found | Search |
| **No typo tolerance** | Head term returns results, misspelling returns zero | Typo Tolerance & Synonyms |
| **Head-term zero results** | A common on-site term returns an empty results page | Search / Zero-results recovery |
| **No natural-language search** | `"<term> under $50"` returns nothing while `"<term>"` works | NL / Semantic Search |
| **No autosuggest** | No typeahead/autocomplete wiring on the search box | Autosuggest |
| **Thin faceting** | Category/search page has little/no filtering | Browse & Facets |
| **No recommendations** | No "you may also like / customers also bought" pods | Recommendations |
| **No personalization** | No personalized merchandising signals | Personalization |

It also **fingerprints the platform** (Shopify, Magento/Adobe Commerce, Salesforce
Commerce Cloud, BigCommerce, WooCommerce, …) and the **incumbent discovery vendor**
(Algolia, Searchspring, Bloomreach, Klevu, Coveo, Nosto, …). Sites already running
**Constructor.io** are flagged `EXISTING` and routed to expansion, not new-logo.

## Output (per run, into `--out`)

- `<domain>.json` — machine-readable findings, scores and profile.
- `<domain>.brief.md` — a sales brief: snapshot, prioritized findings + fixes,
  concrete examples, and a draft outreach email.
- `leaderboard.md` / `leaderboard.csv` — all scanned sites ranked by
  **fit × opportunity** with priority tiers (A / B / C / EXISTING).

See [`examples/sample_output/`](examples/sample_output/) for a real generated
brief and leaderboard.

## Install

```bash
cd constructor_scout
pip install -r requirements.txt        # requests, beautifulsoup4, anthropic
# or: pip install .   (installs the `constructor-scout` command)
```

Set your Anthropic key for tailored examples + outreach (optional — the tool
falls back to templated copy without it):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Direct scanning (`scan`)

When you already know which sites to audit, `scan` deep-scans them straight away
and writes a full brief + leaderboard:

```bash
# Single site (bare flags also work: `python -m constructor_scout --url ...`)
python -m constructor_scout scan --url allbirds.com --out out -v

# A list you control (CSV or one-per-line; see examples/targets.example.csv)
python -m constructor_scout scan --targets prospects.csv --out out

# Auto-discover prospects from a vertical, then scan them
python -m constructor_scout scan \
  --discover "best independent outdoor gear online stores" \
  --discover-limit 10 --out out
```

### Commands & flags

- `region --country "<name>"` — discover → rank → select → deep-scan.
  `--verticals`, `--per-vertical N`, `--max-sites N`, `--top N`, `--select 1,3`, `--no-deep`.
- `scan` — `--url` (repeatable), `--targets FILE`, `--discover QUERY` (repeatable), `--discover-limit N`.
- Shared: `--out DIR`, `--model`, `--no-llm`, `--api-key`, `--max-pages`, `--delay`, `--timeout`, `--no-robots`, `-v`.

## Try it offline

A local fixture storefront (a deliberately gap-ridden Shopify-style site) lets you
see a full brief without crawling anything real:

```bash
python examples/demo_server.py &        # http://127.0.0.1:8077
python -m constructor_scout scan --url http://127.0.0.1:8077 --no-robots --delay 0 --out demo_out -v
```

## How it works

```
targets ──► Crawler (robots-aware, rate-limited)
              │  homepage + category/product/search pages
              ▼
        Fingerprint (platform + incumbent vendor + ecommerce signals)
              ▼
        Detectors (search presence/quality, autosuggest, facets, recs, personalization)
              ▼
        Scoring (fit 0-100, opportunity 0-100 → priority A/B/C/EXISTING)
              ▼
        LLM enrichment (concrete examples + summary + outreach email)   ◄─ optional
              ▼
        Reports: per-site JSON + Markdown brief, cross-site leaderboard
```

## Design notes & limits

- **Crawls public pages only**, honors `robots.txt` by default, rate-limits
  requests (`--delay`), and identifies itself with a descriptive User-Agent.
  Use responsibly and within each site's terms.
- **Heuristics are best-effort.** Detection from static HTML can't see everything
  a JS-rendered storefront does (e.g. autosuggest that only mounts on focus), so
  findings carry a **confidence** score and the brief says *verify before
  outreach*. Treat it as a prospecting aid, not a definitive audit.
- **Auto-discovery** uses DuckDuckGo's HTML endpoint (no API key) and filters out
  marketplaces; review the discovered list before scanning.
- **Network:** scanning real sites requires open outbound HTTPS. In restricted
  environments (allowlist-only egress) the live crawl will be blocked — run it
  where the target sites are reachable.

## Tests

```bash
python -m unittest discover -s tests -v
```
