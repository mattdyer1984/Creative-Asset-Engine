"""
ImportProvider — the interface every import source implements.

Plan reference: architecture plan §5.2.

This mirrors the AI Provider pattern (app.ai_providers, introduced in M2):
a small interface plus a registry, so new sources can be added later
(ZIP archives, local folders, TikTok slideshows, Amazon/Shopify product
pages, cloud storage) without touching anything that consumes their
output.
"""

from typing import Protocol

from app.domain import MarketingCreative


class ImportProvider(Protocol):
    def import_source(self, source_config: dict) -> list[MarketingCreative]:
        """
        Given provider-specific configuration (e.g. file contents for
        LocalFileImporter, a URL for a future TikTokSlideshowImporter),
        return one or more MarketingCreative objects.

        Whatever downloading, unzipping, scraping, or API-calling a given
        provider needs to do happens entirely inside this method - nothing
        about that work is visible to the caller.
        """
        ...
