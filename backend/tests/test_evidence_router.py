"""
Tests for app.services.evidence_router (Phase 10.5 of AI Creative Engine
vNext, see MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §4b).
"""

from datetime import datetime, timezone

from sqlalchemy import select

from app.domain import CreatorInfo, EvidencePackage, MarketingCreative, ProductReferenceHint
from app.models.evidence_source import (
    EVIDENCE_TYPE_SLIDESHOW_UPLOAD,
    EVIDENCE_TYPE_TIKTOK_SLIDESHOW_URL,
    STATUS_SUCCEEDED,
    EvidenceSource,
)
from app.models.project import Project
from app.services.evidence_router import record_evidence_source


def _package(**overrides) -> EvidencePackage:
    defaults = dict(
        source_platform="local_file",
        media_assets=[
            MarketingCreative(
                image_bytes=b"fake",
                original_filename="a.jpg",
                source_type="local_file",
                source_locator="a.jpg",
                imported_at=datetime.now(timezone.utc),
                raw_metadata={},
            )
        ],
    )
    defaults.update(overrides)
    return EvidencePackage(**defaults)


def test_record_evidence_source_persists_package_level_facts(db_session):
    package = _package(
        source_platform="tiktok",
        original_url="https://tiktok.com/@someone/video/123",
        creator=CreatorInfo(handle="@someone", display_name="Someone", profile_url="https://tiktok.com/@someone"),
        caption="check this out",
        hashtags=["fyp", "product"],
        product_references=[ProductReferenceHint(label="Widget", external_id="abc", url="https://shop/abc")],
        platform_metadata={"video_id": "123"},
        raw={"raw_response": True},
    )

    evidence_source = record_evidence_source(
        db_session, package, project_id=None, evidence_type=EVIDENCE_TYPE_TIKTOK_SLIDESHOW_URL
    )
    db_session.commit()
    db_session.refresh(evidence_source)

    assert evidence_source.id is not None
    assert evidence_source.evidence_type == EVIDENCE_TYPE_TIKTOK_SLIDESHOW_URL
    assert evidence_source.status == STATUS_SUCCEEDED
    assert evidence_source.source_locator == "https://tiktok.com/@someone/video/123"
    assert evidence_source.source_platform == "tiktok"
    assert evidence_source.creator_json == {
        "handle": "@someone",
        "display_name": "Someone",
        "profile_url": "https://tiktok.com/@someone",
    }
    assert evidence_source.caption == "check this out"
    assert evidence_source.hashtags_json == ["fyp", "product"]
    assert evidence_source.product_references_json == [
        {"label": "Widget", "external_id": "abc", "url": "https://shop/abc"}
    ]
    assert evidence_source.platform_metadata_json == {"video_id": "123"}
    assert evidence_source.raw_json == {"raw_response": True}


def test_record_evidence_source_handles_no_creator_and_no_project(db_session):
    package = _package()

    evidence_source = record_evidence_source(
        db_session, package, project_id=None, evidence_type=EVIDENCE_TYPE_SLIDESHOW_UPLOAD
    )
    db_session.commit()

    assert evidence_source.creator_json is None
    assert evidence_source.project_id is None
    assert evidence_source.source_locator is None
    assert evidence_source.hashtags_json == []
    assert evidence_source.product_references_json == []


def test_record_evidence_source_scopes_to_a_project_when_given(db_session):
    project = Project(name="Summer Launch")
    db_session.add(project)
    db_session.flush()

    evidence_source = record_evidence_source(
        db_session, _package(), project_id=project.id, evidence_type=EVIDENCE_TYPE_SLIDESHOW_UPLOAD
    )
    db_session.commit()

    persisted = db_session.scalars(select(EvidenceSource)).one()
    assert persisted.id == evidence_source.id
    assert persisted.project_id == project.id
