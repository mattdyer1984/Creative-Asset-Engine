"""
Tests for the import integrity gate (Critical TikTok Slideshow Import
Fix, see MIGRATION_PLAN.md) - app.services.import_integrity.
check_import_integrity is pure and deterministic; these tests build
EvidencePackage/MarketingCreative instances directly rather than going
through a real Import Provider.
"""

import logging
from datetime import datetime, timezone

from app.domain import EvidencePackage, MarketingCreative
from app.services.import_integrity import check_import_integrity, log_integrity_report


def _asset(index: int, content: bytes = b"") -> MarketingCreative:
    return MarketingCreative(
        image_bytes=content or f"content-{index}".encode(),
        original_filename=f"slide_{index}.jpg",
        source_type="tiktok",
        source_locator=f"https://cdn.example/{index}.jpg",
        imported_at=datetime.now(timezone.utc),
        raw_metadata={"index": index},
    )


def _package(assets: list[MarketingCreative], downloaded_count: int, failed_assets: list[dict] | None = None):
    return EvidencePackage(
        source_platform="tiktok",
        media_assets=assets,
        downloaded_count=downloaded_count,
        failed_assets=failed_assets or [],
    )


def test_complete_import_passes_the_gate():
    package = _package([_asset(0), _asset(1), _asset(2), _asset(3)], downloaded_count=4)

    report = check_import_integrity("tiktok", "slideshow", 4, package)

    assert report.complete is True
    assert report.slides_detected == 4
    assert report.slides_downloaded == 4
    assert report.slides_validated == 4
    assert report.ordering_verified is True
    assert report.duplicate_count == 0


def test_count_mismatch_fails_the_gate():
    package = _package([_asset(0)], downloaded_count=1, failed_assets=[{"index": 1, "reason": "no URL"}])

    report = check_import_integrity("tiktok", "slideshow", 4, package)

    assert report.complete is False
    assert report.slides_downloaded == 1
    assert report.failed_assets == [{"index": 1, "reason": "no URL"}]


def test_broken_ordering_fails_the_gate():
    # index 2 missing, a gap in the sequence - a real symptom of a
    # provider silently reordering or partially failing without
    # reporting it via failed_assets.
    package = _package([_asset(0), _asset(1), _asset(3)], downloaded_count=3)

    report = check_import_integrity("tiktok", "slideshow", 3, package)

    assert report.ordering_verified is False
    assert report.complete is False


def test_duplicate_content_fails_the_gate():
    duplicate_bytes = b"same-bytes-twice"
    package = _package(
        [_asset(0, duplicate_bytes), _asset(1, duplicate_bytes)],
        downloaded_count=2,
    )

    report = check_import_integrity("tiktok", "slideshow", 2, package)

    assert report.duplicate_count == 1
    assert report.complete is False


def test_log_integrity_report_emits_the_exact_required_format(caplog):
    package = _package([_asset(0), _asset(1), _asset(2), _asset(3)], downloaded_count=4)
    report = check_import_integrity("downie", "slideshow", 4, package)

    with caplog.at_level(logging.INFO, logger="app.services.import_integrity"):
        log_integrity_report(report)

    lines = [record.message for record in caplog.records]
    assert lines == [
        "Import provider: Downie",
        "Content type: slideshow",
        "Slides detected: 4",
        "Slides downloaded: 4",
        "Slide ordering verified: true",
        "Import complete: true",
    ]
