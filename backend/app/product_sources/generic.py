"""
GenericUrlAdapter - the platform-agnostic fallback Product Source (Phase
5.3 of Product Intelligence, see MIGRATION_PLAN.md). schema.org JSON-LD
first, OpenGraph/basic page metadata if no JSON-LD Product block is
found. Always matches() True - the catch-all, must stay last in
app.product_sources.registry.PRODUCT_SOURCE_ADAPTERS.

Vocabulary discipline applies here too (see base.py, revision #5):
schema.org's own standard Product properties map onto the existing
vocabulary field-for-field in the common case (name, brand, color,
material). Anything a page's JSON-LD/OpenGraph exposes that doesn't map
stays out of `attributes` entirely - it's still preserved in `raw`
(ProductSourceExtraction.raw, stored as ProductSourceImport.
raw_response_json), just not promoted to a canonical field on this
adapter's say-so alone.

Bundle detection (Phase 5.9 of the catalogue layer, see
MIGRATION_PLAN.md's frozen catalogue ADR): a first, deliberately narrow
heuristic - a JSON-LD @graph containing more than one Product entry (this
adapter already expands @graph bundles, see _find_all_product_jsonld
below) is treated as a bundle listing. evidence.bundle is populated with
one BundleMemberHint per detected Product, uniformly - the top-level
title/brand/attributes/images are deliberately NOT filled from any one
member in this case (that would misleadingly describe one item as if it
were a fact about the whole listing). A listing with no such signal
simply has bundle=None, exactly as before this sub-phase existed - not
exhaustive, degraded (missed signal) rather than broken for bundle-shaped
listings that don't use this particular pattern.
"""

import json
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.product_sources.base import (
    BundleMemberHint,
    ColorValue,
    ListValue,
    NormalizedAttribute,
    NormalizedBundleEvidence,
    NormalizedProductEvidence,
    NormalizedProductImage,
    ProductSourceExtraction,
    TextValue,
)

FETCH_TIMEOUT_SECONDS = 10.0
# A product page's HTML has no business being bigger than this - fetching
# arbitrary user-supplied URLs is real abuse-surface even in a local
# single-user app, worth bounding regardless.
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (compatible; CreativeAssetEngine/1.0; +product-intelligence)"


class GenericUrlAdapter:
    def __init__(self, transport: httpx.BaseTransport | None = None):
        # Injectable transport so tests never hit real network (see
        # tests/test_generic_product_source_adapter.py) - None uses
        # httpx's real default transport.
        self._transport = transport

    def matches(self, url: str) -> bool:
        return True

    def extract(self, url: str) -> ProductSourceExtraction:
        html = self._fetch_bounded(url)
        soup = BeautifulSoup(html, "html.parser")

        products_jsonld = _find_all_product_jsonld(soup)
        if len(products_jsonld) > 1:
            # Bundle-shaped: deliberately do NOT promote any one member's
            # brand/attributes/images to the top level - that would
            # misleadingly describe just one item as if it were a fact
            # about the whole listing (same reasoning the catalogue ADR
            # uses for why Product's vocabulary can't honestly describe a
            # bundle). Every member is represented uniformly, only inside
            # bundle.member_hints.
            bundle_evidence = _bundle_evidence_from_jsonld(soup, products_jsonld)
            normalized = NormalizedProductEvidence(
                source_type="generic_url",
                source_url=url,
                title=bundle_evidence.title,
                bundle=bundle_evidence,
            )
            return ProductSourceExtraction(raw={"bundle_members": products_jsonld}, normalized=normalized)
        if products_jsonld:
            return ProductSourceExtraction(
                raw=products_jsonld[0], normalized=_normalize_jsonld(url, products_jsonld[0])
            )

        raw, normalized = _normalize_opengraph(url, soup)
        return ProductSourceExtraction(raw=raw, normalized=normalized)

    def _fetch_bounded(self, url: str) -> str:
        with httpx.Client(
            transport=self._transport, timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True
        ) as client:
            with client.stream("GET", url, headers={"User-Agent": USER_AGENT}) as response:
                response.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > MAX_RESPONSE_BYTES:
                        raise ValueError(f"Response from {url} exceeded {MAX_RESPONSE_BYTES} bytes")
                    chunks.append(chunk)
                return b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")


