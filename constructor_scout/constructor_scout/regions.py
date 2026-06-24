"""Turn a country/region into ecommerce-prospect discovery queries.

Phase 1 of the regional workflow: given a country, build a spread of search
queries across common retail verticals so discovery surfaces a broad set of
real online stores operating in that market.
"""

from __future__ import annotations

# Retail/ecommerce verticals we sweep per region.
DEFAULT_VERTICALS: tuple[str, ...] = (
    "fashion and clothing",
    "shoes and footwear",
    "beauty and cosmetics",
    "consumer electronics",
    "home and furniture",
    "jewelry and watches",
    "sporting goods and outdoor",
    "toys and baby",
    "grocery and food",
    "pet supplies",
)

# Common country-code TLDs, used to bias/score local sites.
COUNTRY_TLDS: dict[str, str] = {
    "united kingdom": "co.uk", "uk": "co.uk", "england": "co.uk",
    "germany": "de", "deutschland": "de",
    "france": "fr", "spain": "es", "italy": "it", "netherlands": "nl",
    "australia": "com.au", "canada": "ca", "ireland": "ie", "india": "in",
    "japan": "jp", "brazil": "com.br", "mexico": "com.mx", "sweden": "se",
    "norway": "no", "denmark": "dk", "poland": "pl", "switzerland": "ch",
    "austria": "at", "belgium": "be", "portugal": "pt", "new zealand": "co.nz",
    "united states": "com", "usa": "com", "us": "com",
}


def region_tld(country: str) -> str | None:
    return COUNTRY_TLDS.get(country.strip().lower())


def region_queries(country: str, verticals: list[str] | None = None) -> list[str]:
    """Build discovery queries for a country across retail verticals."""
    country = country.strip()
    verts = verticals if verticals else list(DEFAULT_VERTICALS)
    queries: list[str] = [
        f"top online retailers in {country}",
        f"best ecommerce stores {country}",
        f"popular online shops {country}",
    ]
    for v in verts:
        queries.append(f"best online {v} stores in {country}")
    return queries
