"""
Dependency-aware staleness (Phase 7.4 of the Narrative pass, see
MIGRATION_PLAN.md's architecture direction for this phase).

An artifact is stale if the upstream artifact it recorded as its input
is no longer the *current* one - e.g. Recreation Prompt was built from
Creative Fingerprint version A, but Creative Fingerprint has since been
regenerated to version B; the Recreation Prompt is now stale relative to
the slide's current state, even though its own content hasn't changed.

Compute-on-read, same philosophy as app.services.slideshow_blueprint.
assemble_slideshow_blueprint itself - never a persisted flag that could
itself go stale.

STAGE_DEPENDENCIES documents the full pipeline graph (derived from
reading the actual current stage code, not invented - see the
architecture direction doc for the reasoning behind each edge). It's not
used for computation directly below - each artifact type records its
provenance differently (single FK columns vs. a JSON id list), so each
gets its own small, direct comparison function - but it's the
authoritative, single-source-of-truth documentation of which stage
depends on which.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.creative_fingerprint import CreativeFingerprint
from app.models.marketing_analysis import MarketingAnalysis
from app.models.narrative_structure import NarrativeStructure
from app.models.ocr_result import OCRResult
from app.models.product_lock_profile import ProductLockProfile
from app.models.product_reference_image import ProductReferenceImage
from app.models.recreation_prompt import RecreationPrompt
from app.models.slideshow import Slideshow

STAGE_DEPENDENCIES: dict[str, list[str]] = {
    "ocr": [],
    "product_isolation": [],
    "product_lock_profile": ["product_isolation"],
    "creative_fingerprint": ["ocr"],
    "marketing_analysis": ["creative_fingerprint"],
    "narrative_structure": ["ocr"],
    "recreation_prompt": ["product_lock_profile", "creative_fingerprint"],
}


@dataclass
class StalenessResult:
    is_stale: bool
    stale_because: list[str] = field(default_factory=list)


def _fresh() -> StalenessResult:
    return StalenessResult(is_stale=False, stale_because=[])


def _unknown() -> StalenessResult:
    """No provenance recorded (a pre-dependency-tracking row, or a dependency that was never used) - can't say either way."""
    return StalenessResult(is_stale=False, stale_because=[])


def product_lock_profile_staleness(db: Session, lock_profile: ProductLockProfile) -> StalenessResult:
    """
    recorded_ids may legitimately be empty (Product Lock Profile can run
    before Product Isolation ever has - see that stage's own docstring) -
    handled correctly by direct set comparison below, not a special case:
    empty-vs-empty is fresh, empty-vs-now-populated is exactly the "went
    stale because isolation ran since" case this function exists to catch.
    """
    current_ids = {
        img.id
        for img in db.query(ProductReferenceImage).filter(
            ProductReferenceImage.product_id == lock_profile.product_id,
            ProductReferenceImage.is_current.is_(True),
        )
    }
    recorded_ids = set(lock_profile.reference_image_ids_json or [])
    if current_ids != recorded_ids:
        return StalenessResult(is_stale=True, stale_because=["product_isolation"])
    return _fresh()


def creative_fingerprint_staleness(db: Session, fingerprint: CreativeFingerprint) -> StalenessResult:
    if fingerprint.ocr_result_id is None:
        return _unknown()
    ocr_result = db.get(OCRResult, fingerprint.ocr_result_id)
    if ocr_result is None or not ocr_result.is_current:
        return StalenessResult(is_stale=True, stale_because=["ocr"])
    return _fresh()


def marketing_analysis_staleness(db: Session, marketing_analysis: MarketingAnalysis) -> StalenessResult:
    if marketing_analysis.creative_fingerprint_id is None:
        return _unknown()
    fingerprint = db.get(CreativeFingerprint, marketing_analysis.creative_fingerprint_id)
    if fingerprint is None or not fingerprint.is_current:
        return StalenessResult(is_stale=True, stale_because=["creative_fingerprint"])
    return _fresh()


def narrative_structure_staleness(db: Session, narrative: NarrativeStructure) -> StalenessResult:
    slideshow = db.get(Slideshow, narrative.slideshow_id)
    if slideshow is None:
        return _unknown()
    current_ids = [slide.current_ocr_result_id for slide in slideshow.slides]
    recorded_ids = list(narrative.ocr_result_ids_json or [])
    if current_ids != recorded_ids:
        return StalenessResult(is_stale=True, stale_because=["ocr"])
    return _fresh()


def recreation_prompt_staleness(db: Session, recreation_prompt: RecreationPrompt) -> StalenessResult:
    stale_because: list[str] = []

    lock_profile = db.get(ProductLockProfile, recreation_prompt.product_lock_profile_id)
    if lock_profile is None or not lock_profile.is_current:
        stale_because.append("product_lock_profile")

    fingerprint = db.get(CreativeFingerprint, recreation_prompt.creative_fingerprint_id)
    if fingerprint is None or not fingerprint.is_current:
        stale_because.append("creative_fingerprint")

    return StalenessResult(is_stale=bool(stale_because), stale_because=stale_because)
