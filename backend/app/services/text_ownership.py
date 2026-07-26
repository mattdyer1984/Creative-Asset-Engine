"""
Text ownership (ADR 0001 WP-1.5A).

**One inspectable answer to "who is responsible for rendering this text?"**

Routing used to be implicit - scattered conditionals deciding, in effect,
whether a block got composited or left to the model. That is how a block
ended up owned twice: the model rendered the caption because it was in the
reference image, and the Rendering Engine composited it again on top, and
nothing in the system could state which path was supposed to own it.

So ownership is an explicit decision object, recorded per block, carried into
the render manifest, and asserted on. Duplication becomes a property that can
be checked rather than a defect that has to be spotted.

Routing (ADR §4, §6):

    designed_typography  -> deterministic_typography   L1 renderer
    platform_caption     -> caption_renderer           respects overlay policy
    product_native       -> product_lock                stays with the object
    environmental        -> image_generation            stays in the scene

`human_review` is a real destination, not an error path: an uncertain block is
preserved and surfaced (ADR D7), because keeping removable text is
recoverable and removing keepable text is not.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.services.profile_schema import (
    SCHEMA_VERSION,
    CapabilityLevel,
    OverlayPolicy,
    TextMode,
)
from app.services.text_classification import (
    AUTO_OVERRIDE_CONFIDENCE,
    REVIEW_CONFIDENCE,
    TextClass,
    classify_block,
)


class Owner(StrEnum):
    """
    WHO is responsible for this text appearing.

    Four owners, deliberately. An earlier version had `image_generation` and
    `product_lock` as separate owners, which was a category error: both mean
    "the image carries this text". Keeping them apart would have forced a new
    owner for every future production method - reference_image, inpainting,
    product_reference - when they are all one ownership domain answering to
    one question. HOW the image comes to carry it is `ImageStrategy`.
    """

    IMAGE = "image"
    TYPOGRAPHY = "typography"
    CAPTION = "caption"
    REVIEW = "review"


class ImageStrategy(StrEnum):
    """
    HOW the image owner will produce the text. Only meaningful for Owner.IMAGE.

    Separating this from ownership is what keeps the owner vocabulary stable
    while production methods multiply.
    """

    REFERENCE_CONDITIONED = "reference_conditioned"
    PRODUCT_LOCK = "product_lock"
    GENERATED = "generated"
    INPAINTED = "inpainted"
    HYBRID = "hybrid"


class HandlingPolicy(StrEnum):
    PRESERVE_VERBATIM = "preserve_verbatim"
    PRESERVE_VISUAL_ROLE = "preserve_visual_role"
    OPTIONAL_OVERLAY = "optional_overlay"
    USER_REPLACEMENT = "user_replacement"
    REVIEW_REQUIRED = "review_required"


class DecisionSource(StrEnum):
    PROJECT_DEFAULT = "project_default"
    BLOCK_OVERRIDE = "block_override"
    USER_DECISION = "user_decision"


#: Owners that draw text after generation, deterministically. A block owned
#: by one of these must NOT also be produced by the image.
RENDERER_OWNED = frozenset({Owner.TYPOGRAPHY, Owner.CAPTION})

_ROUTING: dict[TextClass, tuple[Owner, "ImageStrategy | None"]] = {
    TextClass.DESIGNED_TYPOGRAPHY: (Owner.TYPOGRAPHY, None),
    TextClass.PLATFORM_CAPTION: (Owner.CAPTION, None),
    TextClass.PRODUCT_NATIVE: (Owner.IMAGE, ImageStrategy.PRODUCT_LOCK),
    TextClass.ENVIRONMENTAL: (Owner.IMAGE, ImageStrategy.GENERATED),
}


class TextOwnership(BaseModel):
    """One block's routing decision, with the reasoning that produced it."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    #: The OCR block this decision came from, so a persisted artifact can be
    #: traced back to the recognition that produced it.
    source_ocr_block_id: str | None = None
    text: str
    text_class: TextClass
    owner: Owner
    handling_policy: HandlingPolicy
    source: DecisionSource
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    #: The classifier's working, kept for review rather than summarised away.
    evidence: list[str] = Field(default_factory=list)
    #: How the image will produce it. Only set when owner is IMAGE.
    image_strategy: ImageStrategy | None = None
    #: Normalised [x_min, y_min, x_max, y_max], when OCR gave us one.
    bounds: tuple[float, float, float, float] | None = None

    #: Package C. The composition zone this block sits in, and what that zone
    #: is related to. Recorded even when it did not change the decision, so a
    #: reviewer can see what the geometry said as well as what routing did.
    composition_zone_id: str | None = None
    composition_zone_role: str | None = None
    #: Zones this block's zone is related to (`price attached-to product`).
    #: This is what makes "the price belongs to THAT product" durable rather
    #: than an inference redone differently by every later stage.
    associated_zone_ids: list[str] = Field(default_factory=list)

    @property
    def is_image_owned(self) -> bool:
        return self.owner is Owner.IMAGE

    @property
    def is_renderer_owned(self) -> bool:
        return self.owner in RENDERER_OWNED


