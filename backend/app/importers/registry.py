"""
Import Provider registry.

Adding a future provider (ZIP archive, local folder, TikTok slideshow,
Amazon/Shopify product page, cloud storage) is: implement ImportProvider
in a new module, add one line here. No other code changes.
"""

from app.importers.base import ImportProvider
from app.importers.local_file import LocalFileImporter
from app.importers.playwright_tiktok import PlaywrightTikTokImporter

IMPORTERS: dict[str, type[ImportProvider]] = {
    "local_file": LocalFileImporter,
    "tiktok": PlaywrightTikTokImporter,
}


def get_importer(source_type: str) -> ImportProvider:
    importer_cls = IMPORTERS.get(source_type)
    if importer_cls is None:
        known = ", ".join(sorted(IMPORTERS))
        raise ValueError(f"Unknown import source '{source_type}'. Known sources: {known}")
    return importer_cls()
