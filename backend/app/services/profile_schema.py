"""
Creative Project Profile schemas (ADR 0001 §14, WP-1.1).

**Independent visual roles, deliberately not collapsed.** The WP-1.4 gate
proved this the hard way: a block carried one colour, so bullet markers
inherited the text colour and rendered black where benchmark 4 has red. That
single conflation visibly flattened the hierarchy. Markers, rules, dividers,
italic emphasis, strokes, shadows and containers each get their own role map
and must stay that way.

**Machine analysis and user decisions never share a field.** `analysed_*`
holds what the analyser inferred; `user_*` holds what a human decided.
Re-analysis overwrites the former and must never touch the latter - a user
who set the overlay policy to `remove` should not find it silently restored
because the slideshow was re-analysed. Merging them into one JSON blob would
make that guarantee unenforceable, which is why they are separate columns.

**Schema-versioned.** `SCHEMA_VERSION` is stamped on every persisted profile
and validated on load, so a profile written by an older build is detected
rather than silently misread.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Bumped whenever the persisted shape changes incompatibly.
SCHEMA_VERSION = "1.0"


class TextMode(StrEnum):
    DESIGNED_TYPOGRAPHY = "designed_typography"
    PLATFORM_CAPTION = "platform_caption"


class CopyPolicy(StrEnum):
    PRESERVE_VERBATIM = "preserve_verbatim"
    PRESERVE_MEANING = "preserve_meaning"
    USER_REPLACEMENT = "user_replacement"


class OverlayPolicy(StrEnum):
    KEEP = "keep"
    REMOVE = "remove"
    REPLACE = "replace"
    REVIEW_INDIVIDUALLY = "review_individually"


class ProductionValueStrategy(StrEnum):
    MATCH = "match"
    REFINE = "refine"
    ELEVATE = "elevate"


class FamilyClass(StrEnum):
    SERIF = "serif"
    GROTESQUE = "grotesque"
    GEOMETRIC_SANS = "geometric-sans"
    CONDENSED_SANS = "condensed-sans"
    SLAB = "slab"
    SCRIPT = "script"
    DISPLAY = "display"


class CapabilityLevel(StrEnum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class TextRole(BaseModel):
    """How one named text role is set. Keyed by role: headline, body, label…"""

    model_config = ConfigDict(extra="forbid")

    family_class: FamilyClass = FamilyClass.GROTESQUE
    weight: str = "regular"
    italic: bool = False
    case: str = "as-written"
    colour_role: str = "near-black"
    alignment: str = "left"
    size_ratio: float = Field(default=1.0, gt=0)
    tracking: float = 0.0
    line_height: float = Field(default=1.18, gt=0)

    @field_validator("weight")
    @classmethod
    def _weight(cls, value: str) -> str:
        if value not in {"regular", "bold"}:
            raise ValueError("weight must be 'regular' or 'bold'")
        return value

    @field_validator("case")
    @classmethod
    def _case(cls, value: str) -> str:
        if value not in {"as-written", "upper", "lower"}:
            raise ValueError("case must be as-written, upper or lower")
        return value

    @field_validator("alignment")
    @classmethod
    def _alignment(cls, value: str) -> str:
        if value not in {"left", "centre", "right"}:
            raise ValueError("alignment must be left, centre or right")
        return value


class MarkerRole(BaseModel):
    """
    A bullet or list marker. Independent of the text it precedes: benchmark 4
    has red markers against near-black copy, and the gate render proved that
    inheriting the text colour flattens the hierarchy.
    """

    model_config = ConfigDict(extra="forbid")

    glyph: str = "•"
    colour_role: str = "near-black"
    size_ratio: float = Field(default=1.0, gt=0)
    gap_ratio: float = Field(default=0.4, ge=0)


class RuleRole(BaseModel):
    """A short rule under a heading - benchmark 4's red underrule."""

    model_config = ConfigDict(extra="forbid")

    colour_role: str = "near-black"
    width_ratio: float = Field(default=0.42, gt=0, le=1.0)
    thickness_ratio: float = Field(default=0.045, gt=0)
    gap_ratio: float = Field(default=0.10, ge=0)


class DividerRole(BaseModel):
    """A separating line between regions - benchmark 7's face divider."""

    model_config = ConfigDict(extra="forbid")

    colour_role: str = "white"
    orientation: str = "vertical"
    thickness_ratio: float = Field(default=0.004, gt=0)

    @field_validator("orientation")
    @classmethod
    def _orientation(cls, value: str) -> str:
        if value not in {"vertical", "horizontal"}:
            raise ValueError("orientation must be vertical or horizontal")
        return value


