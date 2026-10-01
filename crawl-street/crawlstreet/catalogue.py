"""Aggregate extracted products into a structured catalogue + signals that the
query generator uses to build *sensible* test queries.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from statistics import median
from typing import List, Optional

from .extract import Product

_STOPWORDS = {
    "the", "and", "for", "with", "a", "an", "of", "to", "in", "on", "by",
    "new", "sale", "set", "pack", "size", "color", "colour", "pcs", "pc",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)


@dataclass
class Catalogue:
    products: List[Product] = field(default_factory=list)
    brands: Counter = field(default_factory=Counter)
    categories: Counter = field(default_factory=Counter)
    keywords: Counter = field(default_factory=Counter)
    currencies: Counter = field(default_factory=Counter)

    def add(self, product: Product) -> None:
        self.products.append(product)
        if product.brand:
            self.brands[product.brand.strip()] += 1
        if product.category:
            self.categories[product.category.strip()] += 1
        if product.currency:
            self.currencies[product.currency.strip()] += 1
        for tok in _tokens(product.name):
            self.keywords[tok] += 1

    # --- derived signals --------------------------------------------------
    def prices(self) -> List[float]:
        return [p.price for p in self.products if isinstance(p.price, (int, float))]

    def price_stats(self) -> Optional[dict]:
        pr = self.prices()
        if not pr:
            return None
        return {
            "count": len(pr),
            "min": round(min(pr), 2),
            "max": round(max(pr), 2),
            "median": round(median(pr), 2),
            "avg": round(sum(pr) / len(pr), 2),
        }

    def top_brands(self, n: int = 10) -> List[str]:
        return [b for b, _ in self.brands.most_common(n)]

    def top_categories(self, n: int = 10) -> List[str]:
        return [c for c, _ in self.categories.most_common(n)]

    def top_keywords(self, n: int = 20) -> List[str]:
        return [k for k, _ in self.keywords.most_common(n)]

    def summary(self) -> dict:
        return {
            "total_products": len(self.products),
            "unique_brands": len(self.brands),
            "unique_categories": len(self.categories),
            "price_stats": self.price_stats(),
            "top_brands": self.top_brands(),
            "top_categories": self.top_categories(),
            "top_keywords": self.top_keywords(),
            "currencies": [c for c, _ in self.currencies.most_common()],
        }

    def sample(self, n: int = 50) -> List[dict]:
        return [p.to_dict() for p in self.products[:n]]


def _tokens(text: str) -> List[str]:
    out = []
    for t in _TOKEN_RE.findall(text or ""):
        tl = t.lower()
        if len(tl) >= 3 and tl not in _STOPWORDS and not tl.isdigit():
            out.append(tl)
    return out
