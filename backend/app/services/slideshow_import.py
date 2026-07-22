"""
Slideshow import orchestration (new pipeline) - Phase 2.5 of the
Slideshow/Slide migration. Parallel equivalent of
app.services.creative_import.import_creatives.

Persists each imported MarketingCreative as its own independent
Slideshow + single Slide, matching Phase 2's cardinality-preserving
scope - true multi-file-as-one-slideshow import is Phase 4, not this one.

Reuses app.storage.save_creative_original unchanged (keyed by an
arbitrary id used only as a folder name, so a Slide's id works exactly
as well as a Creative's id did) rather than introducing a new storage
function - the on-disk path still reads storage/creatives/<id>/, which
is a little misleading for what's now a Slide's image, but renaming it
would mean touching storage.py, which the old pipeline also depends on.
Not worth it for Phase 2; worth revisiting once the old pipeline no
longer exists (Phase 2.7+).
"""

from sqlalchemy.orm import Session

from app.domain import MarketingCreative
from app.importers import get_importer
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.storage import save_creative_original


def import_slideshows(
    db: Session,
    source_type: str,
    source_config: dict,
    project_id: str | None,
) -> list[Slideshow]:
    """
    Resolve the requested Import Provider, run it, and persist every
    MarketingCreative it returns as its own independent Slideshow (with
    one Slide) - batch = independent items, same as the old pipeline.
    """
    importer = get_importer(source_type)
    marketing_creatives = importer.import_source(source_config)

    return [
        _persist_marketing_creative(db, mc, project_id)
        for mc in marketing_creatives
    ]


def _persist_marketing_creative(
    db: Session,
    marketing_creative: MarketingCreative,
    project_id: str | None,
) -> Slideshow:
    slideshow = Slideshow(
        project_id=project_id,
        imported_at=marketing_creative.imported_at,
        source_references_json={
            "source_type": marketing_creative.source_type,
            "source_locator": marketing_creative.source_locator,
            "raw_metadata": marketing_creative.raw_metadata,
        },
    )
    db.add(slideshow)
    db.flush()  # assigns slideshow.id without committing yet

    slide = Slide(
        slideshow_id=slideshow.id,
        slide_index=0,
        original_filename=marketing_creative.original_filename,
        source_type=marketing_creative.source_type,
        source_locator=marketing_creative.source_locator,
        raw_metadata_json=marketing_creative.raw_metadata,
        # placeholder; replaced below once we have the generated id
        stored_file_path="",
    )
    db.add(slide)
    db.flush()  # assigns slide.id without committing yet

    stored_path = save_creative_original(
        slide.id, marketing_creative.original_filename, marketing_creative.image_bytes
    )
    slide.stored_file_path = str(stored_path)

    db.commit()
    db.refresh(slideshow)
    return slideshow
