"""
Render manifest (ADR 0001 WP-1.5A).

**Historical outputs must stay explainable after re-analysis.** The manifest
records the profile and typography that were actually used, by id, at the
moment of rendering - not "whatever the newest record happens to be when
somebody looks". A project re-analysed next week must not silently rewrite
the explanation of an image produced today.

It is also the one place that answers, for any block: who owned this, why,
what was drawn, where, in what style, and what warnings were raised. That is
what makes the no-duplication rule checkable rather than merely intended.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.services.profile_schema import SCHEMA_VERSION
from app.services.graphic_ownership import (
    CleanupAction,
    OwnershipAttempt,
    RenderZone,
    ZoneOccupancy,
)
from app.services.text_ownership import OwnershipPlan, TextOwnership

#: Bumped when the renderer's output would change for identical input.
RENDERER_VERSION = "L1-1.0"


class RenderedBlock(BaseModel):
    """A block the deterministic renderer actually drew."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    text: str
    role: str
    bounds: tuple[float, float, float, float]
    font_token: str
    colour_role: str
    owner: str


class SkippedBlock(BaseModel):
    """A block a renderer did NOT draw, and the reason - never silent."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    text: str
    owner: str
    reason: str


class RenderManifest(BaseModel):
    """Everything needed to reproduce and audit one final output."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    renderer_version: str = RENDERER_VERSION

    #: The profile actually used, pinned by id. Never resolved at read time.
    profile_id: str | None = None
    typography_schema_version: str | None = None

    #: token -> the concrete face it resolved to on the rendering host.
    font_token_bindings: dict[str, str] = Field(default_factory=dict)

    #: Every OCR block considered, before routing.
    source_blocks: list[str] = Field(default_factory=list)

    text_ownership_decisions: list[TextOwnership] = Field(default_factory=list)
    rendered_blocks: list[RenderedBlock] = Field(default_factory=list)
    skipped_blocks: list[SkippedBlock] = Field(default_factory=list)
    caption_blocks: list[str] = Field(default_factory=list)
    image_owned_blocks: list[str] = Field(default_factory=list)

    #: The policies in force at render time, already resolved.
    effective_policies: dict[str, str] = Field(default_factory=dict)

    #: WP-1.5B/Package D. The ladder's working, so the manifest debugs rather
    #: than merely records: every rung records why the previous one failed,
    #: what it produced, how that was validated, and what it cost.
    #: The zones an owner claimed, and where each claim came from - a
    #: contract zone or, where the contract was silent, an OCR box.
    render_zones: list[RenderZone] = Field(default_factory=list)
    zone_occupancy: list[ZoneOccupancy] = Field(default_factory=list)
    ownership_attempts: list[OwnershipAttempt] = Field(default_factory=list)
    cleanup_actions: list[CleanupAction] = Field(default_factory=list)

    warnings: list[str] = Field(default_factory=list)

    def accounts_for_every_block(self) -> bool:
        """
        Every source block must appear in exactly one outcome bucket.

        A block that is neither rendered, skipped, captioned nor image-owned
        has silently vanished, which is precisely the class of failure the
        manifest exists to make impossible to miss.
        """
        accounted = (
            {b.block_id for b in self.rendered_blocks}
            | {b.block_id for b in self.skipped_blocks}
            | set(self.caption_blocks)
            | set(self.image_owned_blocks)
        )
        expected = {d.block_id for d in self.text_ownership_decisions}
        return accounted == expected


def start_manifest(
    plan: OwnershipPlan,
    *,
    profile_id: str | None,
    typography_schema_version: str | None,
    effective_policies: dict[str, str],
) -> RenderManifest:
    """Seed a manifest from the ownership plan, before anything is drawn."""
    manifest = RenderManifest(
        profile_id=profile_id,
        typography_schema_version=typography_schema_version,
        source_blocks=[d.text for d in plan.decisions],
        text_ownership_decisions=list(plan.decisions),
        effective_policies=effective_policies,
    )
    for decision in plan.decisions:
        if decision.is_image_owned:
            manifest.image_owned_blocks.append(decision.block_id)
    return manifest