class StrokeRole(BaseModel):
    """L2. The caption outline - never applied to designed typography."""

    model_config = ConfigDict(extra="forbid")

    colour_role: str = "near-black"
    width_ratio: float = Field(default=0.03, gt=0)


class ShadowRole(BaseModel):
    """L2."""

    model_config = ConfigDict(extra="forbid")

    colour_role: str = "near-black"
    offset_ratio: float = Field(default=0.04, ge=0)
    blur_ratio: float = Field(default=0.0, ge=0)


class ContainerRole(BaseModel):
    """L2. The rounded box behind a platform caption."""

    model_config = ConfigDict(extra="forbid")

    fill_colour_role: str = "white"
    corner_ratio: float = Field(default=0.35, ge=0)
    padding_ratio: float = Field(default=0.25, ge=0)


class TypographySystem(BaseModel):
    """
    ADR 0001 §10. Every role family is its own map, keyed by role name, so a
    change to markers cannot silently move the body text and vice versa.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    primary_family_class: FamilyClass = FamilyClass.GROTESQUE
    secondary_family_class: FamilyClass | None = None
    capability_level: CapabilityLevel = CapabilityLevel.L1
    base_size_ratio: float = Field(default=0.045, gt=0)

    #: role name -> named colour, e.g. {"accent": "dark-red"}
    colour_roles: dict[str, str] = Field(default_factory=dict)

    text_roles: dict[str, TextRole] = Field(default_factory=dict)
    marker_roles: dict[str, MarkerRole] = Field(default_factory=dict)
    rule_roles: dict[str, RuleRole] = Field(default_factory=dict)
    divider_roles: dict[str, DividerRole] = Field(default_factory=dict)
    italic_roles: dict[str, TextRole] = Field(default_factory=dict)
    stroke_roles: dict[str, StrokeRole] = Field(default_factory=dict)
    shadow_roles: dict[str, ShadowRole] = Field(default_factory=dict)
    container_roles: dict[str, ContainerRole] = Field(default_factory=dict)

    #: Free-form but validated shape: {"headline_to_body": 2.9}
    size_scale: dict[str, float] = Field(default_factory=dict)
    case_rules: list[str] = Field(default_factory=list)
    weight_hierarchy: list[str] = Field(default_factory=list)


class BlockClassificationEvidence(BaseModel):
    """Why the analyser classified one block as it did - shown on review."""

    model_config = ConfigDict(extra="forbid")

    text: str
    text_class: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    needs_review: bool = False


class ClassificationEvidence(BaseModel):
    """The analyser's working, kept so a human can audit a decision."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    blocks: list[BlockClassificationEvidence] = Field(default_factory=list)
    project_mode_reasons: list[str] = Field(default_factory=list)


class UserTypographyOverrides(BaseModel):
    """
    Deliberate human corrections to the analysed typography.

    Sparse by design: only what the user actually changed. An empty override
    set means "no human has expressed an opinion", which is different from
    "the human agreed with the analyser".
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    text_roles: dict[str, TextRole] = Field(default_factory=dict)
    marker_roles: dict[str, MarkerRole] = Field(default_factory=dict)
    rule_roles: dict[str, RuleRole] = Field(default_factory=dict)
    divider_roles: dict[str, DividerRole] = Field(default_factory=dict)
    colour_roles: dict[str, str] = Field(default_factory=dict)
    primary_family_class: FamilyClass | None = None
    secondary_family_class: FamilyClass | None = None
    base_size_ratio: float | None = Field(default=None, gt=0)


def merge_typography(
    analysed: TypographySystem, overrides: UserTypographyOverrides | None
) -> TypographySystem:
    """
    The effective system: analysis with human corrections laid over it.

    Per-role rather than wholesale, so overriding one marker does not discard
    the analyser's work on every other role. Neither input is mutated - the
    analysed system must remain intact for re-analysis comparison and for the
    UI to show what was changed and why.
    """
    if overrides is None:
        return analysed.model_copy(deep=True)

    merged = analysed.model_copy(deep=True)
    if overrides.primary_family_class is not None:
        merged.primary_family_class = overrides.primary_family_class
    if overrides.secondary_family_class is not None:
        merged.secondary_family_class = overrides.secondary_family_class
    if overrides.base_size_ratio is not None:
        merged.base_size_ratio = overrides.base_size_ratio

    merged.colour_roles = {**merged.colour_roles, **overrides.colour_roles}
    merged.text_roles = {**merged.text_roles, **overrides.text_roles}
    merged.marker_roles = {**merged.marker_roles, **overrides.marker_roles}
    merged.rule_roles = {**merged.rule_roles, **overrides.rule_roles}
    merged.divider_roles = {**merged.divider_roles, **overrides.divider_roles}
    return merged
