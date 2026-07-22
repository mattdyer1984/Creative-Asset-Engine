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
"""

import json
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.product_sources.base import (
    ColorValue,
    ListValue,
    NormalizedAttribute,
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

        product_jsonld = _find_product_jsonld(soup)
        if product_jsonld is not None:
            return ProductSourceExtraction(raw=product_jsonld, normalized=_normalize_jsonld(url, product_jsonld))

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


def _find_product_jsonld(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        candidates = data if isinstance(data, list) else [data]
        # @graph is a common JSON-LD pattern bundling multiple entities
        # (Product, Organization, BreadcrumbList, ...) in one script block.
        expanded: list[dict] = []
        for candidate in candidates:
            if isinstance(candidate, dict) and isinstance(candidate.get("@graph"), list):
                expanded.extend(item for item in candidate["@graph"] if isinstance(item, dict))
            elif isinstance(candidate, dict):
                expanded.append(candidate)

        for item in expanded:
            if _is_product_type(item.get("@type")):
                return item
    return None


def _is_product_type(type_value: object) -> bool:
    if isinstance(type_value, str):
        return type_value == "Product"
    if isinstance(type_value, list):
        return "Product" in type_value
    return False


def _normalize_jsonld(url: str, data: dict) -> NormalizedProductEvidence:
    title = data.get("name")
    brand = _extract_brand(data.get("brand"))

    attributes: dict[str, NormalizedAttribute] = {}
    if brand:
        attributes["brand"] = NormalizedAttribute(value=TextValue(text=brand), confidence=0.9)

    color = data.get("color")
    if isinstance(color, str) and color.strip():
        attributes["color"] = NormalizedAttribute(value=ColorValue(label=color.strip()), confidence=0.8)

    material = data.get("material")
    if material:
        items = [m.strip() for m in material.split(",")] if isinstance(material, str) else [str(material)]
        attributes["materials"] = NormalizedAttribute(value=ListValue(items=items), confidence=0.7)

    return NormalizedProductEvidence(
        source_type="generic_url",
        source_url=url,
        title=title if isinstance(title, str) else None,
        brand=brand,
        images=_extract_images(data.get("image"), url),
        attributes=attributes,
    )


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
