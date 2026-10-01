"""Generate search queries that *make sense for the crawled catalogue*.

The whole point: random queries ("foo", "test") tell you nothing about a
store's search. Queries built from the store's own brands, categories and
product vocabulary actually exercise it. We generate a spread of query
*intents* and tag each so the report can show coverage by type.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .catalogue import Catalogue


@dataclass
class GeneratedQuery:
    text: str
    intent: str          # exact_product | brand | category | brand_category |
                         # keyword | multiword | typo | nonsense
    expect_results: bool # whether a healthy search *should* return hits
    rationale: str


def generate_queries(cat: Catalogue, limit: int = 25) -> List[GeneratedQuery]:
    out: List[GeneratedQuery] = []
    seen = set()

    def add(text: str, intent: str, expect: bool, why: str) -> None:
        text = (text or "").strip()
        key = text.lower()
        if text and key not in seen and len(text) <= 80:
            seen.add(key)
            out.append(GeneratedQuery(text, intent, expect, why))

    brands = cat.top_brands(8)
    cats = cat.top_categories(8)
    keywords = cat.top_keywords(15)
    names = [p.name for p in cat.products if p.name][:12]

    # 1. Exact product names — the strongest "does search work at all" signal.
    for name in names:
        words = name.split()
        add(" ".join(words[:5]), "exact_product", True,
            "exact product title should return the product itself")

    # 2. Single brand queries.
    for b in brands:
        add(b, "brand", True, f"'{b}' is a brand in the catalogue")

    # 3. Single category queries.
    for c in cats:
        add(c, "category", True, f"'{c}' is a product category in the catalogue")

    # 4. Brand + category combos (realistic shopper intent).
    for b in brands[:4]:
        for c in cats[:3]:
            add(f"{b} {c}", "brand_category", True,
                f"shoppers combine brand and category: {b} + {c}")

    # 5. Salient keywords from product titles.
    for k in keywords:
        add(k, "keyword", True, f"'{k}' is a frequent term in product titles")

    # 6. Multi-word phrase from the most common keywords (tests tokenisation).
    if len(keywords) >= 2:
        add(f"{keywords[0]} {keywords[1]}", "multiword", True,
            "two common terms together — tests multi-token matching")

    # 7. A deliberate typo of a popular term (tests fuzzy/typo tolerance).
    if keywords:
        add(_typo(keywords[0]), "typo", True,
            f"misspelling of '{keywords[0]}' — tests typo tolerance")
    if brands:
        add(_typo(brands[0]), "typo", True,
            f"misspelling of brand '{brands[0]}' — tests typo tolerance")

    # 8. A guaranteed-nonsense control (healthy search returns *zero* here).
    add("qwzxv- no such product 9931", "nonsense", False,
        "control query — a correct search engine returns no results")

    # Interleave intents so an early cutoff still covers variety.
    ordered = _interleave(out)
    return ordered[:limit]


def _interleave(queries: List[GeneratedQuery]) -> List[GeneratedQuery]:
    buckets: dict = {}
    for q in queries:
        buckets.setdefault(q.intent, []).append(q)
    order = ["exact_product", "brand", "category", "keyword", "brand_category",
             "multiword", "typo", "nonsense"]
    result: List[GeneratedQuery] = []
    while any(buckets.get(k) for k in buckets):
        for intent in order:
            if buckets.get(intent):
                result.append(buckets[intent].pop(0))
    return result


def _typo(word: str) -> str:
    if len(word) < 4:
        return word + "s"
    i = len(word) // 2
    chars = list(word)
    chars[i], chars[i + 1] = chars[i + 1], chars[i]  # transpose two letters
    return "".join(chars)
