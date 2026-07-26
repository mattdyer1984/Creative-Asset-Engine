"""
Composition Contract (ADR 0001 §9, Package B).

The intermediate abstraction between "preserve pixels" (too rigid - the
benchmarks move the camera and reorder panels) and "preserve the device" (too
loose - it permits losing the price label or the spine overlay).

**Required to complete ownership, not merely the next phase.** WP-1.5A could
not determine *this text belongs to this product* and WP-1.5B could not
determine *where a graphic element will be drawn*; both are spatial-
relationship problems, and both are answered here.

Closed vocabularies throughout. Nine relation types express all eight
benchmarks. A general-purpose graph was deliberately rejected: it is hard to
validate, hard to prompt from, and invites expressing things we cannot check.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "1.0"


class Device(StrEnum):
    SPLIT_COMPARISON = "split-comparison"
    GRID_COLLAGE = "grid-collage"
    SIDE_BY_SIDE_COMPARISON = "side-by-side-comparison"
    PRODUCT_HERO = "product-hero"
    SCENE_WITH_CAPTION = "scene-with-caption"
    SHELF_SNAPSHOT = "shelf-snapshot"
    DIAGRAM_WITH_CALLOUT = "diagram-with-callout"
    SCREEN_IN_SCENE = "screen-in-scene"
    #: Honest when the evidence does not support a device. Never a default
    #: dressed up as a finding.
    UNKNOWN = "unknown"


class ZoneRole(StrEnum):
    TEXT = "text"
    CAPTION = "caption"
    SUBJECT = "subject"
    PRODUCT = "product"
    CALLOUT = "callout"
    NEGATIVE_SPACE = "negative-space"
    SCREEN = "screen"
    PRICE = "price"
    GRAPHIC = "graphic"


class Relation(StrEnum):
    ABOVE = "above"
    BELOW = "below"
    LEFT_OF = "left-of"
    RIGHT_OF = "right-of"
    ATTACHED_TO = "attached-to"
    POINTS_TO = "points-to"
    SPLITS = "splits"
    FLANKS = "flanks"
    CONTAINS = "contains"


class Zone(BaseModel):
    """A named region with a role. Bounds are normalised."""

    model_config = ConfigDict(extra="forbid")

    zone_id: str
    role: ZoneRole
    bounds: tuple[float, float, float, float]

    @field_validator("bounds")
    @classmethod
    def _bounds(cls, value):
        if not all(0.0 <= v <= 1.0 for v in value):
            raise ValueError("zone bounds are normalised to 0..1")
        if value[0] >= value[2] or value[1] >= value[3]:
            raise ValueError("zone bounds must be non-empty")
        return value

    def contains_point(self, x: float, y: float) -> bool:
        return self.bounds[0] <= x <= self.bounds[2] and self.bounds[1] <= y <= self.bounds[3]

    def overlap_fraction(self, other: tuple[float, float, float, float]) -> float:
        """How much of `other` falls inside this zone."""
        left = max(self.bounds[0], other[0])
        top = max(self.bounds[1], other[1])
        right = min(self.bounds[2], other[2])
        bottom = min(self.bounds[3], other[3])
        if right <= left or bottom <= top:
            return 0.0
        area = (other[2] - other[0]) * (other[3] - other[1])
        return ((right - left) * (bottom - top)) / area if area else 0.0


class RelationEdge(BaseModel):
    """
    subject -> relation -> object, over ZONE IDS.

    Endpoints must name declared zones. An earlier revision allowed free
    element names, which quietly reopened the escape hatch the closed
    vocabularies were meant to shut: `[shelf, contains, product]` reads as
    structure but nothing can resolve `shelf`, so no stage could act on it.
    A relation whose endpoints are not zones is narration, not a contract.
    """

    model_config = ConfigDict(extra="forbid")

    subject: str
    relation: Relation
    object: str


class CompositionContract(BaseModel):
    """ADR 0001 §9."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    device: Device = Device.UNKNOWN
    device_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    zones: list[Zone] = Field(default_factory=list)
    relations: list[RelationEdge] = Field(default_factory=list)
    #: Ordered: what the eye reaches first, second, third.
    emphasis: list[str] = Field(default_factory=list)

    @property
    def is_confident(self) -> bool:
        return self.device is not Device.UNKNOWN and self.device_confidence >= 0.5

    def zones_with_role(self, role: ZoneRole) -> list[Zone]:
        return [z for z in self.zones if z.role is role]

    def zone_for(self, bounds: tuple[float, float, float, float], *, minimum: float = 0.5):
        """
        The zone a region mostly sits in, or None.

        Used by ownership to answer questions OCR cannot: is this text inside
        a screen, attached to a product, or part of the designed text column?

        The MOST SPECIFIC containing zone wins, not the first one found.
        Zones nest legitimately - a label sits inside a product, a product
        sits inside a shelf - and both contain the text completely, so raw
        overlap cannot separate them. Taking the smallest is what makes
        "which product is this price attached to?" answerable at all; taking
        the first would let a full-canvas subject zone swallow everything.
        """
        candidates = [
            zone for zone in self.zones if zone.overlap_fraction(bounds) > minimum
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda z: (z.bounds[2] - z.bounds[0]) * (z.bounds[3] - z.bounds[1]))

    def related(self, subject: str, relation: Relation) -> list[str]:
        return [e.object for e in self.relations if e.subject == subject and e.relation is relation]

    def neighbours(self, zone_id: str) -> list[str]:
        """
        Every zone this one is related to, in either direction.

        Relations are recorded from whichever end read most naturally to the
        annotator - `price-label below product` and `product above price-label`
        are the same fact. Callers asking "what is this associated with?" must
        not have to know which way round it was written.
        """
        found = {
            e.object if e.subject == zone_id else e.subject
            for e in self.relations
            if zone_id in (e.subject, e.object)
        }
        return sorted(found - {zone_id})

    def unresolved_relations(self) -> list[RelationEdge]:
        """Edges naming something that is not a declared zone."""
        ids = {z.zone_id for z in self.zones}
        return [e for e in self.relations if e.subject not in ids or e.object not in ids]
