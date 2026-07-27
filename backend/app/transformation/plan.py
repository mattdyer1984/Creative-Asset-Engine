"""
Transformation Plan — the single source of truth for generation and validation.

A DECISION model, not an analysis model. It contains only what generation and
validation must NOT be allowed to guess.

Per element:
    - what must survive?          (must_survive)
    - what should improve?        (should_improve)
    - how commercially important? (commercial_importance)

Slideshow-level rules/properties (count, distinctness, price-anchor, no-CTA)
live in `invariants`, which validation checks — they are not element survival
requirements.

Each slide also carries an executable `SceneDirective`: the minimum visual
decision generation needs so the adapter never guesses the scene.

`Provenance` records which analysis artefact produced each decision (dev-time).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional
import json

PLAN_SCHEMA_VERSION = "0.2.0-slice"

# closed vocabularies (small, extensible by governance)
MUST_SURVIVE = {"identity", "exact_text", "meaning", "presence"}
SHOULD_IMPROVE = {"environment", "lighting", "composition", "styling", "framing", "modernise"}
COMMERCIAL_IMPORTANCE = {"none", "low", "medium", "high", "critical"}
ELEMENT_KINDS = {"product", "text", "object"}

# text: how confident/canonical is the copy? (point 2)
TEXT_STATUS = {"trusted_exact", "exact_commercial_value", "meaning_preserve", "uncertain"}
# text: who renders it? composite_layer & interface_renderer are deterministic
# restore mechanisms; provider_scene means the image model draws it (e.g. on a product). (point 3)
RENDERING_OWNER = {"composite_layer", "interface_renderer", "provider_scene"}
# product identity: how is it preserved? (point 3)
#   product_reference  — regenerate from trusted reference images + identity constraint (default; keeps originality)
#   identity_constraint — textual identity constraint only
#   source_pixels      — literally keep source pixels (last resort; works AGAINST originality)
PRESERVATION_MODE = {"product_reference", "identity_constraint", "source_pixels"}

CommercialValue = dict  # {"type": "discount_pct"|"price"|"price_final", "value": str, "raw": str}
BBox = list             # [x_min, y_min, x_max, y_max], each 0..1


@dataclass
class Provenance:
    decision: str
    source: str
    detail: str = ""


@dataclass
class PlanElement:
    element_id: str
    kind: str
    label: str
    must_survive: list[str] = field(default_factory=list)
    should_improve: list[str] = field(default_factory=list)
    commercial_importance: str = "none"
    verbatim: Optional[str] = None
    # text-specific
    text_status: Optional[str] = None
    commercial_values: list[CommercialValue] = field(default_factory=list)
    rendering_owner: Optional[str] = None
    reserved_zone: Optional[BBox] = None
    # product-specific
    preservation_mode: Optional[str] = None
    reference_ids: list[str] = field(default_factory=list)
    provenance: list[Provenance] = field(default_factory=list)


@dataclass
class SceneDirective:
    """The minimum executable visual decision for a slide (adapter reads this, never guesses)."""
    concept: str = ""
    subject_present: bool = False
    subject_action: Optional[str] = None
    subject_emotion: list[str] = field(default_factory=list)
    environment: str = ""
    lighting: str = ""
    framing: str = ""
    text_safe_zones: list[BBox] = field(default_factory=list)
    references_provided: list[str] = field(default_factory=list)   # e.g. "product_reference:<id>"
    change_directives: list[str] = field(default_factory=list)     # concrete originality levers
    gaps: list[str] = field(default_factory=list)                  # essential info analysis did NOT provide
    provenance: list[Provenance] = field(default_factory=list)


@dataclass
class SlideDirective:
    slide_index: int
    role: str
    promoted_product_allowed: bool
    cta_allowed: bool
    scene: SceneDirective = field(default_factory=SceneDirective)
    required_text_element_ids: list[str] = field(default_factory=list)
    elements: list[PlanElement] = field(default_factory=list)
    originality_levers_required: int = 3
    provenance: list[Provenance] = field(default_factory=list)


@dataclass
class Invariant:
    name: str
    scope: str
    spec: dict = field(default_factory=dict)
    provenance: list[Provenance] = field(default_factory=list)


@dataclass
class TransformationPlan:
    slideshow_id: str
    plan_version: int
    processing_mode: str
    mechanisms_to_preserve: list[str]
    slides: list[SlideDirective]
    invariants: list[Invariant]
    schema_version: str = PLAN_SCHEMA_VERSION

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def element_index(self) -> dict[str, PlanElement]:
        return {e.element_id: e for s in self.slides for e in s.elements}
