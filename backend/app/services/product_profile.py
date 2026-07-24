"""
Canonical Product Profile assembly (Phase 5.5 of Product Intelligence,
see MIGRATION_PLAN.md). Merges every current evidence source for a
Product into one field-level, provenance-tagged view - compute-on-read,
mirroring app.services.slideshow_blueprint.assemble_slideshow_blueprint.

Two evidence categories exist today:
- ProductSourceImport (Phase 5.1/5.3) - already normalized at the
  adapter boundary (Phase 5.2/5.3) into the canonical vocabulary, no
  mapping needed here beyond parsing normalized_json back into typed
  ProductAttributeValue instances.
- ProductLockProfile (pre-Phase-5, vision-derived) - predates the
  canonical vocabulary entirely, so this module maps its native schema
  into canonical fields itself - the one place this mapping needs to
  happen (every adapter does it for itself everywhere else).

Precedence: immutable fields prefer ProductSourceImport (listing/URL)
evidence, contextual fields prefer ProductLockProfile (vision) evidence
- already follows directly from CANONICAL_FIELD_VOCABULARY's own
classification (see app.product_sources.base's comment on why this
isn't a separately stored vocabulary property).

Known simplification, flagged rather than solved here: the Product Lock
Profile Stage doesn't emit per-field confidence today. Vision-derived
fields get a flat, documented default confidence
(VISION_DEFAULT_CONFIDENCE) rather than blocking this service on
prompt-engineering work to add real per-field confidence - a reasonable
fast-follow, not a prerequisite for shipping field-level provenance.
"""

from pydantic import BaseModel, Field, TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.product_lock_profile import ProductLockProfile
from app.models.product_source_import import ProductSourceImport
from app.product_sources.base import (
    CANONICAL_FIELD_VOCABULARY,
    ColorValue,
    ListValue,
    ProductAttributeValue,
    TextValue,
)

VISION_DEFAULT_CONFIDENCE = 0.85
SOURCE_TYPE_VISION = "vision"

_ATTRIBUTE_VALUE_ADAPTER: TypeAdapter[ProductAttributeValue] = TypeAdapter(ProductAttributeValue)

# One resolved field's candidate value before it's known whether it wins
# the merge: (value, confidence, source_type, source_id).
_Candidate = tuple[ProductAttributeValue, float, str, str]


class ProductProfileField(BaseModel):
    value: ProductAttributeValue
    source_type: str
    source_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    classification: str  # "immutable" | "contextual" - see CANONICAL_FIELD_VOCABULARY


class ProductProfile(BaseModel):
    product_id: str
    fields: dict[str, ProductProfileField] = Field(default_factory=dict)


def assemble_product_profile(db: Session, product: Product) -> ProductProfile:
    vision_fields = _fields_from_current_lock_profile(db, product.id)
    source_fields = _fields_from_current_source_import(db, product.id)

    merged: dict[str, ProductProfileField] = {}
    for field_name, definition in CANONICAL_FIELD_VOCABULARY.items():
        vision_candidate = vision_fields.get(field_name)
        source_candidate = source_fields.get(field_name)

        winner = (
            (source_candidate or vision_candidate)
            if definition.classification == "immutable"
            else (vision_candidate or source_candidate)
        )
        if winner is None:
            continue

        value, confidence, source_type, source_id = winner
        merged[field_name] = ProductProfileField(
            value=value,
            source_type=source_type,
            source_id=source_id,
            confidence=confidence,
            classification=definition.classification,
        )

    return ProductProfile(product_id=product.id, fields=merged)


def _fields_from_current_source_import(db: Session, product_id: str) -> dict[str, _Candidate]:
    row = db.scalars(
        select(ProductSourceImport).where(
            ProductSourceImport.product_id == product_id,
            ProductSourceImport.is_current.is_(True),
        )
    ).first()
    if row is None or not row.normalized_json:
        return {}

    result: dict[str, _Candidate] = {}
    for field_name, attr in row.normalized_json.get("attributes", {}).items():
        if field_name not in CANONICAL_FIELD_VOCABULARY:
            continue  # defensive - normalized_json should already only contain known fields
        value = _ATTRIBUTE_VALUE_ADAPTER.validate_python(attr["value"])
        result[field_name] = (value, attr["confidence"], row.source_type, row.id)
    return result


