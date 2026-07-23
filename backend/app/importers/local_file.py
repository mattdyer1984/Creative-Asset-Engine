"""
LocalFileImporter — V1's only Import Provider.

Takes files already read into memory (the API layer reads them from the
browser's file upload) and returns one MarketingCreative per file,
wrapped in an EvidencePackage (Phase 10.5 of AI Creative Engine vNext,
see MIGRATION_PLAN.md's ADR §4a) - creator/caption/hashtags/
product_references left None/empty, the correct, expected value for a
local upload with no platform context.
"""

from datetime import datetime, timezone

from app.domain import EvidencePackage, MarketingCreative


class LocalFileImporter:
    """
    source_config shape:
        {
            "files": [
                {"filename": "hero-shot.jpg", "content": b"..."},
                ...
            ]
        }
    """

    def import_source(self, source_config: dict) -> EvidencePackage:
        files = source_config.get("files", [])
        now = datetime.now(timezone.utc)

        media_assets = [
            MarketingCreative(
                image_bytes=file["content"],
                original_filename=file["filename"],
                source_type="local_file",
                source_locator=file["filename"],
                imported_at=now,
                raw_metadata={},
            )
            for file in files
        ]

        return EvidencePackage(
            source_platform="local_file",
            media_assets=media_assets,
            imported_at=now,
        )
