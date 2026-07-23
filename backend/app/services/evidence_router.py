"""
Evidence Router — Phase 10.5 of AI Creative Engine vNext (see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §4b). Turns one
EvidencePackage (whatever an ImportProvider just returned) into a
persisted EvidenceSource row - the package-level facts that have nowhere
else to live, kept separate from the per-image Slideshow/Slide rows
app.services.slideshow_import already owns.

Deliberately a single small function, not a class: there is exactly one
thing to route an EvidencePackage to today (an EvidenceSource row).
Future platform-specific routing (e.g. resolving product_references
against real Products) is out of this phase's scope - see the ADR's
§4b non-goals.
"""

from sqlalchemy.orm import Session

from app.domain import EvidencePackage
from app.models.evidence_source import EvidenceSource


def record_evidence_source(
    db: Session, package: EvidencePackage, project_id: str | None, evidence_type: str
) -> EvidenceSource:
    """
    Persist (flush, not commit - the caller owns the transaction, same
    convention as app.services.slideshow_import's own _persist_* helpers)
    one EvidenceSource row for this EvidencePackage. `evidence_type` is
    the caller's own routing purpose (e.g. "slideshow_upload") - see
    app.models.evidence_source's docstring for why this isn't derived
    from `package.source_platform` here.
    """
    evidence_source = EvidenceSource(
        project_id=project_id,
        evidence_type=evidence_type,
        source_locator=package.original_url,
        source_platform=package.source_platform,
        creator_json=(
            {
                "handle": package.creator.handle,
                "display_name": package.creator.display_name,
                "profile_url": package.creator.profile_url,
            }
            if package.creator is not None
            else None
        ),
        caption=package.caption,
        hashtags_json=list(package.hashtags),
        product_references_json=[
            {"label": ref.label, "external_id": ref.external_id, "url": ref.url}
            for ref in package.product_references
        ],
        platform_metadata_json=dict(package.platform_metadata),
        raw_json=dict(package.raw),
        imported_at=package.imported_at,
    )
    db.add(evidence_source)
    db.flush()  # assigns evidence_source.id without committing yet
    return evidence_source
