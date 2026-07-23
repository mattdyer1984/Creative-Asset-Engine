"""
SceneAnalysis — Phase 10.4 of AI Creative Engine vNext (see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §8, "Scene
Intelligence"). Genuinely new - confirmed via that ADR's §1 that
`ProductIsolationProvider` today detects and crops exactly the product,
nothing else; nothing in this codebase segments a slide into regions or
scores their importance before this.

`AnalysisArtifactMixin`-shaped like `CreativeFingerprint` - a per-slide
analysis pass, part of `SLIDESHOW_STAGE_PIPELINE` like every other
analysis artifact (not a paid generation/validation action kept out of
it, unlike `GeneratedImage`/`ImageValidationResult`).

regions_json is a plain JSON list of region dicts
(`region_type`/`bounding_box`/`importance_tier`/`notes`), not a
separate join table - regions have no identity or lifecycle of their
own beyond "part of this one analysis" (the same reasoning
`ImageValidationResult.field_checks_json` and
`OCRResult.structured_blocks_json` already use for their own per-item
lists), unlike `GenerationReferenceSetImage`, which is a real join
table because its rows reference other real, independently-addressable
entities (`ProductReferenceImage`).

The ADR's one hard constraint, enforced in code by
`SceneIntelligenceStage`, not trusted from the AI response: **any
region the model classifies as `region_type="product"` is always
forced to `importance_tier="essential"`**, regardless of what tier the
model itself assigned - Scene Intelligence's whole value is in
correctly identifying what's *safe* to change, and getting the product
region's tier wrong would directly undermine Product Lock v2's
identity-fidelity work.
"""

from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._analysis_artifact_mixin import AnalysisArtifactMixin


class SceneAnalysis(Base, AnalysisArtifactMixin):
    __tablename__ = "scene_analyses"

    slide_id: Mapped[str] = mapped_column(ForeignKey("slides.id"), nullable=False)
    regions_json: Mapped[list] = mapped_column(JSON, nullable=False)
