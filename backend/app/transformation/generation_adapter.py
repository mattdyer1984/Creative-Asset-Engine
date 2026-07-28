"""
Generation adapter — builds a provider-ready request from the Plan and NOTHING
else. Its only input is the TransformationPlan. It composes the prompt (that is
the adapter's job — executing decisions), but it never reads analysis.

Overlay-first flow (point 3):
  extract overlay -> EXCLUDE from image generation -> reserve layout space ->
  generate the upgraded scene -> composite deterministic text -> verify.

If the Plan is missing something essential, it is reported in `unresolved`
(never guessed). A non-empty `unresolved` means the Plan is not yet sufficient.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .plan import TransformationPlan, SlideDirective


@dataclass
class GenerationRequest:
    slide_index: int
    provider: str
    prompt: str
    reference_images: list[str] = field(default_factory=list)
    reserved_text_zones: list[list] = field(default_factory=list)
    composite_layer: list[dict] = field(default_factory=list)   # rendered by the app, not the model
    excluded_from_generation: list[str] = field(default_factory=list)
    originality_levers_required: int = 3
    unresolved: list[str] = field(default_factory=list)         # essential info the Plan didn't supply


def _slide(plan: TransformationPlan, idx: int) -> SlideDirective:
    s = next((s for s in plan.slides if s.slide_index == idx), None)
    if s is None:
        raise ValueError(f"slide {idx} not in plan")
    return s


def build_generation_request(plan: TransformationPlan, slide_index: int) -> GenerationRequest:
    s = _slide(plan, slide_index)
    sc = s.scene
    unresolved = list(sc.gaps)

    lines: list[str] = []
    # 1. scene concept + subject
    if sc.concept:
        lines.append(f"Create an original {sc.concept}.")
    if sc.subject_present:
        emo = ", ".join(sc.subject_emotion) if sc.subject_emotion else ""
        act = sc.subject_action or ""
        lines.append(f"Show a NEW, different person {act}"
                     + (f", conveying {emo}." if emo else "."))
    # 2. product identity via references (not source pixels)
    prod = next((e for e in s.elements if e.kind == "product"), None)
    references: list[str] = list(sc.references_provided)
    if s.promoted_product_allowed and prod:
        # Anchor the promoted identity ONLY where the plan reveals it (product element
        # survives by "identity"). Where the product is merely present (survives by
        # "presence"), show it in-context WITHOUT anchoring the promoted-offer identity —
        # so no missing-reference conflict is raised on an identity-withheld hook.
        if "identity" in prod.must_survive:
            if prod.preservation_mode == "product_reference" and prod.reference_ids:
                lines.append(f"Feature the exact promoted product ({prod.label}); reproduce its identity "
                             f"precisely from the provided reference image(s); regenerate the surroundings.")
            elif prod.preservation_mode == "identity_constraint":
                lines.append(f"Feature the promoted product ({prod.label}); keep its identity accurate.")
                unresolved.append("product identity has no reference images (identity_constraint only)")
        else:
            lines.append(f"A product ({prod.label}) is visible in the scene, but do NOT reveal or anchor "
                         f"the promoted-offer identity here — keep it incidental and in-context.")
    elif not s.promoted_product_allowed:
        lines.append("Do NOT show or reference the promoted product (this is the hook; the product is withheld).")

    # 3. environment / lighting / framing + change directives (originality)
    if sc.environment:
        lines.append(f"Environment: {sc.environment} — but change it substantially from the original.")
    if sc.lighting:
        lines.append(f"Lighting: {sc.lighting}.")
    if sc.framing:
        lines.append(f"Framing: {sc.framing}.")
    if sc.change_directives:
        lines.append("Deliberately change, for originality: " + ", ".join(sc.change_directives) + ".")

    # 4. overlay-first: reserve zones, render NO text
    reserved_zones, composite, excluded = [], [], []
    for e in s.elements:
        if e.kind == "text" and e.rendering_owner == "composite_layer":
            excluded.append(e.element_id)
            composite.append({"element": e.element_id, "text": e.verbatim,
                              "zone": e.reserved_zone, "status": e.text_status})
            if e.reserved_zone:
                reserved_zones.append(e.reserved_zone)
            else:
                unresolved.append(f"composite text {e.element_id} has no reserved zone")
    if reserved_zones:
        lines.append(f"Reserve {len(reserved_zones)} clear text-safe zone(s) at "
                     f"{reserved_zones}; render NO text, numbers, prices or watermarks in the image "
                     f"(all copy is composited by the app afterwards).")

    return GenerationRequest(
        slide_index=slide_index, provider="nano_banana", prompt="\n".join(lines),
        reference_images=references, reserved_text_zones=reserved_zones,
        composite_layer=composite, excluded_from_generation=excluded,
        originality_levers_required=s.originality_levers_required, unresolved=unresolved,
    )
