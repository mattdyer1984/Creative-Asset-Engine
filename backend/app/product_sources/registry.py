"""
Product Source registry (Phase 5.2 of Product Intelligence, see
MIGRATION_PLAN.md).

Unlike app.importers/app.ai_providers' registries (keyed by an explicit
string the caller already knows), this one resolves by inspecting the
URL itself - the whole point is that Product Intelligence, and the user
submitting a URL, never need to know or pick which platform it is; the
adapter's own matches() answers that.

Ordered most-specific-first: a platform-specific adapter's matches()
checks its own domain/URL patterns; the generic fallback's matches()
always returns True, so it only ever wins when nothing more specific
did - which requires it to stay last in this list.

No concrete adapters registered yet - Phase 5.3 (generic) and 5.4
(TikTok Shop) add themselves here as they land.
"""

from app.product_sources.base import ProductSourceAdapter

PRODUCT_SOURCE_ADAPTERS: list[type[ProductSourceAdapter]] = []


def get_product_source_adapter(url: str) -> ProductSourceAdapter:
    for adapter_cls in PRODUCT_SOURCE_ADAPTERS:
        adapter = adapter_cls()
        if adapter.matches(url):
            return adapter
    raise ValueError(
        f"No Product Source adapter matches '{url}' - the generic fallback adapter "
        "should always match once registered; this means it hasn't been added to "
        "PRODUCT_SOURCE_ADAPTERS yet."
    )