class OwnershipPlan(BaseModel):
    """Every block's decision for one slide, plus what the model must avoid."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    decisions: list[TextOwnership] = Field(default_factory=list)

    @property
    def renderer_owned(self) -> list[TextOwnership]:
        return [d for d in self.decisions if d.is_renderer_owned]

    @property
    def image_owned(self) -> list[TextOwnership]:
        return [d for d in self.decisions if d.is_image_owned]

    @property
    def needs_review(self) -> list[TextOwnership]:
        return [d for d in self.decisions if d.owner is Owner.REVIEW]

    def texts_the_model_must_not_render(self) -> list[str]:
        """
        Copy the generator must leave out because a renderer will place it.

        This is the pre-generation half of the no-duplication rule: checking
        afterwards only tells you it went wrong, whereas instructing the model
        up front is what stops it.
        """
        return [d.text for d in self.renderer_owned if d.text.strip()]


def _bounds_of(block: dict) -> tuple[float, float, float, float] | None:
    box = block.get("bounding_box") or {}
    try:
        return (
            float(box["x_min"]), float(box["y_min"]),
            float(box["x_max"]), float(box["y_max"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


#: Zone roles that establish what a block is ATTACHED TO, which the wording
#: cannot. A price under a product is environmental scene text, not the
#: product's own packaging; text inside a screen belongs to the screen.
_SPATIAL_CLASS: dict[str, TextClass] = {
    "product": TextClass.PRODUCT_NATIVE,
    "screen": TextClass.ENVIRONMENTAL,
    "price": TextClass.ENVIRONMENTAL,
    "caption": TextClass.PLATFORM_CAPTION,
    "graphic": TextClass.DESIGNED_TYPOGRAPHY,
}

#: Roles that declare what a block is PART OF, which outranks how it reads.
#: A block inside a product or a screen is attached to it whatever it says,
#: and a rule under a heading has no wording for the classifier to read at
#: all - position is the only evidence there is.
#:
#: `text` and `caption` zones are deliberately absent: designed copy and
#: platform captions genuinely share regions, so there the wording still
#: gets to speak and a disagreement is a real contest, not noise.
_SPATIAL_OVERRIDES_WORDING = frozenset({"product", "screen", "price", "graphic"})


class SpatialEvidence(BaseModel):
    """What the Composition Contract says about one block's position."""

    model_config = ConfigDict(extra="forbid")

    zone_id: str | None = None
    zone_role: str | None = None
    text_class: TextClass | None = None
    associated_zone_ids: list[str] = Field(default_factory=list)

    @property
    def overrides_wording(self) -> bool:
        return self.zone_role in _SPATIAL_OVERRIDES_WORDING


def _spatial_evidence(contract, bounds) -> SpatialEvidence:
    """
    What the composition says this block is attached to.

    This is the capability WP-1.5A lacked. You cannot determine *this text
    belongs to this product* from wording, and a shelf price reads like
    neither a caption nor packaging - it is scene text that happens to be
    about a product, and only its position says so.

    Relations are carried through as well as the zone: knowing the price is
    `attached-to` a specific product zone is what lets a later stage keep them
    together, instead of each stage re-guessing the association from geometry.
    """
    if contract is None or bounds is None:
        return SpatialEvidence()
    zone = contract.zone_for(bounds)
    if zone is None:
        return SpatialEvidence()
    role = str(zone.role)
    return SpatialEvidence(
        zone_id=zone.zone_id,
        zone_role=role,
        text_class=_SPATIAL_CLASS.get(role),
        associated_zone_ids=contract.neighbours(zone.zone_id),
    )