def extract_branding_text(lock_profile: ProductLockProfile) -> list[str]:
    """
    The exact text printed on the product's own packaging/label, per the
    Product Lock Profile's vision-derived `labels_and_text` field - the
    same extraction `_fields_from_current_lock_profile` below uses to
    populate the canonical `branding_text` field. Public so
    app.services.generation_engine can reuse this exact list to tell the
    image generation model what text to reproduce, not just imply it via
    reference-image conditioning - a real fix for a real, live-confirmed
    bottleneck (see MIGRATION_PLAN.md): the generation prompt previously
    never told the model what the packaging's own text actually says, so
    Stage 2 validation's `branding_text` check (which compares against
    this exact same field) failed almost every real attempt. Reusing the
    identical extraction here keeps what the model is told to reproduce
    and what it's judged against from ever silently drifting apart.
    """
    return [
        label["text"]
        for label in (lock_profile.structured_json.get("labels_and_text") or [])
        if isinstance(label, dict) and label.get("text")
    ]


def _fields_from_current_lock_profile(db: Session, product_id: str) -> dict[str, _Candidate]:
    row = db.scalars(
        select(ProductLockProfile).where(
            ProductLockProfile.product_id == product_id,
            ProductLockProfile.is_current.is_(True),
        )
    ).first()
    if row is None:
        return {}
    data = row.structured_json

    result: dict[str, _Candidate] = {}

    def add(field_name: str, value: ProductAttributeValue | None) -> None:
        if value is not None:
            result[field_name] = (value, VISION_DEFAULT_CONFIDENCE, SOURCE_TYPE_VISION, row.id)

    if data.get("product_category"):
        add("product_category", TextValue(text=data["product_category"]))
    if data.get("shape_and_proportions"):
        add("shape", TextValue(text=data["shape_and_proportions"]))

    packaging = data.get("packaging") or {}
    packaging_text = " · ".join(
        part for part in (packaging.get("type"), packaging.get("closure"), packaging.get("notes")) if part
    )
    if packaging_text:
        add("packaging", TextValue(text=packaging_text))

    if data.get("materials"):
        add("materials", ListValue(items=list(data["materials"])))

    primary_colors = (data.get("colors") or {}).get("primary") or []
    if primary_colors:
        # Vision's colors.primary is a list; the canonical `color` field is
        # a single ColorValue - the first primary color is "the" color for
        # this field, a deliberate simplification, not an oversight.
        add("color", ColorValue(label=primary_colors[0]))

    branding = data.get("branding") or {}
    if branding.get("brand_name"):
        add("brand", TextValue(text=branding["brand_name"]))

    label_texts = extract_branding_text(row)
    if label_texts:
        add("branding_text", ListValue(items=label_texts))

    # viewing_angle and perspective are both camera-framing concepts in the
    # vision schema - folded into the single canonical camera_angle field
    # rather than inventing a second field for "perspective" (revision #5
    # discipline: map into existing fields wherever the concept overlaps).
    camera_text = "; ".join(part for part in (data.get("viewing_angle"), data.get("perspective")) if part)
    if camera_text:
        add("camera_angle", TextValue(text=camera_text))

    if data.get("approximate_scale_in_frame"):
        add("composition", TextValue(text=data["approximate_scale_in_frame"]))

    if data.get("lighting_characteristics"):
        add("lighting", TextValue(text=data["lighting_characteristics"]))

    # Deliberately not mapped: surface_finish, distinguishing_features,
    # immutable_characteristics, extensions - none represent a genuinely
    # new canonical concept (revision #5); they remain visible in
    # ProductLockProfile.structured_json directly, just not promoted here.

    return result
