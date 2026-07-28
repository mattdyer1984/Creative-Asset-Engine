"""
Coarse Attention Derivation.

This layer begins describing the DESTINATION (not the source). At this stage it
*derives* — it recovers, deterministically, the communication relationships and
attention structure already implicit in the Transformation Plan. It does not yet
*choose* between multiple valid destination strategies; when it later makes
creative choices not already encoded upstream, it becomes an Attention Planner.

It describes where a viewer's attention should go and what must be communicated,
provider-independently. A provider's composition is one valid solution.

The key abstraction is the CREATIVE CONTRACT:
  - the preserved communication relationships + focal constraints are the invariant;
  - everything not named in the contract is open design space.
Which of those open dimensions a given provider can actually vary is an ADAPTER
decision (provider capability), deliberately NOT enumerated here — that keeps
provider-independent planning separate from provider concerns.

Consumes ONLY the Transformation Plan + overlay brief. Never analysis/OCR.
Discipline (shared with Scene and Ownership): if a relationship cannot be
recovered confidently, emit an explicit gap — never invent it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from .plan import TransformationPlan, SlideDirective

# Role → coarse zone: ONLY a fallback used when no preserved geometry exists.
# When a reserved box is present, position comes from geometry (see _quantise_zone),
# and the role answers only "what is this space for", never "where".
_ZONE = {"hook_caption": "top", "price_card": "lower-corner", "subhead": "lower", "cta": "lower"}


def _band_v(y: float) -> str:
    return "top" if y < 0.33 else ("middle" if y < 0.66 else "lower")


def _band_h(x: float) -> str:
    return "left" if x < 0.33 else ("centre" if x < 0.66 else "right")


_V_ORDER = ("top", "middle", "lower")


def _quantise_zone(box):
    """A preserved reserved_zone [x_min,y_min,x_max,y_max] (normalised, y-down) →
    (coarse zone_intent, gap|None). Coarse, never coordinates. Uncertainty is
    preserved: a box spanning two adjacent vertical bands yields a compound label
    (e.g. 'top-middle'); a full-height box cannot be reduced and returns a gap."""
    x0, y0, x1, y1 = box
    b0, b1 = _band_v(max(0.0, y0)), _band_v(min(1.0, y1))
    i0, i1 = _V_ORDER.index(b0), _V_ORDER.index(b1)
    if i1 - i0 >= 2:
        # spans top..lower — genuinely cannot be reduced to a coarse vertical intent
        return "flexible", ("reserved zone spans the full height; coarse vertical "
                            "placement intent cannot be determined from geometry")
    v = b0 if i0 == i1 else f"{b0}-{b1}"           # single or two-adjacent-band compound
    # horizontal qualifier only when the box is localised to a SIDE (left/right);
    # a full-width or horizontally-central box adds no side information.
    if (x1 - x0) >= 0.6:
        h = None
    else:
        hb = _band_h((x0 + x1) / 2)
        h = None if hb == "centre" else hb
    return (v if h is None else f"{v}-{h}"), None


@dataclass
class BriefItem:
    purpose: str                       # hook_caption | price_card | subhead | cta
    box: tuple | None = None           # preserved reserved_zone (normalised); quantised, never sent raw


@dataclass
class Focus:
    element_ref: str
    weight: str                        # primary | secondary | supporting | absent
    attention_role: str


@dataclass
class Relationship:
    relationship: str                  # a PERSUASION relationship, not a layout
    must_hold: bool
    rationale: str
    geometry: str = "provider's choice"


@dataclass
class AttentionOpening:
    purpose: str
    zone_intent: str                   # coarse intent, not coordinates
    strictness: str                    # high | medium
    source: str = "geometry"           # provenance: geometry (quantised box) | role_default


@dataclass
class CreativeContract:
    """The invariant. Everything NOT named here is open design space, resolved by
    the adapter against its own capabilities. We do not enumerate the free space."""
    invariants: list[str]              # preserved relationships + focal constraints
    reuse_source_framing: bool = False


@dataclass
class SlideAttention:
    slide_index: int
    role: str
    dynamics: str                      # calm | building | dramatic
    focal_order: list[Focus]
    communication_relationships: list[Relationship]
    attention_openings: list[AttentionOpening]
    creative_contract: CreativeContract
    gaps: list[str] = field(default_factory=list)


@dataclass
class AttentionDerivation:
    slideshow_id: str
    slides: list[SlideAttention]


def _dynamics(role: str, mechanisms: list[str]) -> str:
    if role == "hook":
        return "building"
    if role == "reveal":
        return "dramatic" if ("product_desirability" in mechanisms or "value" in mechanisms) else "building"
    if role in ("educational", "problem", "education_step"):
        return "calm"
    if role in ("comparison", "comparison_side"):
        return "building"
    return "calm"


def _relationships(slide: SlideDirective, mechanisms: list[str], has_price_brief: bool):
    rels, gaps = [], []
    role, subj = slide.role, slide.scene.subject_present
    if role == "hook":
        if not slide.promoted_product_allowed:
            # the product is visually ABSENT — withhold it entirely to open the gap
            rels.append(Relationship("product_withheld", True,
                                     "the hook withholds the absent product to open a curiosity gap"))
        elif not slide.promoted_identity_revealed:
            # the product is VISIBLE but its promoted identity/offer is withheld —
            # the curiosity gap is preserved through identity concealment, not deletion
            rels.append(Relationship("promoted_identity_withheld", True,
                                     "the product is visible but its promoted identity/offer is "
                                     "withheld to open a curiosity gap"))
        if subj:
            rels.append(Relationship("reaction_drives_curiosity", True, "the person's reaction is the hook"))
    if role == "reveal" and slide.promoted_product_allowed:
        rels.append(Relationship("product_revealed", True, "the reveal presents the promoted product"))
        rels.append(Relationship("product_is_dominant_focus", True, "the product carries this slide"))
        gaps.append("whether the product must be shown *in use* (e.g. 'homemade') is not recoverable "
                    "from the Plan — coarse derivation cannot assert it")
    if role in ("educational", "problem", "education_step"):
        rels.append(Relationship("headline_explains_subject", True, "the headline explains the illustrated subject"))
    if role in ("comparison", "comparison_side"):
        rels.append(Relationship("comparison_must_remain_legible", True, "a comparison relationship carries the message"))
        gaps.append("comparison sub-type (before/after vs equally-weighted) not distinguishable from the Plan")
    if "value" in mechanisms and has_price_brief:
        rels.append(Relationship("price_is_evidence", True, "the discount/price is the persuasion proof, not decoration"))
    if "social_proof" in mechanisms or "scarcity" in mechanisms:
        rels.append(Relationship("quantity_or_proof_visible", True, "abundance/proof must read as evidence"))
    return rels, gaps


def _focal(slide: SlideDirective):
    focal = []
    prod = [e for e in slide.elements if e.kind == "product"]
    if slide.promoted_product_allowed and prod:
        # every promoted product is a focal anchor — the collection is not collapsed to prod[0]
        for p in prod:
            focal.append(Focus(p.element_id, "primary", "a promoted product is a destination of attention"))
    if slide.scene.subject_present:
        w = "secondary" if (slide.promoted_product_allowed and prod) else "primary"
        focal.append(Focus("subject", w, "the person / reaction / illustrated figure"))
    focal.append(Focus("scene", "supporting", "environment and context"))
    if slide.role == "hook" and not slide.promoted_product_allowed:
        focal.append(Focus("promoted_product", "absent", "deliberately withheld on the hook"))
    return focal


def derive_attention(plan: TransformationPlan, brief: dict[int, list[BriefItem]]) -> AttentionDerivation:
    slides = []
    for s in plan.slides:
        items = brief.get(s.slide_index, [])
        has_price = any(b.purpose == "price_card" for b in items)
        rels, gaps = _relationships(s, plan.mechanisms_to_preserve, has_price)
        focal = _focal(s)
        # Opening placement comes from the PRESERVED geometry (reserved_zone),
        # quantised to a coarse band. The role only names the purpose. Position is
        # taken from the role table ONLY as an explicit fallback when no box exists.
        openings = []
        for b in items:
            strict = "high" if b.purpose == "price_card" else "medium"
            if b.box is not None:
                intent, zgap = _quantise_zone(b.box)
                openings.append(AttentionOpening(b.purpose, intent, strict, source="geometry"))
                if zgap:
                    gaps.append(f"{b.purpose} opening: {zgap} — using coarse fallback intent")
            else:
                openings.append(AttentionOpening(b.purpose, _ZONE.get(b.purpose, "flexible"),
                                                 strict, source="role_default"))
                gaps.append(f"{b.purpose} opening position inferred from role "
                            f"(no preserved geometry)")
        # The creative contract = the invariant only. The remaining design space is
        # implicit (everything else) and resolved by the adapter, not enumerated here.
        invariants = [r.relationship for r in rels] + \
                     [f"{f.element_ref} stays {f.weight}" for f in focal if f.weight in ("primary", "absent")]
        slides.append(SlideAttention(
            slide_index=s.slide_index, role=s.role, dynamics=_dynamics(s.role, plan.mechanisms_to_preserve),
            focal_order=focal, communication_relationships=rels, attention_openings=openings,
            creative_contract=CreativeContract(invariants=invariants), gaps=gaps,
        ))
    return AttentionDerivation(slideshow_id=plan.slideshow_id, slides=slides)
