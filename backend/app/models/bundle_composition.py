"""
BundleComposition / BundleCompositionMember — Phase 10.7 of AI Creative
Engine vNext (see MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext"
§12's "Bundle Composition" addendum). The user's explicit answer to
that section's conflict #1: the Generation/Reference Selection/
Identity Validation engines stay product-centric (reason about exactly
one canonical product at a time) - Bundle Composition is a composition
capability layered on top for the specific case a marketing objective
calls for a group shot, "a composition problem, not a relaxation of
Product Lock."

A `BundleComposition` is created fresh for one `GenerationAttempt`,
exactly mirroring how a single-product attempt's own
`GenerationReferenceSet` is created fresh per attempt rather than
reused as a persisted template (see app.services.reference_selection) -
not a reusable "bundle definition" entity a user configures ahead of
time. `slide_id`/`creative_specification_id` record which attempt it
was built for, the same provenance `GenerationAttempt` itself already
carries.

Each `BundleCompositionMember` runs Reference Selection independently,
once per product, exactly as the single-product flow already does
(app.services.reference_selection.select_reference_images) - Bundle
Composition never asks Reference Selection to reason about more than
one product at once, it only assembles already-independent selections
afterward. `generation_reference_set_id` is therefore always non-null:
a member row is only ever persisted once its own Reference Selection
has already succeeded (see app.services.generation_engine.
run_bundle_generation_attempt) - a member whose product has no
Library yet aborts the whole attempt before any row here is written,
the same "no partial write on failure" discipline
run_generation_attempt already holds for its own single Reference Set.

role_in_scene (e.g. "hero"/"left"/"right"/"background") and rank feed
the Prompt Compiler's bundle-composition instruction
(app.services.prompt_compiler.compile_generation_request) - what the
provider is told each product's part in the composed scene is, and
what order its reference images appear in the compiled request.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import new_uuid, utcnow


class BundleComposition(Base):
    __tablename__ = "bundle_compositions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    slide_id: Mapped[str] = mapped_column(ForeignKey("slides.id"), nullable=False)
    creative_specification_id: Mapped[str] = mapped_column(
        ForeignKey("creative_specifications.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class BundleCompositionMember(Base):
    __tablename__ = "bundle_composition_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    bundle_composition_id: Mapped[str] = mapped_column(
        ForeignKey("bundle_compositions.id"), nullable=False
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    generation_reference_set_id: Mapped[str] = mapped_column(
        ForeignKey("generation_reference_sets.id"), nullable=False
    )
    role_in_scene: Mapped[str] = mapped_column(String(64), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
