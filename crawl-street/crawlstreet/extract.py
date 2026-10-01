"""HTML extraction: links, text, search forms, and products.

Product detection, in priority order:
  1. JSON-LD  (<script type="application/ld+json"> Product / Offer)  -- most reliable
  2. OpenGraph product meta tags (og:type=product, product:price:amount ...)
  3. Microdata (itemtype schema.org/Product)
  4. DOM heuristics (price-shaped text near a product-ish container)

Built on stdlib html.parser so there are no native parser dependencies.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlsplit, urlunsplit

_PRICE_RE = re.compile(
    r"(?:(?P<cur>[$£€¥])\s?)?(?P<num>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)(?:\s?(?P<cur2>USD|EUR|GBP|CAD|AUD))?",
)
_WS_RE = re.compile(r"\s+")


@dataclass
class Product:
    name: str
    url: str = ""
    price: Optional[float] = None
    currency: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    sku: Optional[str] = None
    availability: Optional[str] = None
    image: Optional[str] = None
    source: str = "heuristic"   # which extractor found it

    def key(self) -> str:
        return (self.sku or self.url or self.name or "").strip().lower()

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class SearchForm:
    action: str
    param: str
    method: str = "get"


@dataclass
class PageData:
    url: str
    title: str = ""
    text_len: int = 0
    links: List[str] = field(default_factory=list)
    products: List[Product] = field(default_factory=list)
    search_forms: List[SearchForm] = field(default_factory=list)
    is_product_page: bool = False


class _Collector(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base = base_url
        self.links: List[str] = []
        self.title = ""
        self.text_chunks: List[str] = []
        self.jsonld_blobs: List[str] = []
        self.meta: Dict[str, str] = {}
        self.search_forms: List[SearchForm] = []
        self.microdata_products: List[Product] = []

        self._in_title = False
        self._in_script = False
        self._script_type = ""
        self._script_buf: List[str] = []
        self._in_style = False
        # form tracking
        self._form_stack: List[dict] = []
        # microdata tracking
        self._md_stack: List[Optional[Product]] = []
        self._md_prop_target: Optional[tuple] = None  # (product, attr)

    # -- tags --------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            href = _clean_url(urljoin(self.base, a["href"]))
            if href:
                self.links.append(href)
        elif tag == "link" and a.get("href") and "canonical" in (a.get("rel") or ""):
            pass
        elif tag == "title":
            self._in_title = True
        elif tag == "script":
            self._in_script = True
            self._script_type = (a.get("type") or "").lower()
            self._script_buf = []
        elif tag == "style":
            self._in_style = True
        elif tag == "meta":
            prop = a.get("property") or a.get("name")
            if prop and a.get("content"):
                self.meta[prop.lower()] = a["content"]
        elif tag == "form":
            form = {"action": _clean_url(urljoin(self.base, a.get("action", self.base))),
                    "method": (a.get("method") or "get").lower(),
                    "role": (a.get("role") or ""),
                    "inputs": []}
            self._form_stack.append(form)
        elif tag == "input":
            if self._form_stack:
                self._form_stack[-1]["inputs"].append({
                    "name": a.get("name", ""),
                    "type": (a.get("type") or "text").lower(),
                    "placeholder": (a.get("placeholder") or "").lower(),
                    "aria": (a.get("aria-label") or "").lower(),
                })
        # microdata
        if a.get("itemscope") is not None and _is_product_type(a.get("itemtype", "")):
            self._md_stack.append(Product(name="", source="microdata"))
        elif self._md_stack and self._md_stack[-1] is not None and a.get("itemprop"):
            self._apply_microprop(a)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script":
            if self._script_type in ("application/ld+json", "application/json+ld"):
                self.jsonld_blobs.append("".join(self._script_buf))
            self._in_script = False
            self._script_type = ""
        elif tag == "style":
            self._in_style = False
        elif tag == "form":
            if self._form_stack:
                self._finalize_form(self._form_stack.pop())

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._in_script:
            self._script_buf.append(data)
        elif self._in_style:
            pass
        else:
            s = data.strip()
            if s:
                self.text_chunks.append(s)

    # -- helpers -----------------------------------------------------------
    def _apply_microprop(self, a: dict) -> None:
        prod = self._md_stack[-1]
        prop = a.get("itemprop", "").lower()
        content = a.get("content")
        if prop == "name" and content:
            prod.name = content
        elif prop == "brand" and content:
            prod.brand = content
        elif prop == "sku" and content:
            prod.sku = content
        elif prop == "price" and content:
            prod.price = _to_float(content)
        elif prop == "pricecurrency" and content:
            prod.currency = content
        elif prop == "image" and content:
            prod.image = _clean_url(urljoin(self.base, content))

    def _finalize_form(self, form: dict) -> None:
        for inp in form["inputs"]:
            looks_search = (
                inp["type"] == "search"
                or inp["name"] in ("q", "query", "search", "keyword", "keywords", "s", "term")
                or "search" in inp["placeholder"] or "search" in inp["aria"]
                or "search" in form["role"]
            )
            if looks_search and inp["name"]:
                self.search_forms.append(
                    SearchForm(action=form["action"], param=inp["name"], method=form["method"])
                )
                return


def _is_product_type(itemtype: str) -> bool:
    return "schema.org/product" in (itemtype or "").lower()


def parse_page(url: str, html: str) -> PageData:
    c = _Collector(url)
    try:
        c.feed(html)
    except Exception:
        pass

    products: List[Product] = []
    products.extend(_from_jsonld(c.jsonld_blobs, url))
    products.extend(p for p in c._md_stack if p and p.name)
    og = _from_opengraph(c.meta, url, c.title)
    if og:
        products.append(og)

    # Dedupe by key, keeping the richest (most-filled) record.
    merged: Dict[str, Product] = {}
    for p in products:
        if not p.name:
            continue
        k = p.key()
        if k not in merged or _richness(p) > _richness(merged[k]):
            merged[k] = p

    text = _WS_RE.sub(" ", " ".join(c.text_chunks))
    is_product = bool(merged) or _page_looks_like_product(c.meta, c.title)

    return PageData(
        url=url,
        title=_WS_RE.sub(" ", c.title).strip(),
        text_len=len(text),
        links=_dedupe(c.links),
        products=list(merged.values()),
        search_forms=_dedupe_forms(c.search_forms),
        is_product_page=is_product,
    )


# ---------------------------------------------------------------------------
def _from_jsonld(blobs: List[str], base: str) -> List[Product]:
    out: List[Product] = []
    for blob in blobs:
        blob = blob.strip()
        if not blob:
            continue
        try:
            data = json.loads(blob)
        except Exception:
            continue
        for node in _walk_jsonld(data):
            if not isinstance(node, dict):
                continue
            t = node.get("@type", "")
            types = t if isinstance(t, list) else [t]
            if any(str(x).lower() == "product" for x in types):
                out.append(_product_from_jsonld(node, base))
    return out


def _walk_jsonld(data):
    stack = [data]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            yield cur
            if "@graph" in cur and isinstance(cur["@graph"], list):
                stack.extend(cur["@graph"])
            for v in cur.values():
                if isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)


def _product_from_jsonld(node: dict, base: str) -> Product:
    offers = node.get("offers")
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    offers = offers or {}
    brand = node.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    cat = node.get("category")
    image = node.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url")
    return Product(
        name=str(node.get("name", "")).strip(),
        url=_clean_url(urljoin(base, node.get("url", base))),
        price=_to_float(offers.get("price") if isinstance(offers, dict) else None),
        currency=(offers.get("priceCurrency") if isinstance(offers, dict) else None),
        brand=str(brand) if brand else None,
        category=str(cat) if cat else None,
        sku=str(node.get("sku")) if node.get("sku") else None,
        availability=_avail(offers.get("availability") if isinstance(offers, dict) else None),
        image=_clean_url(urljoin(base, image)) if image else None,
        source="json-ld",
    )


def _from_opengraph(meta: Dict[str, str], base: str, title: str) -> Optional[Product]:
    if meta.get("og:type", "").lower() not in ("product", "product.item", "og:product"):
        if "product:price:amount" not in meta:
            return None
    name = meta.get("og:title") or title
    if not name:
        return None
    return Product(
        name=name.strip(),
        url=_clean_url(meta.get("og:url", base)),
        price=_to_float(meta.get("product:price:amount")),
        currency=meta.get("product:price:currency"),
        brand=meta.get("product:brand") or meta.get("og:brand"),
        image=_clean_url(urljoin(base, meta["og:image"])) if meta.get("og:image") else None,
        availability=meta.get("product:availability"),
        source="opengraph",
    )


def _page_looks_like_product(meta: Dict[str, str], title: str) -> bool:
    return meta.get("og:type", "").lower().startswith("product")


# --- small utils -----------------------------------------------------------
def _richness(p: Product) -> int:
    return sum(1 for v in (p.price, p.brand, p.category, p.sku, p.image, p.url) if v)


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"\d[\d.,]*", str(v))
    if not m:
        return None
    raw = m.group(0)
    # Normalise 1.234,56 -> 1234.56 and 1,234.56 -> 1234.56
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".") if len(raw.split(",")[-1]) == 2 else raw.replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _avail(v) -> Optional[str]:
    if not v:
        return None
    return str(v).rsplit("/", 1)[-1]


def _clean_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if url.startswith(("javascript:", "mailto:", "tel:", "#", "data:")):
        return ""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https", ""):
        return ""
    # drop fragment
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def _dedupe(items: List[str]) -> List[str]:
    seen: Set[str] = set()
    out = []
    for it in items:
        if it and it not in seen:
            seen.add(it)
            out.append(it)
    return out


def _dedupe_forms(forms: List[SearchForm]) -> List[SearchForm]:
    seen: Set[str] = set()
    out = []
    for f in forms:
        k = f"{f.action}|{f.param}"
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out
