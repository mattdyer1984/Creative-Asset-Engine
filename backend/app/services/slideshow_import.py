"""
Slideshow import orchestration (new pipeline) - Phase 2.5 of the
Slideshow/Slide migration. Parallel equivalent of
app.services.creative_import.import_creatives.

By default persists each imported MarketingCreative as its own
independent Slideshow + single Slide (batch = independent items, same as
the old pipeline) - Phase 2's cardinality-preserving scope. Phase 4 (true
multi-slide import, see MIGRATION_PLAN.md) adds `group_as_one`: an
explicit, default-off opt-in that instead persists every MarketingCreative
in the batch as Slides (slide_index 0..N-1) on a single Slideshow.
Deliberately NOT the default - multi-file-select today means "N unrelated
items," a real, already-relied-on behavior (see MIGRATION_PLAN.md's Phase
4 plan for the reasoning); grouping is something the caller opts into,
not something inferred from "more than one file was selected."

Reuses app.storage.save_creative_original unchanged (keyed by an
arbitrary id used only as a folder name, so a Slide's id works exactly
as well as a Creative's id did) rather than introducing a new storage
function - the on-disk path still reads storage/creatives/<id>/, which
is a little misleading for what's now a Slide's image, but renaming it
would mean touching storage.py, which the old pipeline also depends on.
Not worth it for Phase 2; worth revisiting once the old pipeline no
longer exists (Phase 2.7+).

Since Phase 10.5 (AI Creative Engine vNext, see MIGRATION_PLAN.md's ADR
§4b), an ImportProvider returns an EvidencePackage rather than a bare
list - this module unwraps `media_assets` for the existing per-image
Slideshow/Slide persistence unchanged, and additionally routes the
package itself through app.services.evidence_router to record its
package-level facts as one EvidenceSource, pointed at by every Slideshow
this call produces. `evidence_type` is looked up per `source_type` (new
in Phase 10.6, adding "tiktok") rather than hardcoded, since a Local
File upload and a TikTok URL import are genuinely different evidence
types per the ADR's own vocabulary (§4b).
"""

from sqlalchemy.orm import Session

from app.domain import EvidencePackage, MarketingCreative
from app.importers import get_importer
from app.models.evidence_source import (
    EVIDENCE_TYPE_SLIDESHOW_UPLOAD,
    EVIDENCE_TYPE_TIKTOK_SLIDESHOW_URL,
)
from app.models._shared import utcnow
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.services.evidence_router import record_evidence_source
from app.services.image_dimensions import measure_dimensions
from app.storage import save_creative_original

_EVIDENCE_TYPE_BY_SOURCE_TYPE = {
    "local_file": EVIDENCE_TYPE_SLIDESHOW_UPLOAD,
    "tiktok": EVIDENCE_TYPE_TIKTOK_SLIDESHOW_URL,
    # DownieImporter (Phase 10.6b) is a fallback implementation behind the
    # same real-world evidence category as "tiktok" above, not a new one -
    # the caller (POST /import-url's `provider` field) picks which
    # ImportProvider actually runs; this app never brands the result by it.
    "downie": EVIDENCE_TYPE_TIKTOK_SLIDESHOW_URL,
}


def import_slideshows(
    db: Session,
    source_type: str,
    source_config: dict,
    project_id: str | None,
    group_as_one: bool = False,
) -> list[Slideshow]:
    """
    Resolve the requested Import Provider, run it, and persist what it
    returns. Thin wrapper around `persist_evidence_package` - the
    Critical TikTok Slideshow Import Fix's orchestrator
    (app.services.tiktok_import_chain) already has an EvidencePackage in
    hand by the time it's ready to persist (having picked a winning
    provider out of several attempts) and calls that shared function
    directly, rather than this one re-running `import_source` a second
    time.
    """
    importer = get_importer(source_type)
    package = importer.import_source(source_config)
    return persist_evidence_package(db, package, source_type, project_id, group_as_one)


