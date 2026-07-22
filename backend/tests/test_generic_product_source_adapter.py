"""
Tests for GenericUrlAdapter (Phase 5.3 of Product Intelligence, see
MIGRATION_PLAN.md). No real network calls - httpx.MockTransport feeds
fixture HTML/responses, matching the "no real network calls in the test
suite" discipline the plan called for.
"""

import httpx
import pytest

from app.product_sources.base import ColorValue, ListValue, TextValue
from app.product_sources.generic import MAX_RESPONSE_BYTES, GenericUrlAdapter

JSONLD_PRODUCT_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "Product",
  "name": "Sunrise Orange Juice",
  "brand": {"@type": "Brand", "name": "Bellavita"},
  "color": "Amber",
  "material": "Glass, Aluminium",
  "image": ["/images/bottle-front.jpg", {"url": "https://cdn.example.com/bottle-side.jpg"}]
}
</script>
</head><body></body></html>
"""

JSONLD_GRAPH_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@graph": [
    {"@type": "Organization", "name": "Bellavita Inc"},
    {"@type": "Product", "name": "Evoband Wristband", "brand": "Evoband"}
  ]
}
</script>
</head><body></body></html>
"""

JSONLD_MULTI_PRODUCT_GRAPH_HTML = """
<html><head>
<title>Bella Vita Luxury Gift Set</title>
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@graph": [
    {"@type": "Organization", "name": "Bella Vita Luxury"},
    {"@type": "Product", "name": "G.O.A.T. Man", "brand": "Bella Vita Luxury", "color": "Amber"},
    {"@type": "Product", "name": "CEO Man", "brand": "Bella Vita Luxury", "color": "Black"}
  ]
}
</script>
</head><body></body></html>
"""

OPENGRAPH_ONLY_HTML = """
<html><head>
<title>Fallback Page Title</title>
<meta property="og:title" content="OG Product Title" />
<meta property="og:image" content="/og-image.jpg" />
<meta property="og:description" content="A great product." />
</head><body></body></html>
"""

NO_MARKUP_HTML = """
<html><head><title>Just A Plain Page</title></head><body></body></html>
"""


def _adapter_with_response(html: str, status_code: int = 200, content_type: str = "text/html") -> GenericUrlAdapter:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, content=html.encode(), headers={"content-type": content_type})

    return GenericUrlAdapter(transport=httpx.MockTransport(handler))


def test_matches_is_always_true():
    adapter = GenericUrlAdapter()
    assert adapter.matches("https://anything.example/whatever") is True


def test_extracts_from_schema_org_jsonld():
    adapter = _adapter_with_response(JSONLD_PRODUCT_HTML)
    result = adapter.extract("https://shop.example/products/sunrise-oj")

    assert result.raw["name"] == "Sunrise Orange Juice"
    assert result.normalized.title == "Sunrise Orange Juice"
    assert result.normalized.brand == "Bellavita"
    assert result.normalized.attributes["brand"].value == TextValue(text="Bellavita")
    assert result.normalized.attributes["color"].value == ColorValue(label="Amber")
    assert result.normalized.attributes["materials"].value == ListValue(items=["Glass", "Aluminium"])
    # Relative image URL resolved against the page URL; absolute one left as-is.
    image_urls = {img.url for img in result.normalized.images}
    assert image_urls == {
        "https://shop.example/images/bottle-front.jpg",
        "https://cdn.example.com/bottle-side.jpg",
    }


def test_extracts_product_from_at_graph_bundle():
    adapter = _adapter_with_response(JSONLD_GRAPH_HTML)
    result = adapter.extract("https://shop.example/products/evoband")

    assert result.normalized.title == "Evoband Wristband"
    assert result.normalized.brand == "Evoband"


