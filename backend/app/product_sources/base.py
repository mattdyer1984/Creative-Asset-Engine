"""
ProductSourceAdapter - the Stage-equivalent interface every Product
Source implements, plus the shared contract every adapter normalizes
into: a small, closed set of typed attribute-value shapes
(ProductAttributeValue), the canonical field vocabulary
(CANONICAL_FIELD_VOCABULARY), and the normalized evidence shape adapters
return (NormalizedProductEvidence).

Standing design principle this whole module exists to serve (see
MIGRATION_PLAN.md, Phase 5 revision #4): the Product Profile is a
canonical contract future systems (Generation Engine, Validation Engine,
future Product Sources) depend on, not a UI convenience - field values
carry enough structure to be machine-comparable, not just
human-readable strings.

Vocabulary discipline (see MIGRATION_PLAN.md, Phase 5 revision #5): this
vocabulary is intentionally small and stable. Adapters normalize INTO
these fields wherever possible. A new canonical field is added only when
it represents a genuinely new product concept the existing model cannot
express - not because one adapter's source happens to expose something
that doesn't map cleanly. Anything an adapter extracts that doesn't map
to an existing field belongs in ProductSourceImport.raw_response_json,
never a new field added just to fit it in.
"""

from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, Field

# --- Typed attribute values -------------------------------------------------
#
# A field's value is not a bare string. The Validation Engine's job is
# comparing a generated output against the canonical product and measuring
# fidelity - comparing free-text strings ("red" vs. "crimson") is fragile
# in a way comparing structured values isn't. This is a small, CLOSED set
# of shapes - not an open-ended type system - covering exactly the kinds
# of values implied by the fields already named across the Phase 5
# planning conversation.


class TextValue(BaseModel):
    kind: Literal["text"] = "text"
    text: str


class DimensionValue(BaseModel):
    kind: Literal["dimension"] = "dimension"
    length: float | None = None
    width: float | None = None
    height: float | None = None
    unit: str


class ColorValue(BaseModel):
    """
    Both a human-readable label and a machine-comparable hex value where
    extractable. Neither alone is enough: a Validation Engine needs the
    hex to measure fidelity numerically, a human reading the profile
    needs the label. hex is optional - not every source (e.g. a vision
    model asked for a color name) will have it.
    """

    kind: Literal["color"] = "color"
    label: str
    hex: str | None = None


class NumberValue(BaseModel):
    kind: Literal["number"] = "number"
    value: float
    unit: str | None = None


class ListValue(BaseModel):
    kind: Literal["list"] = "list"
    items: list[str]


ProductAttributeValue = Annotated[
    TextValue | DimensionValue | ColorValue | NumberValue | ListValue,
    Field(discriminator="kind"),
]

_VALUE_KIND_TO_TYPE: dict[str, type[BaseModel]] = {
    "text": TextValue,
    "dimension": DimensionValue,
    "color": ColorValue,
    "number": NumberValue,
    "list": ListValue,
}


# --- Canonical field vocabulary ---------------------------------------------


class FieldDefinition(BaseModel):
    classification: Literal["immutable", "contextual"]
    value_kind: Literal["text", "dimension", "color", "number", "list"]