#: What the deterministic renderer can actually produce today. Designed
#: typography above this level is routed to the image instead: the renderer
#: would draw flat type where the source had it outlined, wrapped or occluded,
#: and a flat recreation of integrated typography is worse than letting the
#: model attempt it. Raise this as the renderer gains capability - the routing
#: is then a configuration change, not a code change.
RENDERER_CAPABILITY = CapabilityLevel.L1

_CAPABILITY_ORDER = {CapabilityLevel.L1: 1, CapabilityLevel.L2: 2, CapabilityLevel.L3: 3}


def exceeds_renderer(level: CapabilityLevel | None) -> bool:
    if level is None:
        return False
    return _CAPABILITY_ORDER[level] > _CAPABILITY_ORDER[RENDERER_CAPABILITY]


def decide_ownership(
    blocks: list[dict] | None,
    *,
    overlay_policy: OverlayPolicy = OverlayPolicy.KEEP,
    project_text_mode: TextMode | None = None,
    contract=None,
    capability_level: CapabilityLevel | None = None,
) -> OwnershipPlan:
    """
    Route every OCR block to exactly one owner.

    `project_text_mode` is the project's DEFAULT interpretation (ADR §12.1).
    A block with no distinguishing signals of its own takes it rather than
    going to review - benchmark 4's bullets ("You struggle to straighten up")
    fire no pattern at all, and routing every such block to human review
    would flood the queue with text the project already answers for.

    Review is reserved for blocks that are genuinely CONTESTED: signals fired
    and disagreed. Falling through to a documented default is not the same as
    being uncertain, and conflating them makes review meaningless.

    `overlay_policy` only ever affects captions - it is the user's control
    over their own post, and it must never reach designed typography or
    product-native text, which belong to the creative (ADR §4).
    """
    decisions: list[TextOwnership] = []

    for index, block in enumerate(blocks or []):
        classification = classify_block(block)
        text = (block.get("text") or "").strip()
        text_class = classification.text_class

        contested = bool(classification.reasons) and not any(
            "preserving by default" in reason or "no distinguishing" in reason
            for reason in classification.reasons
        )

        # Composition first, where it speaks. Spatial attachment is stronger
        # evidence than wording for the roles that establish it: a block
        # inside a product zone IS product text, whatever it says.
        spatial = _spatial_evidence(contract, _bounds_of(block))
        spatial_applied = False
        if spatial.text_class is not None and (spatial.overrides_wording or not contested):
            if spatial.text_class is not text_class:
                classification.reasons.insert(
                    0, f"composition: block sits in the {spatial.zone_id!r} "
                       f"{spatial.zone_role} zone"
                )
            text_class = spatial.text_class
            spatial_applied = True

        # No signals at all: take the project's default interpretation. This
        # is a documented fallback, not an uncertain judgement.
        if not contested and not spatial_applied and text_class is not TextClass.PRODUCT_NATIVE:
            if project_text_mode is TextMode.PLATFORM_CAPTION:
                text_class = TextClass.PLATFORM_CAPTION
            elif project_text_mode is TextMode.DESIGNED_TYPOGRAPHY:
                text_class = TextClass.DESIGNED_TYPOGRAPHY

        # Contested blocks are preserved and surfaced, never silently routed.
        if (
            contested
            and not spatial_applied
            and classification.confidence < REVIEW_CONFIDENCE
            and text_class is not TextClass.PRODUCT_NATIVE
        ):
            decisions.append(
                TextOwnership(
                    block_id=f"block-{index}",
                    source_ocr_block_id=block.get("id") or f"ocr-{index}",
                    text=text, text_class=text_class, owner=Owner.REVIEW,
                    evidence=list(classification.reasons),
                    handling_policy=HandlingPolicy.REVIEW_REQUIRED,
                    source=DecisionSource.PROJECT_DEFAULT,
                    confidence=classification.confidence,
                    reason=(
                        "confidence below the review band - preserved pending review "
                        f"({'; '.join(classification.reasons[:2]) or 'no signals'})"
                    ),
                    bounds=_bounds_of(block),
                    composition_zone_id=spatial.zone_id,
                    composition_zone_role=spatial.zone_role,
                    associated_zone_ids=spatial.associated_zone_ids,
                )
            )
            continue

        owner, image_strategy = _ROUTING[text_class]

        # Capability gate. Designed typography the renderer cannot reproduce
        # goes to the image rather than being drawn flat - ADR §10.3's L1/L2/L3
        # split reaching ownership, which is where it has to act. Benchmark 5's
        # "10/10 man" is the case: annotated designed typography, but treated
        # as part of the artwork, so L1 would flatten it.
        capability_note = ""
        if text_class is TextClass.DESIGNED_TYPOGRAPHY and exceeds_renderer(capability_level):
            owner, image_strategy = Owner.IMAGE, ImageStrategy.GENERATED
            capability_note = (
                f"typography is {capability_level} and the renderer is "
                f"{RENDERER_CAPABILITY} - left to the image rather than drawn flat"
            )
            classification.reasons.insert(0, capability_note)

        if capability_note:
            policy = HandlingPolicy.PRESERVE_VISUAL_ROLE
        elif text_class is TextClass.PLATFORM_CAPTION:
            policy = HandlingPolicy.OPTIONAL_OVERLAY
            if overlay_policy is OverlayPolicy.REPLACE:
                policy = HandlingPolicy.USER_REPLACEMENT
            elif overlay_policy is OverlayPolicy.REVIEW_INDIVIDUALLY:
                owner, policy = Owner.REVIEW, HandlingPolicy.REVIEW_REQUIRED
        elif text_class is TextClass.DESIGNED_TYPOGRAPHY:
            policy = HandlingPolicy.PRESERVE_VERBATIM
        else:
            # Product-native and environmental text is preserved by staying
            # with the object or the scene - its visual role is what matters,
            # and re-typesetting it would fabricate branded packaging.
            policy = HandlingPolicy.PRESERVE_VISUAL_ROLE

        source = (
            DecisionSource.PROJECT_DEFAULT
            if not contested
            else DecisionSource.BLOCK_OVERRIDE
            if classification.confidence >= AUTO_OVERRIDE_CONFIDENCE
            else DecisionSource.PROJECT_DEFAULT
        )

        decisions.append(
            TextOwnership(
                block_id=f"block-{index}",
                source_ocr_block_id=block.get("id") or f"ocr-{index}",
                text=text, text_class=text_class, owner=owner,
                evidence=list(classification.reasons),
                image_strategy=image_strategy, handling_policy=policy, source=source,
                confidence=classification.confidence,
                reason=(
                    "; ".join(classification.reasons[:3])
                    or f"no block signals - project default ({project_text_mode})"
                ),
                bounds=_bounds_of(block),
                composition_zone_id=spatial.zone_id,
                composition_zone_role=spatial.zone_role,
                associated_zone_ids=spatial.associated_zone_ids,
            )
        )

    return OwnershipPlan(decisions=decisions)


class DuplicateOwnership(RuntimeError):
    """A block routed to more than one owner - the defect this model prevents."""


def assert_single_ownership(plan: OwnershipPlan) -> None:
    """
    ADR §4 acceptance criterion 3: text is never duplicated between
    generation and rendering.

    Checks the structural half - that no block appears twice in the plan.
    Whether the model *also* rendered renderer-owned text despite being told
    not to is a separate, post-generation check.
    """
    seen: dict[str, str] = {}
    for decision in plan.decisions:
        if decision.block_id in seen:
            raise DuplicateOwnership(
                f"{decision.block_id} is owned by both {seen[decision.block_id]} "
                f"and {decision.owner}"
            )
        seen[decision.block_id] = str(decision.owner)

    by_text: dict[str, list[str]] = {}
    for decision in plan.decisions:
        if decision.text.strip():
            by_text.setdefault(decision.text.strip().lower(), []).append(str(decision.owner))
    for text, owners in by_text.items():
        distinct = set(owners)
        if len(distinct) > 1 and distinct & {str(o) for o in RENDERER_OWNED}:
            raise DuplicateOwnership(
                f"text {text[:40]!r} is claimed by multiple owners: {sorted(distinct)}"
            )