def _find_all_product_jsonld(soup: BeautifulSoup) -> list[dict]:
    """
    Every JSON-LD entity typed Product across the page's <script
    type="application/ld+json"> blocks, expanding @graph bundles (a
    common JSON-LD pattern grouping multiple entities - Product,
    Organization, BreadcrumbList, ... - in one script block). More than
    one entry here is this adapter's bundle-detection signal (Phase 5.9,
    see MIGRATION_PLAN.md's frozen catalogue ADR) - a page listing N
    distinct products under one @graph is treated as a bundle listing.
    """
    found: list[dict] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        candidates = data if isinstance(data, list) else [data]
        expanded: list[dict] = []
        for candidate in candidates:
            if isinstance(candidate, dict) and isinstance(candidate.get("@graph"), list):
                expanded.extend(item for item in candidate["@graph"] if isinstance(item, dict))
            elif isinstance(candidate, dict):
                expanded.append(candidate)

        found.extend(item for item in expanded if _is_product_type(item.get("@type")))
    return found


def _is_product_type(type_value: object) -> bool:
    if isinstance(type_value, str):
        return type_value == "Product"
    if isinstance(type_value, list):
        return "Product" in type_value
    return False


def _attributes_from_jsonld(data: dict) -> dict[str, NormalizedAttribute]:
    """
    Shared by _normalize_jsonld (the primary/single-product path) and
    _bundle_evidence_from_jsonld (Phase 5.9's per-member hints) - the same
    small set of schema.org properties maps into the same canonical
    fields regardless of whether the entity turns out to be the page's
    one product or one member of a detected bundle.
    """
    attributes: dict[str, NormalizedAttribute] = {}

    brand = _extract_brand(data.get("brand"))
    if brand:
        attributes["brand"] = NormalizedAttribute(value=TextValue(text=brand), confidence=0.9)

    color = data.get("color")
    if isinstance(color, str) and color.strip():
        attributes["color"] = NormalizedAttribute(value=ColorValue(label=color.strip()), confidence=0.8)

    material = data.get("material")
    if material:
        items = [m.strip() for m in material.split(",")] if isinstance(material, str) else [str(material)]
        attributes["materials"] = NormalizedAttribute(value=ListValue(items=items), confidence=0.7)

    return attributes


def _normalize_jsonld(url: str, data: dict) -> NormalizedProductEvidence:
    title = data.get("name")
    brand = _extract_brand(data.get("brand"))

    return NormalizedProductEvidence(
        source_type="generic_url",
        source_url=url,
        title=title if isinstance(title, str) else None,
        brand=brand,
        images=_extract_images(data.get("image"), url),
        attributes=_attributes_from_jsonld(data),
    )


def _bundle_evidence_from_jsonld(soup: BeautifulSoup, products_jsonld: list[dict]) -> NormalizedBundleEvidence:
    """
    Builds one uniform member hint per detected Product entity - all of
    them, not just the ones beyond the first, so a human reviewing the
    bundle (Phase 5.10+) sees every member represented the same way
    rather than one implicitly-special "primary" item. The bundle's own
    title falls back to the page's <title> tag, since a dedicated "this
    is a bundle" JSON-LD node is not something this narrow heuristic
    assumes exists.
    """
    page_title = soup.title.string.strip() if soup.title and soup.title.string else None
    member_hints = [
        BundleMemberHint(
            label=item.get("name") if isinstance(item.get("name"), str) else "Unnamed item",
            attributes=_attributes_from_jsonld(item),
        )
        for item in products_jsonld
    ]
    return NormalizedBundleEvidence(title=page_title, member_hints=member_hints)


def _extract_brand(brand_field: object) -> str | None:
    if isinstance(brand_field, str):
        return brand_field
    if isinstance(brand_field, dict):
        name = brand_field.get("name")
        return name if isinstance(name, str) else None
    return None


def _extract_images(image_field: object, page_url: str) -> list[NormalizedProductImage]:
    if image_field is None:
        return []
    raw_list = image_field if isinstance(image_field, list) else [image_field]
    images: list[NormalizedProductImage] = []
    for item in raw_list:
        if isinstance(item, str):
            images.append(NormalizedProductImage(url=urljoin(page_url, item)))
        elif isinstance(item, dict) and isinstance(item.get("url"), str):
            images.append(NormalizedProductImage(url=urljoin(page_url, item["url"])))
    return images


def _normalize_opengraph(url: str, soup: BeautifulSoup) -> tuple[dict, NormalizedProductEvidence]:
    def meta(prop: str) -> str | None:
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        content = tag.get("content") if tag else None
        return content.strip() if isinstance(content, str) and content.strip() else None

    og_title = meta("og:title")
    og_image = meta("og:image")
    og_description = meta("og:description")
    page_title = soup.title.string.strip() if soup.title and soup.title.string else None

    raw = {"og:title": og_title, "og:image": og_image, "og:description": og_description, "title": page_title}

    title = og_title or page_title
    images = [NormalizedProductImage(url=urljoin(url, og_image))] if og_image else []

    normalized = NormalizedProductEvidence(
        source_type="generic_url", source_url=url, title=title, images=images
    )
    return raw, normalized
