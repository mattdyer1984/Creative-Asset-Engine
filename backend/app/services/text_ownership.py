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

from app.services.profile_schema import SCHEMA_VERSION, OverlayPolicy, TextMode
from app.services.text_classification import (
    AUTO_OVERRIDE_CONFIDENCE,
    REVIEW_CONFIDENCE,
    TextClass,
    classify_block,
)


class Owner(StrEnum):
    IMAGE_GENERATION = "image_generation"
    PRODUCT_LOCK = "product_lock"
    DETERMINISTIC_TYPOGRAPHY = "deterministic_typography"
    CAPTION_RENDERER = "caption_renderer"
    HUMAN_REVIEW = "human_review"


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


#: Owners that place text into the base image during generation. A block owned
#: by one of these must NOT also be drawn by a renderer afterwards.
IMAGE_OWNED = frozenset({Owner.IMAGE_GENERATION, Owner.PRODUCT_LOCK})

#: Owners that draw text after generation, deterministically.
RENDERER_OWNED = frozenset({Owner.DETERMINISTIC_TYPOGRAPHY, Owner.CAPTION_RENDERER})

_OWNER_FOR_CLASS = {
    TextClass.DESIGNED_TYPOGRAPHY: Owner.DETERMINISTIC_TYPOGRAPHY,
    TextClass.PLATFORM_CAPTION: Owner.CAPTION_RENDERER,
    TextClass.PRODUCT_NATIVE: Owner.PRODUCT_LOCK,
    TextClass.ENVIRONMENTAL: Owner.IMAGE_GENERATION,
}


class TextOwnership(BaseModel):
    """One block's routing decision, with the reasoning that produced it."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    text: str
    text_class: TextClass
    owner: Owner
    handling_policy: HandlingPolicy
    source: DecisionSource
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    #: Normalised [x_min, y_min, x_max, y_max], when OCR gave us one.
    bounds: tuple[float, float, float, float] | None = None

    @property
    def is_image_owned(self) -> bool:
        return self.owner in IMAGE_OWNED

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
        return [d for d in self.decisions if d.owner is Owner.HUMAN_REVIEW]

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


def decide_ownership(
    blocks: list[dict] | None,
    *,
    overlay_policy: OverlayPolicy = OverlayPolicy.KEEP,
    project_text_mode: TextMode | None = None,
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

        # No signals at all: take the project's default interpretation. This
        # is a documented fallback, not an uncertain judgement.
        if not contested and text_class is not TextClass.PRODUCT_NATIVE:
            if project_text_mode is TextMode.PLATFORM_CAPTION:
                text_class = TextClass.PLATFORM_CAPTION
            elif project_text_mode is TextMode.DESIGNED_TYPOGRAPHY:
                text_class = TextClass.DESIGNED_TYPOGRAPHY

        # Contested blocks are preserved and surfaced, never silently routed.
        if (
            contested
            and classification.confidence < REVIEW_CONFIDENCE
            and text_class is not TextClass.PRODUCT_NATIVE
        ):
            decisions.append(
                TextOwnership(
                    block_id=f"block-{index}", text=text, text_class=text_class,
                    owner=Owner.HUMAN_REVIEW,
                    handling_policy=HandlingPolicy.REVIEW_REQUIRED,
                    source=DecisionSource.PROJECT_DEFAULT,
                    confidence=classification.confidence,
                    reason=(
                        "confidence below the review band - preserved pending review "
                        f"({'; '.join(classification.reasons[:2]) or 'no signals'})"
                    ),
                    bounds=_bounds_of(block),
                )
            )
            continue

        owner = _OWNER_FOR_CLASS[text_class]

        if text_class is TextClass.PLATFORM_CAPTION:
            policy = HandlingPolicy.OPTIONAL_OVERLAY
            if overlay_policy is OverlayPolicy.REPLACE:
                policy = HandlingPolicy.USER_REPLACEMENT
            elif overlay_policy is OverlayPolicy.REVIEW_INDIVIDUALLY:
                owner, policy = Owner.HUMAN_REVIEW, HandlingPolicy.REVIEW_REQUIRED
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
                block_id=f"block-{index}", text=text, text_class=text_class, owner=owner,
                handling_policy=policy, source=source,
                confidence=classification.confidence,
                reason=(
                    "; ".join(classification.reasons[:3])
                    or f"no block signals - project default ({project_text_mode})"
                ),
                bounds=_bounds_of(block),
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