def persist_evidence_package(
    db: Session,
    package: EvidencePackage,
    source_type: str,
    project_id: str | None,
    group_as_one: bool = False,
) -> list[Slideshow]:
    """
    Persist an already-obtained EvidencePackage either as N independent
    Slideshows (default) or, if `group_as_one` is set, as a single
    Slideshow with N ordered Slides. Every Slideshow produced points at
    the same EvidenceSource, recording this one Import Provider call's
    package-level facts.
    """
    marketing_creatives = package.media_assets

    if not marketing_creatives:
        return []

    evidence_type = _EVIDENCE_TYPE_BY_SOURCE_TYPE.get(source_type, EVIDENCE_TYPE_SLIDESHOW_UPLOAD)
    evidence_source = record_evidence_source(db, package, project_id, evidence_type=evidence_type)

    if group_as_one:
        return [
            _persist_marketing_creatives_as_one_slideshow(
                db, marketing_creatives, project_id, evidence_source.id
            )
        ]

    return [
        _persist_marketing_creative(db, mc, project_id, evidence_source.id)
        for mc in marketing_creatives
    ]


def _persist_slide(
    db: Session, slideshow_id: str, slide_index: int, marketing_creative: MarketingCreative
) -> Slide:
    slide = Slide(
        slideshow_id=slideshow_id,
        slide_index=slide_index,
        original_filename=marketing_creative.original_filename,
        source_type=marketing_creative.source_type,
        source_locator=marketing_creative.source_locator,
        raw_metadata_json=marketing_creative.raw_metadata,
        # placeholder; replaced below once we have the generated id
        stored_file_path="",
    )
    db.add(slide)
    db.flush()  # assigns slide.id without committing yet

    # Measure source pixel dimensions HERE — the earliest boundary at which the
    # original bytes are guaranteed to exist. Persisted so the evidence survives even
    # if the stored file is later removed. A failed measurement leaves width/height
    # NULL but records the attempt, so "unmeasurable" is distinguishable from
    # "never attempted".
    dims = measure_dimensions(marketing_creative.image_bytes)
    if dims is not None:
        slide.source_width, slide.source_height = dims
        slide.dimension_measurement_source = "ingest:slideshow_import"
        slide.dimension_measured_at = utcnow()
    else:
        slide.dimension_measurement_source = "ingest:slideshow_import:unreadable"
        slide.dimension_measured_at = utcnow()

    stored_path = save_creative_original(
        slide.id, marketing_creative.original_filename, marketing_creative.image_bytes
    )
    slide.stored_file_path = str(stored_path)
    return slide


def _persist_marketing_creative(
    db: Session,
    marketing_creative: MarketingCreative,
    project_id: str | None,
    evidence_source_id: str,
) -> Slideshow:
    slideshow = Slideshow(
        project_id=project_id,
        evidence_source_id=evidence_source_id,
        imported_at=marketing_creative.imported_at,
        source_references_json={
            "source_type": marketing_creative.source_type,
            "source_locator": marketing_creative.source_locator,
            "raw_metadata": marketing_creative.raw_metadata,
        },
    )
    db.add(slideshow)
    db.flush()  # assigns slideshow.id without committing yet

    _persist_slide(db, slideshow.id, 0, marketing_creative)

    db.commit()
    db.refresh(slideshow)
    return slideshow


def _persist_marketing_creatives_as_one_slideshow(
    db: Session,
    marketing_creatives: list[MarketingCreative],
    project_id: str | None,
    evidence_source_id: str,
) -> Slideshow:
    first = marketing_creatives[0]
    slideshow = Slideshow(
        project_id=project_id,
        evidence_source_id=evidence_source_id,
        imported_at=first.imported_at,
        source_references_json={
            # No single source_locator/raw_metadata makes sense for a
            # multi-file group - each Slide already carries its own (see
            # _persist_slide); this just records the shared source_type
            # and how many Slides came from this one import.
            "source_type": first.source_type,
            "grouped_slide_count": len(marketing_creatives),
        },
    )
    db.add(slideshow)
    db.flush()  # assigns slideshow.id without committing yet

    for index, marketing_creative in enumerate(marketing_creatives):
        _persist_slide(db, slideshow.id, index, marketing_creative)

    db.commit()
    db.refresh(slideshow)
    return slideshow
