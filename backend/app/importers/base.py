"""
ImportProvider — the interface every import source implements.

Plan reference: architecture plan §5.2.

This mirrors the AI Provider pattern (app.ai_providers, introduced in M2):
a small interface plus a registry, so new sources can be added later
(ZIP archives, local folders, TikTok slideshows, Amazon/Shopify product
pages, cloud storage) without touching anything that consumes their
output.

Return type changed from `list[MarketingCreative]` to `EvidencePackage`
in Phase 10.5 of AI Creative Engine vNext (see MIGRATION_PLAN.md's ADR
§4a) - a real, if additive-in-spirit, breaking change to already-shipped
code, not purely additive like most of that ADR. MarketingCreative
itself is unchanged; it's nested inside the package's `media_assets`
rather than being the return type directly, so the analysis pipeline's
per-image handling is unaffected - only the boundary between an
ImportProvider and the Evidence Engine (app.services.evidence_router)
changes.
"""

from typing import Protocol

from app.domain import EvidencePackage


class ImportProvider(Protocol):
    def import_source(self, source_config: dict) -> EvidencePackage:
        """
        Given provider-specific configuration (e.g. file contents for
        LocalFileImporter, a URL for a future TikTokSlideshowImporter),
        return one EvidencePackage - the per-image MarketingCreative
        objects plus whatever package-level provenance this source
        actually has (creator/caption/hashtags/product_references/raw).
        A source with no such context (LocalFileImporter) still returns
        a real EvidencePackage, just with those fields left None/empty -
        the correct, expected value for an upload with no platform
        context, not a gap to work around.

        Whatever downloading, unzipping, scraping, or API-calling a given
        provider needs to do happens entirely inside this method - nothing
        about that work is visible to the caller.
        """
        ...
