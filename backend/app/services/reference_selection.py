"""
Reference Selection — Phase 9.3 of Product Lock v2 (see
MIGRATION_PLAN.md's "ADR: Canonical Product Reference" §6). Narrows the
Canonical Reference Library down to a small, scene-appropriate
GenerationReferenceSet for one specific generation call.

A separate service from the Prompt Compiler, deliberately: this module
does real I/O (a DB read of the Library, and a provider-capability
query) that the compiler's pure-function contract can't accommodate
without breaking its own test suite's whole premise (plain dicts in,
no DB, no provider). By the time this module's output reaches the
compiler, it's already just a list of file paths - plain data.

Two-step selection, matching the "compute what can be computed" rule
this whole ADR keeps returning to:
1. Scene-aware filtering (classical, free) - the Creative
   Specification's composition/camera_and_perspective text matched
   against each Library image's role tag by keyword. No AI call.
2. Provider-capability limiting - ask the configured provider how many
   reference images it can accept (ImageGenerationProvider.capabilities.
   max_reference_images) and cap the selection there, rather than a
   hardcoded architecture-wide constant.

No TextGenerationProvider-assisted fallback yet (ADR §6 proposes it as
an upgrade path "if classical proves too crude in practice," not built
speculatively now) - if keyword matching finds nothing, this falls back
to ranking the whole Library by quality_score, still classical.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_providers.base import ProviderCapabilities
from app.models.generation_reference_set import GenerationReferenceSet
from app.models.generation_reference_set_image import GenerationReferenceSetImage
from app.models.product_reference_image import ProductReferenceImage

# role -> keywords that, if found in the scene description, prefer that
# role's Library images. Free string matching, not a closed enum - new
# roles Reference Scoring emits just don't get a keyword match and fall
# through to the quality-ranked default, not an error.
_ROLE_KEYWORDS: dict[str, list[str]] = {
    "45_degree": ["45-degree", "45 degree", "three-quarter", "three quarter"],
    "front": ["front-facing", "front on", "straight-on", "straight on", "head-on", "head on"],
    "side": ["side view", "side-on", "profile"],
    "rear": ["rear", "back view", "behind"],
    "packaging": ["packaging", "box", "carton", "in-box"],
    "branding_closeup": ["logo", "label close", "brand close", "close-up on the label", "close up on the brand"],
    "hero": ["hero shot", "hero image"],
}


def _library_images(db: Session, product_id: str) -> list[ProductReferenceImage]:
    return list(
        db.scalars(
            select(ProductReferenceImage).where(
                ProductReferenceImage.product_id == product_id,
                ProductReferenceImage.is_current.is_(True),
                ProductReferenceImage.library_status == "included",
            )
        )
    )


def _scene_text(creative_specification: dict) -> str:
    parts = [
        creative_specification.get("composition") or "",
        creative_specification.get("camera_and_perspective") or "",
    ]
    return " ".join(parts).lower()


def _classical_rank(
    library_images: list[ProductReferenceImage], creative_specification: dict
) -> list[ProductReferenceImage]:
    scene_text = _scene_text(creative_specification)

    matched_roles = {
        role
        for role, keywords in _ROLE_KEYWORDS.items()
        if any(keyword in scene_text for keyword in keywords)
    }

    def sort_key(image: ProductReferenceImage) -> tuple[int, float]:
        role_match = 1 if image.role in matched_roles else 0
        return (role_match, image.quality_score or 0.0)

    return sorted(library_images, key=sort_key, reverse=True)


def select_reference_images(
    db: Session,
    product_id: str,
    creative_specification: dict,
    provider_capabilities: ProviderCapabilities,
) -> GenerationReferenceSet | None:
    """
    Returns None (not an empty GenerationReferenceSet) if the Library
    has no included images yet - matches this codebase's existing
    tri-state discipline (e.g. staleness's tri-state, Narrative
    Structure's forced unclassifiable) for "the precondition genuinely
    isn't met" rather than silently persisting an empty, useless row.
    """
    library_images = _library_images(db, product_id)
    if not library_images:
        return None

    ranked = _classical_rank(library_images, creative_specification)
    limit = max(provider_capabilities.max_reference_images, 0)
    selected = ranked[:limit] if limit else []

    if not selected:
        return None

    generation_reference_set = GenerationReferenceSet(
        analysis_run_id=None,
        generated_image_id=None,
        selection_method_json={
            "method": "classical_role_keyword_match",
            "library_size": len(library_images),
            "provider_max_reference_images": provider_capabilities.max_reference_images,
        },
    )
    db.add(generation_reference_set)
    db.flush()

    for rank, image in enumerate(selected):
        db.add(
            GenerationReferenceSetImage(
                generation_reference_set_id=generation_reference_set.id,
                product_reference_image_id=image.id,
                product_id=product_id,
                role=image.role,
                rank=rank,
            )
        )
    db.flush()

    return generation_reference_set


def get_reference_image_paths(db: Session, generation_reference_set_id: str) -> list[str]:
    """
    Resolves a GenerationReferenceSet's member rows back to real file
    paths, in rank order. Shared by the Generation Engine
    (app.slideshow_stages.image_generation_stage, building the Prompt
    Compiler's hard-prerequisite reference_image_paths) and Stage 1
    Identity Validation (app.slideshow_stages.image_validation_stage,
    Phase 9.4 - re-reading the *same* Set actually used to generate,
    per ADR §7) - one query, not duplicated in both Stage files.
    """
    rows = (
        db.query(GenerationReferenceSetImage, ProductReferenceImage)
        .join(
            ProductReferenceImage,
            ProductReferenceImage.id == GenerationReferenceSetImage.product_reference_image_id,
        )
        .filter(GenerationReferenceSetImage.generation_reference_set_id == generation_reference_set_id)
        .order_by(GenerationReferenceSetImage.rank)
        .all()
    )
    return [reference_image.file_path for _, reference_image in rows]


def create_reference_set_from_ids(
    db: Session, product_id: str, reference_ids: list[str]
) -> GenerationReferenceSet | None:
    """
    Build a GenerationReferenceSet from an EXPLICIT, already-decided list of
    product_reference_image ids - the Transformation Plan's own chosen
    references (after the observed-crop-over-listing precedence in
    transformation_runner). Unlike `select_reference_images`, this runs no
    scene-keyword ranking and no `library_status` filter: the Plan already
    decided which references anchor identity, and this only persists that
    decision so the identity validator (image_validation_stage) compares the
    generated image against the same references generation actually used.

    Returns None for an empty list - matching `select_reference_images`'s
    tri-state, so a slide with no references produces no Set and Stage 1
    Identity Validation skips itself for free (generation_reference_set_id
    stays None on each candidate), exactly like a Story Slide.
    """
    ids = [rid for rid in reference_ids if rid]
    if not ids:
        return None

    generation_reference_set = GenerationReferenceSet(
        analysis_run_id=None,
        generated_image_id=None,
        selection_method_json={
            "method": "transformation_plan_references",
            "reference_count": len(ids),
        },
    )
    db.add(generation_reference_set)
    db.flush()

    for rank, reference_id in enumerate(ids):
        db.add(
            GenerationReferenceSetImage(
                generation_reference_set_id=generation_reference_set.id,
                product_reference_image_id=reference_id,
                product_id=product_id,
                role=None,
                rank=rank,
            )
        )
    db.flush()
    return generation_reference_set