# Immutable: physical product attributes - shape, dimensions, capacity,
# materials, colours, labels, branding, packaging. Contextual: creative
# information expected to vary between creatives - camera angle,
# composition, lighting, background, props, marketing/emotional framing.
#
# Deliberately not derived automatically from classification alone (e.g.
# "immutable always prefers URL evidence") as a separate stored field
# here - with exactly two evidence categories today (URL-sourced,
# vision-sourced), that preference IS the classification; see Phase 5.5's
# merge service for the one-line rule this collapses to. Storing it
# redundantly per field would just be vocabulary bloat revision #5 exists
# to avoid.
CANONICAL_FIELD_VOCABULARY: dict[str, FieldDefinition] = {
    # Immutable - physical product attributes.
    "brand": FieldDefinition(classification="immutable", value_kind="text"),
    "product_category": FieldDefinition(classification="immutable", value_kind="text"),
    "shape": FieldDefinition(classification="immutable", value_kind="text"),
    "dimensions": FieldDefinition(classification="immutable", value_kind="dimension"),
    "capacity": FieldDefinition(classification="immutable", value_kind="number"),
    "materials": FieldDefinition(classification="immutable", value_kind="list"),
    "color": FieldDefinition(classification="immutable", value_kind="color"),
    "branding_text": FieldDefinition(classification="immutable", value_kind="list"),
    "packaging": FieldDefinition(classification="immutable", value_kind="text"),
    # Contextual - creative information expected to vary between creatives.
    "camera_angle": FieldDefinition(classification="contextual", value_kind="text"),
    "composition": FieldDefinition(classification="contextual", value_kind="text"),
    "lighting": FieldDefinition(classification="contextual", value_kind="text"),
    "background": FieldDefinition(classification="contextual", value_kind="text"),
    "props": FieldDefinition(classification="contextual", value_kind="list"),
    "marketing_context": FieldDefinition(classification="contextual", value_kind="text"),
}


def validate_attribute_value(field_name: str, value: ProductAttributeValue) -> None:
    """
    Raises ValueError if `value`'s shape doesn't match what
    CANONICAL_FIELD_VOCABULARY declares for `field_name`, or if
    `field_name` isn't in the vocabulary at all. Adapters call this
    (indirectly, via NormalizedAttribute construction below) so a
    mismatch is caught at normalization time, not silently accepted.
    """
    definition = CANONICAL_FIELD_VOCABULARY.get(field_name)
    if definition is None:
        known = ", ".join(sorted(CANONICAL_FIELD_VOCABULARY))
        raise ValueError(f"'{field_name}' is not a canonical field. Known fields: {known}")
    expected_type = _VALUE_KIND_TO_TYPE[definition.value_kind]
    if not isinstance(value, expected_type):
        raise ValueError(
            f"Field '{field_name}' expects a {definition.value_kind} value "
            f"({expected_type.__name__}), got {type(value).__name__}"
        )


# --- Normalized evidence shape ----------------------------------------------


class NormalizedAttribute(BaseModel):
    value: ProductAttributeValue
    confidence: float = Field(ge=0.0, le=1.0)


class NormalizedProductImage(BaseModel):
    """
    Adapters report image URLs found on the page, not raw bytes -
    downloading is the importing service's job (Phase 5.3's
    import_product_source), keeping extract() a pure "fetch + parse"
    contract without every adapter re-implementing image-fetching.
    """

    url: str
    role: str = "gallery"  # e.g. "primary", "gallery"


class NormalizedProductEvidence(BaseModel):
    source_type: str
    source_url: str
    title: str | None = None
    brand: str | None = None
    images: list[NormalizedProductImage] = Field(default_factory=list)
    attributes: dict[str, NormalizedAttribute] = Field(default_factory=dict)
    # Loosely typed for v1 - not over-specified before real adapters
    # exist to validate the shape against (see MIGRATION_PLAN.md).
    variants: list[dict] = Field(default_factory=list)


class ProductSourceExtraction(BaseModel):
    """
    extract()'s return type. Bundles the raw fetch result alongside the
    normalized evidence - discovered as a real gap while implementing
    5.3, not anticipated when this Protocol was first sketched:
    ProductSourceImport.raw_response_json (Phase 5.1) needs "whatever the
    adapter's underlying fetch literally returned," and extract() only
    returning NormalizedProductEvidence would force the caller to fetch
    the URL a second time (or the adapter to expose its raw result some
    other way) just to populate that column. Bundling both in one return
    value means each URL is fetched exactly once.
    """

    raw: dict
    normalized: NormalizedProductEvidence


# --- Adapter protocol --------------------------------------------------------


class ProductSourceAdapter(Protocol):
    def matches(self, url: str) -> bool:
        """Can this adapter handle this URL? The generic fallback always returns True."""
        ...

    def extract(self, url: str) -> ProductSourceExtraction:
        """
        Fetch and normalize. Raises on failure (network error, unparseable
        response) - the caller (Phase 5.3's import_product_source) is
        responsible for catching this and recording a failed
        ProductSourceImport, not the adapter itself.
        """
        ...
