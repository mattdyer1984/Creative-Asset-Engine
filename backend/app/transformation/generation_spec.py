"""
GenerationSpecification — single authoritative, immutable (frozen + tuples) view
of a slide. Fidelity is supplied per text by the text-execution seam (which
separates ownership/disposition from fidelity). Reference-fidelity text carries
its owning reference target. Unresolved execution -> explicit assembly gap.
"""
from __future__ import annotations

from dataclasses import dataclass
from .plan import TransformationPlan
from .attention import AttentionDerivation
from .text_execution import TextExecInput, resolve_text_execution
from .ownership import OwnershipDecision


@dataclass(frozen=True)
class SpecProduct:
    ref: str
    label: str
    reference_ids: tuple
    identity_required: bool = True


@dataclass(frozen=True)
class SpecText:
    ref: str
    text: str
    disposition: str                 # overlay_handoff | render_in_asset | unresolved
    fidelity_required: str           # none | semantic_presence | exact_text | reference_fidelity | unresolved
    reference_target: str | None = None
    source: str = ""


@dataclass(frozen=True)
class SpecScene:
    subject_present: bool
    subject_action: str | None
    subject_emotion: tuple
    environment: str
    lighting: str
    concept: str


@dataclass(frozen=True)
class SpecAttention:
    focal_order: tuple
    relationships: tuple             # informational: the source relationships (invariants carry the executable form)
    openings: tuple
    dynamics: str
    contract_invariants: tuple
    reuse_source_framing: bool


@dataclass(frozen=True)
class SlideGenerationSpec:
    slide_index: int
    product_allowed: bool
    products: tuple
    texts: tuple
    scene: SpecScene
    attention: SpecAttention
    gaps: tuple = ()


@dataclass(frozen=True)
class GenerationSpecification:
    slideshow_id: str
    slides: tuple


def assemble_generation_spec(plan: TransformationPlan, attention: AttentionDerivation,
                             ownership: dict[str, OwnershipDecision]) -> GenerationSpecification:
    att_by_idx = {s.slide_index: s for s in attention.slides}
    slides = []
    for s in plan.slides:
        products = tuple(
            SpecProduct(e.element_id, e.label, tuple(e.reference_ids), "identity" in e.must_survive)
            for e in s.elements if e.kind == "product"
        )
        product_ref = products[0].ref if products else None
        texts, gaps = [], []
        for e in s.elements:
            if e.kind != "text":
                continue
            d = ownership.get(e.element_id)
            owning = product_ref if (d is not None and d.ownership_class == "product_native") else None
            inp = TextExecInput(
                ownership=d, text=e.verbatim or "", text_status=e.text_status,
                must_survive=tuple(e.must_survive), semantic_role=(e.label.split()[0] if e.label else None),
                owning_product_ref=owning,
            )
            ex = resolve_text_execution(inp)
            texts.append(SpecText(e.element_id, e.verbatim or "", ex.disposition,
                                  ex.fidelity, ex.reference_target, ex.source))
            if ex.gap:
                gaps.append(f"{e.element_id}: {ex.gap}")

        sc = s.scene
        scene = SpecScene(sc.subject_present, sc.subject_action, tuple(sc.subject_emotion),
                          sc.environment, sc.lighting, sc.concept)
        a = att_by_idx.get(s.slide_index)
        if a:
            attn = SpecAttention(
                focal_order=tuple((f.element_ref, f.weight) for f in a.focal_order),
                relationships=tuple(r.relationship for r in a.communication_relationships),
                openings=tuple((o.purpose, o.zone_intent, o.strictness) for o in a.attention_openings),
                dynamics=a.dynamics, contract_invariants=tuple(a.creative_contract.invariants),
                reuse_source_framing=a.creative_contract.reuse_source_framing,
            )
            gaps.extend(a.gaps)
        else:
            attn = SpecAttention((), (), (), "calm", (), False)
        slides.append(SlideGenerationSpec(
            slide_index=s.slide_index, product_allowed=s.promoted_product_allowed,
            products=products, texts=tuple(texts), scene=scene, attention=attn, gaps=tuple(gaps),
        ))
    return GenerationSpecification(plan.slideshow_id, tuple(slides))
