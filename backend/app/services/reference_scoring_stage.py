"""
Reference Scoring Stage — Phase 9.2 of Product Lock v2 (see
MIGRATION_PLAN.md's "ADR: Canonical Product Reference" §4). Curates the
Canonical Reference Library: scores every unscored candidate
ProductReferenceImage for a product and writes quality_score/
quality_reasons_json/role/library_status back onto that same row.

Not AnalysisArtifactMixin-shaped and does not create new rows - this
Stage updates existing ProductReferenceImage rows in place. There is
nothing to version: a candidate is scored once (library_status flips
from null to "included"/"rejected") and stays that way until an
explicit re-score is requested (not built in this sub-phase - see the
ADR's "Refreshed"/"Replaced" discussion for what that would mean).

Deliberately does NOT create AnalysisRun rows for the Tier 2 vision
calls, unlike every other real paid AI call in this codebase - a real
design decision made during implementation, not an oversight.
ProductReferenceImage.analysis_run_id already means "the run that
acquired this image" (Product Isolation, or null for URL-sourced rows)
and overwriting it here would destroy that provenance for no benefit.
quality_reasons_json is this Stage's own audit trail instead - "record
the reasoning, not just the number," the same discipline
ImageValidationResult.field_checks_json already established - and is
sufficient without a parallel AnalysisRun log entry pointing nowhere.

Two-tier scoring, per the ADR's "compute what can be computed, don't
ask the AI for free facts" discipline:
- Tier 1 (free, deterministic, always run): resolution and file size as
  a crude sharpness proxy. Filters out obviously-unusable candidates
  before spending a Tier 2 call on them.
- Tier 2 (one VisionAnalysisProvider.analyze_creative call per Tier-1
  survivor): role classification, front-visibility, occlusion, brand-
  readability, packaging-visibility, composition quality. quality_score
  is computed in code from these structured judgments - never asked of
  the AI as a bare number, same rule this codebase applies everywhere
  a pass/fail or score is derived from AI-provided facts.
"""

from io import BytesIO
from pathlib import Path

from PIL import Image
from sqlalchemy.orm import Session

from app.ai_providers.registry import default_registry
from app.models.product_reference_image import ProductReferenceImage
from app.services.reference_acquisition import get_unscored_candidates
from app.stages.base import StageResult

# Tier 1 floor - deliberately conservative, filters only the obviously
# unusable (near-blank/corrupt crops, thumbnail-sized images) rather
# than trying to be a real quality judgment on its own.
MIN_DIMENSION_PX = 200
MIN_FILE_SIZE_BYTES = 5_000

TIER2_SCHEMA = {
    "type": "object",
    "properties": {
        "role": {
            "type": "string",
            "enum": [
                "hero", "front", "45_degree", "side", "rear",
                "packaging", "branding_closeup", "other",
            ],
        },
        "front_visible": {"type": "boolean"},
        "occluded": {"type": "boolean"},
        "brand_readable": {"type": "boolean"},
        "packaging_visible": {"type": "boolean"},
        "composition_quality": {"type": "string", "enum": ["poor", "fair", "good", "excellent"]},
        "reasons": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "role", "front_visible", "occluded", "brand_readable",
        "packaging_visible", "composition_quality", "reasons",
    ],
    "additionalProperties": False,
}

_COMPOSITION_SCORE = {"poor": 0.0, "fair": 0.33, "good": 0.67, "excellent": 1.0}

QUALITY_FLOOR = 0.5


def _tier1_score(image_bytes: bytes, file_size: int) -> tuple[float, list[str], bool]:
    """Returns (score 0-1, reasons, cleared_floor)."""
    reasons = []
    try:
        with _open_image(image_bytes) as img:
            width, height = img.size
    except Exception:
        return 0.0, ["could not read image dimensions"], False

    if min(width, height) < MIN_DIMENSION_PX:
        reasons.append(f"below minimum dimension ({width}x{height})")
        return 0.0, reasons, False
    if file_size < MIN_FILE_SIZE_BYTES:
        reasons.append(f"file size too small to be usable ({file_size} bytes)")
        return 0.0, reasons, False

    reasons.append(f"{width}x{height}, {file_size} bytes")
    # Crude sharpness proxy: bytes-per-pixel, normalized against a generous
    # "clearly detailed" reference point rather than a precise metric.
    bytes_per_pixel = file_size / max(width * height, 1)
    sharpness_score = min(bytes_per_pixel / 0.5, 1.0)
    return sharpness_score, reasons, True


def _open_image(image_bytes: bytes):
    return Image.open(BytesIO(image_bytes))


def _score_one(db: Session, image: ProductReferenceImage, vision_provider) -> None:
    image_bytes = Path(image.file_path).read_bytes()
    file_size = len(image_bytes)

    tier1_score, tier1_reasons, cleared_floor = _tier1_score(image_bytes, file_size)

    if not cleared_floor:
        image.quality_score = tier1_score
        image.quality_reasons_json = tier1_reasons
        image.library_status = "rejected"
        return

    tier2 = vision_provider.analyze_creative(
        image_bytes=image_bytes,
        prompt_spec={
            "prompt": (
                "This is a candidate reference image for a product's Canonical "
                "Reference Library - a curated set of images used to condition "
                "AI image generation so the product's real appearance is "
                "preserved. Classify which view/role this image shows, and "
                "judge its usability as a reference: is the product's front "
                "clearly visible, is it occluded by anything, is any brand "
                "text/logo readable, is packaging visible, and how would you "
                "rate the overall composition. Give short reasons for your "
                "judgments."
            ),
            "schema_name": "reference_scoring",
        },
        response_schema=TIER2_SCHEMA,
    )

    checks = [
        (tier2["front_visible"], "front visible"),
        (not tier2["occluded"], "not occluded"),
        (tier2["brand_readable"], "brand text readable"),
        (tier2["packaging_visible"], "packaging visible"),
    ]
    passed_fraction = sum(1 for ok, _ in checks if ok) / len(checks)
    composition_component = _COMPOSITION_SCORE[tier2["composition_quality"]]
    vision_score = (passed_fraction * 0.75) + (composition_component * 0.25)

    reasons = list(tier1_reasons)
    reasons.append(f"role: {tier2['role']}")
    reasons.append(f"composition: {tier2['composition_quality']}")
    reasons.extend(check_reason for ok, check_reason in checks if not ok)
    reasons.extend(tier2["reasons"])

    image.quality_score = vision_score
    image.quality_reasons_json = reasons
    image.role = tier2["role"]
    image.library_status = "included" if vision_score >= QUALITY_FLOOR else "rejected"


def run_reference_scoring(db: Session, product_id: str) -> StageResult:
    candidates = get_unscored_candidates(db, product_id)
    if not candidates:
        return StageResult(succeeded=True)

    vision_provider = default_registry.vision()

    try:
        for image in candidates:
            _score_one(db, image, vision_provider)
            db.flush()
    except Exception as exc:
        return StageResult(succeeded=False, error=str(exc))

    return StageResult(succeeded=True)
