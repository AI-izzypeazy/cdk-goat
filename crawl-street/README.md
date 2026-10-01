# 🛰️ Crawl Street

A **mega-efficient catalogue crawler and search tester**. Point it at an
e-commerce site and it will:

1. **Crawl** the site efficiently and politely, extracting the product
   catalogue (brands, categories, prices, SKUs) from structured data.
2. **Generate search queries that make sense for *that* catalogue** — built
   from the store's own brands, categories and product vocabulary, plus typo
   and nonsense controls.
3. **Run those queries against the site's own search** and grade how well it
   responds, producing a **search-health score**.

Everything is driven from a clean live dashboard, or headless from the CLI.

---

## Why "supercharged"

This is built around the things that actually make a crawler fast *and* able to
stay unblocked on real sites — without resorting to anything abusive:

| Capability | What it does |
|---|---|
| **Connection reuse + HTTP/2** | one shared client, multiplexed requests |
| **Bounded async concurrency** | global *and* per-host limits so you're fast without hammering one host |
| **Realistic, rotating headers** | full, internally-consistent header sets (UA + client-hints + Sec-Fetch), not just a UA string — the single biggest anti-block win |
| **Exponential backoff + `Retry-After`** | rides out 429/503 instead of getting banned |
| **Rotating proxy pool** | optional egress-IP rotation (one client per proxy) |
| **JS render fallback** | optional headless-Chromium pass for JS-only catalogues and soft bot-walls |
| **robots.txt aware** | honoured by default, with an explicit operator override |
| **Structured extraction** | JSON-LD → OpenGraph → microdata → DOM heuristics, merged and de-duplicated |
| **Catalogue-aware query generation** | queries derived from the real catalogue, tagged by *intent* |
| **Transparent grading** | every query gets a verdict (`pass`/`weak`/`fail`) with a human-readable rationale |

### A note on "bypassing bot protection"

Crawl Street implements the hygiene that legitimate, high-throughput crawlers
use to avoid *accidental* blocks: coherent headers, polite pacing, backoff,
optional proxy rotation, and an optional real-browser render. It **respects
`robots.txt` by default** and does **not** solve CAPTCHAs or target specific
WAFs. Only crawl sites you own or are authorised to test.

---

## Install & run

```bash
cd crawl-street
pip install -r requirements.txt     # just httpx; stdlib does the rest

# Launch the dashboard
python run.py
#  → http://127.0.0.1:8787

# …or headless, printing a JSON report
python -m crawlstreet crawl https://store.example.com --max-pages 200 -o report.json
```

Optional JS rendering:

```bash
pip install playwright && playwright install chromium
python -m crawlstreet crawl https://spa-store.example.com --render
```

---

## The dashboard

- **Control panel** — paste a URL and go; *Advanced settings* exposes scope,
  throughput, anti-block hygiene and query-testing knobs, grouped so each
  cluster of controls reads as one idea.
- **Live metric tiles** — pages fetched, products, pages/sec, queue depth,
  blocked/429 count, JS-rendered count, and the **search-health** score.
- **Overview tab** — discovered search endpoint, price distribution, and top
  brands/categories as chips.
- **Catalogue tab** — every extracted product with its source extractor.
- **Query tests tab** — each generated query, its intent, verdict badge, a
  relevance bar, and *why* it was graded that way.
- **Activity tab** — a live event log of the crawl.

---

## CLI reference

```
python -m crawlstreet serve [--host H] [--port P]     # dashboard (default)
python -m crawlstreet crawl URL [options]             # headless, JSON report

  --max-pages N     page ceiling (default 150)
  --max-depth N     link depth (default 4)
  --concurrency N   in-flight requests (default 8)
  --max-queries N   search queries to run (default 25)
  --no-robots       ignore robots.txt (you own the consequences)
  --no-queries      crawl only, skip the search test
  --render          enable the JS render fallback (needs playwright)
  -o FILE           write the JSON report to FILE
```

---

## Architecture

```
crawlstreet/
  config.py      CrawlConfig — all tunables, clamped to safe ranges
  useragents.py  coherent rotating header sets
  fetcher.py     async fetch: HTTP/2, retries, backoff, rate-limit, proxy pool
  robots.py      robots.txt fetch + cache
  render.py      optional Playwright render fallback (soft dependency)
  extract.py     JSON-LD / OpenGraph / microdata / heuristic product extraction
  catalogue.py   aggregate products → brands, categories, price stats, keywords
  queries.py     catalogue-aware query generation, tagged by intent
  search.py      endpoint discovery + query execution + transparent grading
  crawler.py     the orchestrator: frontier, concurrency, live state
  server.py      stdlib HTTP server: JSON API + dashboard
  ui/            the dashboard (index.html + styles.css + app.js)
```

The fetcher and crawler accept an injected `httpx` transport, so the whole
pipeline is testable end-to-end with no network (see `tests/test_pipeline.py`).

---

## Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

The suite drives a full crawl → extract → catalogue → query-grade flow through
an in-process mock shop.
