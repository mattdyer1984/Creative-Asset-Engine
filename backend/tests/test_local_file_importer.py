"""
Tests for app.importers.local_file.LocalFileImporter's Phase 10.5 return
type change (list[MarketingCreative] -> EvidencePackage, see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §4a).
"""

from app.domain import EvidencePackage
from app.importers.local_file import LocalFileImporter


def test_import_source_returns_an_evidence_package_wrapping_the_files():
    importer = LocalFileImporter()

    package = importer.import_source(
        {
            "files": [
                {"filename": "a.jpg", "content": b"aaa"},
                {"filename": "b.jpg", "content": b"bbb"},
            ]
        }
    )

    assert isinstance(package, EvidencePackage)
    assert package.source_platform == "local_file"
    assert package.imported_at is not None
    assert [m.original_filename for m in package.media_assets] == ["a.jpg", "b.jpg"]
    assert [m.image_bytes for m in package.media_assets] == [b"aaa", b"bbb"]
    assert package.creator is None
    assert package.hashtags == []
    assert package.product_references == []


def test_import_source_with_no_files_returns_an_empty_package():
    package = LocalFileImporter().import_source({"files": []})

    assert isinstance(package, EvidencePackage)
    assert package.media_assets == []
