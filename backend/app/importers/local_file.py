"""
LocalFileImporter — V1's only Import Provider.

Takes files already read into memory (the API layer reads them from the
browser's file upload) and returns one MarketingCreative per file.
"""

from datetime import datetime, timezone

from app.domain import MarketingCreative


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

    def import_source(self, source_config: dict) -> list[MarketingCreative]:
        files = source_config.get("files", [])
        now = datetime.now(timezone.utc)

        return [
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
