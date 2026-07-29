"""
In-app entry point to the frozen transformation layer (app.transformation.*).

This is the seam that lets the browser generation flow consume the remediated
Transformation Plan pipeline instead of the older vNext Creative-Specification
path. For one slide it runs:

    build_plan(AnalysisSource) -> ownership -> brief -> derive_attention
        -> assemble_generation_spec -> NanoBananaPromptAdapter.write

and returns a provider-agnostic `GenerationRequest` whose `precompiled_prompt`
is the adapter's final provider request (see GenerationRequest.precompiled_prompt
for why it is sent verbatim rather than re-compiled).

The two derivations `_brief_from_plan`/`_ownership_from_plan` are deterministic
and were previously duplicated in the run_*.py scripts; they are promoted here
so the app and the scripts share one definition.

Reference precedence (the locked evidence-precedence rule, applied here):
observed slide-derived crops are authoritative for product identity; a listing
image only fills a genuine gap. `AnalysisSource.product_references` returns every
current reference (crops AND the listing image), so `_prefer_observed_references`
drops the listing when slide crops exist for the product, and falls back to the
listing only when there is no observed crop. This placement is provisional - the
long-term home is the analysis->plan join - but it keeps the frozen layer
untouched while making the slice honour the rule.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_providers.base import GenerationRequest
from app.config import settings
from app.models.product_reference_image import ProductReferenceImage
from app.models.slide import Slide
from app.transformation.analysis_source import AnalysisSource
from app.transformation.attention import BriefItem, derive_attention
from app.transformation.generation_spec import (
    GenerationSpecification,
    SlideGenerationSpec,
    assemble_generation_spec,
)
from app.transformation.ownership import OwnershipDecision
from app.transformation.plan_builder import build_plan
from app.transformation.adapters.nano_banana_prompt_adapter import NanoBananaPromptAdapter

# Maps a text element's leading role word to the composite-layer brief purpose,
# same table the run_*.py scripts used. An unknown role falls through to
# "subhead" rather than erroring - a brief item with a slightly-off purpose is
# recoverable; a crash here is not.
_ROLE_TO_PURPOSE = {
    "headline": "hook_caption",
    "price": "price_card",
    "subheadline": "subhead",
    "cta": "cta",
}


def _brief_from_plan(plan) -> dict[int, list[BriefItem]]:
    brief: dict[int, list[BriefItem]] = {}
    for s in plan.slides:
        brief[s.slide_index] = [
            BriefItem(
                _ROLE_TO_PURPOSE.get(e.label.split()[0], "subhead"),
                box=tuple(e.reserved_zone) if e.reserved_zone else None,
            )
            for e in s.elements
            if e.kind == "text" and e.rendering_owner == "composite_layer"
        ]
    return brief


def _ownership_from_plan(plan) -> dict[str, OwnershipDecision]:
    """
    Deterministic ownership (element_id -> OwnershipDecision) from the plan's
    rendering_owner: composite_layer = creator overlay (composited later, not
    baked); on-product (element id ends with _packaging) = product_native; any
    other baked scene text = design_integral.
    """
    out: dict[str, OwnershipDecision] = {}
    for sd in plan.slides:
        for e in sd.elements:
            if e.kind != "text":
                continue
            if e.rendering_owner == "composite_layer":
                cls, alters = "creator_overlay", False
            elif e.element_id.endswith("_packaging"):
                cls, alters = "product_native", True
            else:
                cls, alters = "design_integral", True
            out[e.element_id] = OwnershipDecision(
                e.element_id, e.verbatim or "", cls, 0.9, alters,
                "derived from plan rendering_owner", ["plan_derived"], [],
            )
    return out


def build_slideshow_spec(slideshow_id: str, *, db_path: str | None = None) -> GenerationSpecification:
    """Run the transformation layer for a whole slideshow -> GenerationSpecification."""
    source = AnalysisSource(str(db_path or settings.database_path))
    try:
        plan = build_plan(source, slideshow_id)
        ownership = _ownership_from_plan(plan)
        brief = _brief_from_plan(plan)
        attention = derive_attention(plan, brief)
        return assemble_generation_spec(plan, attention, ownership)
    finally:
        # AnalysisSource opens its own read-only sqlite connection; close it so
        # a per-request runner doesn't leak connections against the live DB file.
        conn = getattr(source, "_c", None)
        if conn is not None:
            conn.close()


def _prefer_observed_references(
    db: Session, reference_ids: tuple[str, ...]
) -> tuple[list[str], list[str]]:
    """
    Apply the reference-precedence rule and resolve to on-disk paths.

    Returns (chosen_reference_ids, chosen_file_paths) in the plan's order.
    Slide-derived crops (source_slide_id set) are authoritative; the listing /
    externally-imported reference (source_slide_id NULL) is used only when no
    observed crop exists for the product.
    """
    if not reference_ids:
        return [], []
    rows = db.execute(
        select(
            ProductReferenceImage.id,
            ProductReferenceImage.source_slide_id,
            ProductReferenceImage.file_path,
        ).where(ProductReferenceImage.id.in_(list(reference_ids)))
    ).all()
    by_id = {r.id: r for r in rows}

    observed = [rid for rid in reference_ids if by_id.get(rid) and by_id[rid].source_slide_id]
    chosen_ids = observed if observed else [rid for rid in reference_ids if by_id.get(rid)]
    paths = [by_id[rid].file_path for rid in chosen_ids if by_id[rid].file_path]
    return chosen_ids, paths


@dataclass
class TransformationRequest:
    """
    Everything the generation harness needs to run a Transformation-Plan
    generation for one slide, mapped onto the provider-agnostic types the
    existing pipeline already consumes.
    """

    request: GenerationRequest
    reference_ids: list[str]     # the plan's chosen references, after precedence
    slide_spec: SlideGenerationSpec
    provider_request: str


def build_transformation_request(
    db: Session, slide: Slide, *, db_path: str | None = None
) -> TransformationRequest | None:
    """
    Build the GenerationRequest for `slide` from the Transformation Plan.

    Returns None if the transformation layer produces no spec for this slide's
    index (e.g. the slideshow could not be planned) - the caller treats that as
    a clean "cannot generate from the Plan" failure.
    """
    spec = build_slideshow_spec(slide.slideshow_id, db_path=db_path)
    slide_spec = next((s for s in spec.slides if s.slide_index == slide.slide_index), None)
    if slide_spec is None:
        return None

    out = NanoBananaPromptAdapter().write(slide_spec)
    plan_reference_ids = tuple(r for p in slide_spec.products for r in p.reference_ids)
    chosen_ids, reference_paths = _prefer_observed_references(db, plan_reference_ids)
    aspect = slide_spec.canvas.output_aspect if slide_spec.canvas else "3:4"

    request = GenerationRequest(
        # creative_intent carries the same final text for prompt_used/logging
        # parity; precompiled_prompt is what the adapter actually sends.
        creative_intent=out.provider_request,
        reference_image_paths=reference_paths,
        things_to_avoid=[],
        aspect_ratio=aspect,
        precompiled_prompt=out.provider_request,
    )
    return TransformationRequest(
        request=request,
        reference_ids=chosen_ids,
        slide_spec=slide_spec,
        provider_request=out.provider_request,
    )
