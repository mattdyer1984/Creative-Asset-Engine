"""
Import integrity gate — Critical TikTok Slideshow Import Fix (see
MIGRATION_PLAN.md). A real bug (a 4-image TikTok slideshow silently
importing as 1 image, with a clean 201) traced back to three separate
places quietly dropping partial failures and a persistence layer
(app.services.slideshow_import) that trusted whatever count an Import
Provider returned as ground truth, with zero independent verification.

This module is that independent verification. `check_import_integrity`
is a pure function - it never re-decodes image bytes a second time
(both PlaywrightTikTokImporter and DownieImporter already validate
their own assets and report what they dropped via
EvidencePackage.failed_assets/downloaded_count) - it just checks the
package's own reported numbers against the independently-known expected
count, checks ordering, and checks for duplicates.
"""

import hashlib
import logging
from dataclasses import dataclass

from app.domain import EvidencePackage

logger = logging.getLogger(__name__)


@dataclass
class ImportIntegrityReport:
    provider: str
    content_type: str
    slides_detected: int
    slides_downloaded: int
    slides_validated: int
    ordering_verified: bool
    duplicate_count: int
    failed_assets: list[dict]
    complete: bool


def check_import_integrity(
    provider: str, content_type: str, expected_count: int, package: EvidencePackage
) -> ImportIntegrityReport:
    """
    The gate. `complete` is the single boolean everything else in the
    import chain hinges on - the pipeline must never continue past an
    import where this is False (see app.services.tiktok_import_chain).
    """
    media_assets = package.media_assets
    slides_validated = len(media_assets)

    indices = [mc.raw_metadata.get("index") for mc in media_assets]
    ordering_verified = None not in indices and sorted(indices) == list(range(len(indices)))

    hashes = [hashlib.sha256(mc.image_bytes).hexdigest() for mc in media_assets]
    duplicate_count = len(hashes) - len(set(hashes))

    complete = (
        slides_validated == expected_count
        and package.downloaded_count == expected_count
        and ordering_verified
        and duplicate_count == 0
    )

    return ImportIntegrityReport(
        provider=provider,
        content_type=content_type,
        slides_detected=expected_count,
        slides_downloaded=package.downloaded_count,
        slides_validated=slides_validated,
        ordering_verified=ordering_verified,
        duplicate_count=duplicate_count,
        failed_assets=package.failed_assets,
        complete=complete,
    )


def log_integrity_report(report: ImportIntegrityReport) -> None:
    """Exactly the log format the product spec requires - one line per fact, always in this order."""
    logger.info("Import provider: %s", report.provider.title())
    logger.info("Content type: %s", report.content_type)
    logger.info("Slides detected: %s", report.slides_detected)
    logger.info("Slides downloaded: %s", report.slides_downloaded)
    logger.info("Slide ordering verified: %s", str(report.ordering_verified).lower())
    logger.info("Import complete: %s", str(report.complete).lower())