def test_single_product_at_graph_still_has_no_bundle_evidence():
    """Regression guard: the existing single-product @graph case is unaffected by Phase 5.9."""
    adapter = _adapter_with_response(JSONLD_GRAPH_HTML)
    result = adapter.extract("https://shop.example/products/evoband")
    assert result.normalized.bundle is None
    assert result.normalized.listing is None


def test_detects_bundle_from_multi_product_at_graph():
    """
    Phase 5.9's bundle-detection heuristic (see MIGRATION_PLAN.md's frozen
    catalogue ADR): a @graph with more than one Product entry is treated
    as a bundle listing.
    """
    adapter = _adapter_with_response(JSONLD_MULTI_PRODUCT_GRAPH_HTML)
    result = adapter.extract("https://shop.example/products/bella-vita-set")

    assert result.normalized.bundle is not None
    assert result.normalized.bundle.title == "Bella Vita Luxury Gift Set"
    assert [hint.label for hint in result.normalized.bundle.member_hints] == ["G.O.A.T. Man", "CEO Man"]
    assert result.normalized.bundle.member_hints[0].attributes["color"].value == ColorValue(label="Amber")
    assert result.normalized.bundle.member_hints[1].attributes["color"].value == ColorValue(label="Black")


def test_bundle_evidence_does_not_promote_one_members_facts_to_the_top_level():
    """
    The real point of this design (see generic.py's own docstring): a
    bundle's top-level title/brand/attributes/images must never look like
    facts about "the product" when there are really N of them - only
    bundle.member_hints carries per-member data.
    """
    adapter = _adapter_with_response(JSONLD_MULTI_PRODUCT_GRAPH_HTML)
    result = adapter.extract("https://shop.example/products/bella-vita-set")

    assert result.normalized.brand is None
    assert result.normalized.attributes == {}
    assert result.normalized.images == []
    assert result.raw == {
        "bundle_members": [
            {"@type": "Product", "name": "G.O.A.T. Man", "brand": "Bella Vita Luxury", "color": "Amber"},
            {"@type": "Product", "name": "CEO Man", "brand": "Bella Vita Luxury", "color": "Black"},
        ]
    }


def test_falls_back_to_opengraph_when_no_jsonld_product():
    adapter = _adapter_with_response(OPENGRAPH_ONLY_HTML)
    result = adapter.extract("https://shop.example/products/no-jsonld")

    assert result.normalized.title == "OG Product Title"
    assert result.normalized.images[0].url == "https://shop.example/og-image.jpg"
    assert result.raw["og:description"] == "A great product."
    # No structured attributes extractable from OpenGraph alone.
    assert result.normalized.attributes == {}


def test_falls_back_to_page_title_when_no_og_tags_either():
    adapter = _adapter_with_response(NO_MARKUP_HTML)
    result = adapter.extract("https://shop.example/products/bare")

    assert result.normalized.title == "Just A Plain Page"
    assert result.normalized.images == []


def test_raises_on_unreachable_url():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    adapter = GenericUrlAdapter(transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.ConnectError):
        adapter.extract("https://unreachable.example.invalid/")


def test_raises_on_http_error_status():
    adapter = _adapter_with_response("<html></html>", status_code=404)
    with pytest.raises(httpx.HTTPStatusError):
        adapter.extract("https://shop.example/products/missing")


def test_raises_when_response_exceeds_size_limit():
    oversized_html = "<html><body>" + ("x" * (MAX_RESPONSE_BYTES + 1)) + "</body></html>"
    adapter = _adapter_with_response(oversized_html)
    with pytest.raises(ValueError, match="exceeded"):
        adapter.extract("https://shop.example/products/huge-page")


def test_ignores_malformed_jsonld_and_falls_back():
    malformed_html = """
    <html><head>
    <script type="application/ld+json">{ not valid json </script>
    <meta property="og:title" content="Still Works" />
    </head></html>
    """
    adapter = _adapter_with_response(malformed_html)
    result = adapter.extract("https://shop.example/products/broken-jsonld")
    assert result.normalized.title == "Still Works"
