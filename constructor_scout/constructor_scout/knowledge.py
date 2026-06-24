"""Knowledge base: Constructor.io capabilities and how site gaps map to them.

Every detector finding references a capability id from CAPABILITIES so the
report can explain, in concrete product terms, what Constructor would fix.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Capability:
    id: str
    name: str
    pitch: str  # one-liner used in briefs / outreach
    docs: str


# Constructor.io product surface area, kept deliberately small and concrete.
CAPABILITIES: dict[str, Capability] = {
    "autosuggest": Capability(
        "autosuggest",
        "Autosuggest / Autocomplete",
        "Typeahead with product previews, trending terms and zero-latency "
        "suggestions that convert searchers before they finish typing.",
        "https://constructor.com/products/autosuggest",
    ),
    "search": Capability(
        "search",
        "Search Relevance",
        "AI-ranked results optimized for revenue per visit, not just text "
        "match, with learn-to-rank tuned on real behavior.",
        "https://constructor.com/products/search",
    ),
    "typo_tolerance": Capability(
        "typo_tolerance",
        "Typo Tolerance & Synonyms",
        "Misspellings, plurals and synonyms resolve to the right products "
        "instead of dead-ending shoppers on a zero-results page.",
        "https://constructor.com/products/search",
    ),
    "nl_search": Capability(
        "nl_search",
        "Natural-Language & Semantic Search",
        "Understands intent in queries like 'waterproof jacket under $100' "
        "and returns the right products, not keyword noise.",
        "https://constructor.com/products/search",
    ),
    "browse": Capability(
        "browse",
        "Browse & Merchandising",
        "Category and landing pages ranked and merchandised by the same AI "
        "as search, with drag-and-drop rules for merchandisers.",
        "https://constructor.com/products/browse",
    ),
    "facets": Capability(
        "facets",
        "Facets & Attribute Enrichment",
        "Rich, auto-enriched filters (color, fit, material, price) that help "
        "shoppers narrow large catalogs fast.",
        "https://constructor.com/products/browse",
    ),
    "recommendations": Capability(
        "recommendations",
        "Recommendations",
        "PDP, cart and homepage recommendation pods ('complete the look', "
        "'customers also bought') that lift AOV and units per order.",
        "https://constructor.com/products/recommendations",
    ),
    "personalization": Capability(
        "personalization",
        "Personalization",
        "Per-shopper reranking of search, browse and recs based on real-time "
        "behavior, so every visit is tailored.",
        "https://constructor.com/products/personalization",
    ),
    "collections": Capability(
        "collections",
        "Collections & Quizzes",
        "Curated, shoppable landing experiences and quizzes that capture "
        "intent and guide discovery.",
        "https://constructor.com/products/collections",
    ),
    "zero_results": Capability(
        "zero_results",
        "Zero-Results Recovery & Redirects",
        "No query dead-ends: query rewriting, recommended fallbacks and "
        "managed redirects keep shoppers moving toward a purchase.",
        "https://constructor.com/products/search",
    ),
}


@dataclass(frozen=True)
class IncumbentVendor:
    """A discovery vendor we can fingerprint, and how to position against it."""

    id: str
    name: str
    is_constructor: bool = False
    # Signature substrings to look for in page HTML / script URLs (lowercased).
    signatures: tuple[str, ...] = field(default_factory=tuple)
    # Short competitive angle used in the brief when this incumbent is found.
    angle: str = ""


INCUMBENT_VENDORS: tuple[IncumbentVendor, ...] = (
    IncumbentVendor(
        "constructor", "Constructor.io", is_constructor=True,
        signatures=("cnstrc.com", "constructorio", "constructor-io", "cio_bt", "ac.cnstrc"),
        angle="Already a Constructor customer — route to CS/expansion, not new-logo.",
    ),
    IncumbentVendor(
        "algolia", "Algolia",
        signatures=("algolia", "algolianet.com", "algoliasearch", "instantsearch"),
        angle="Algolia charges per-operation and tunes on text relevance; lead "
        "with revenue-optimized ranking and predictable commerce pricing.",
    ),
    IncumbentVendor(
        "searchspring", "Searchspring",
        signatures=("searchspring", "searchspring.net"),
        angle="Lead with AI ranking, NL search and unified browse/recs depth.",
    ),
    IncumbentVendor(
        "bloomreach", "Bloomreach",
        signatures=("bloomreach", "brapi", "bloomreach.com"),
        angle="Lead with faster time-to-value and merchandiser-friendly tooling.",
    ),
    IncumbentVendor(
        "klevu", "Klevu",
        signatures=("klevu", "js.klevu.com"),
        angle="Lead with scale, personalization depth and revenue optimization.",
    ),
    IncumbentVendor(
        "coveo", "Coveo",
        signatures=("coveo", "coveo.com", "coveoua"),
        angle="Lead with commerce-native UX and speed of deployment.",
    ),
    IncumbentVendor(
        "nosto", "Nosto",
        signatures=("nosto", "nosto.com", "connect.nosto.com"),
        angle="Nosto is recs-centric; lead with unified search + browse + recs.",
    ),
    IncumbentVendor(
        "yotpo", "Yotpo",
        signatures=("yotpo", "staticw2.yotpo.com"),
        angle="Reviews-led vendor; discovery search/browse is greenfield.",
    ),
    IncumbentVendor(
        "salesforce_einstein", "Salesforce Commerce / Einstein",
        signatures=("demandware.edgesuite", "einstein.commercecloud", "cquotient"),
        angle="Einstein search is often underused; lead with relevance lift and "
        "merchandiser control.",
    ),
)


@dataclass(frozen=True)
class Platform:
    id: str
    name: str
    signatures: tuple[str, ...]


PLATFORMS: tuple[Platform, ...] = (
    Platform("shopify", "Shopify", ("cdn.shopify.com", "shopify.theme", "x-shopify", "myshopify.com")),
    Platform("magento", "Magento / Adobe Commerce", ("magento", "mage/", "/static/version", "mage-init")),
    Platform("salesforce", "Salesforce Commerce Cloud", ("demandware", "dwstatic", "/on/demandware")),
    Platform("bigcommerce", "BigCommerce", ("bigcommerce.com", "stencil-utils", "cdn11.bigcommerce")),
    Platform("woocommerce", "WooCommerce", ("woocommerce", "wp-content/plugins/woocommerce", "wc-")),
    Platform("commercetools", "commercetools", ("commercetools", "ctp_")),
    Platform("prestashop", "PrestaShop", ("prestashop", "/prestashop/")),
)
