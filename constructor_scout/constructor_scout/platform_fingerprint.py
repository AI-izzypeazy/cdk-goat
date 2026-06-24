"""Detect the ecommerce platform and incumbent search/discovery vendor."""

from __future__ import annotations

from .knowledge import INCUMBENT_VENDORS, PLATFORMS
from .models import PageSnapshot, SiteProfile


ECOMMERCE_SIGNALS = (
    "add to cart", "add to bag", "addtocart", "/cart", "checkout", "product",
    "price", "in stock", "sku", "sold out", "shop now", "buy now", "wishlist",
    'itemprop="price"', "og:type\" content=\"product", "schema.org/product",
)


def fingerprint(pages: list[PageSnapshot], profile: SiteProfile) -> SiteProfile:
    blob = " ".join(p.text_lower() for p in pages if p.ok)

    # Platform
    for plat in PLATFORMS:
        if any(sig in blob for sig in plat.signatures):
            profile.platform = plat.id
            profile.platform_name = plat.name
            break

    # Incumbent discovery vendor (first match wins; constructor checked first).
    for vendor in INCUMBENT_VENDORS:
        if any(sig in blob for sig in vendor.signatures):
            profile.incumbent_vendor = vendor.id
            profile.incumbent_vendor_name = vendor.name
            profile.is_existing_constructor = vendor.is_constructor
            break

    # Ecommerce-ness
    signals = sorted({s for s in ECOMMERCE_SIGNALS if s in blob})
    profile.catalog_signals = signals
    profile.looks_ecommerce = len(signals) >= 2 or profile.platform != "unknown"

    return profile
