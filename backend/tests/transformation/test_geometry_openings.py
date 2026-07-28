"""
Geometry — text-safe opening placement.

First-loss fix: the coarse opening `zone_intent` must come from the PRESERVED
reserved_zone (quantised to a coarse band), not reconstructed from the text's
role. Role answers "what is this space for"; geometry answers "where". The
provider contract stays coordinate-free — only coarse intent leaves the boundary.

Deterministic, fixture + synthetic driven, no paid calls.
"""
from tests.fixtures.transformation.snapshot_source import SnapshotAnalysisSource
from app.transformation.plan_builder import build_plan
from app.transformation.plan import (
    TransformationPlan, SlideDirective, SceneDirective, PlanElement,
)
from app.transformation.attention import (
    derive_attention, BriefItem, _quantise_zone, _ZONE,
)
from run_three_families import brief_from_plan


# ----------------------------------------------------------- quantiser unit level
def test_quantiser_bands_by_geometry():
    assert _quantise_zone([0.1, 0.05, 0.9, 0.2])[0] == "top"          # full-width top banner
    assert _quantise_zone([0.1, 0.7, 0.9, 0.9])[0] == "lower"         # full-width lower
    assert _quantise_zone([0.1, 0.45, 0.9, 0.55])[0] == "middle"      # full-width mid
    # horizontal qualifier only when localised
    assert _quantise_zone([0.68, 0.72, 0.85, 0.9])[0] == "lower-right"
    assert _quantise_zone([0.0, 0.4, 0.3, 0.6])[0] == "middle-left"


def test_quantiser_preserves_uncertainty():
    # a box spanning two adjacent bands -> compound label (not forced into one)
    assert _quantise_zone([0.1, 0.28, 0.9, 0.5])[0] == "top-middle"
    # a full-height box cannot be reduced -> explicit gap, coarse 'flexible'
    intent, gap = _quantise_zone([0.0, 0.05, 1.0, 0.95])
    assert intent == "flexible" and gap is not None


# ----------------------------------------- the core property: geometry dominates
def _regions_plan():
    """Two headline elements, same role, DIFFERENT positions (top vs middle)."""
    top = PlanElement("s0_t0", "text", "headline text", verbatim="TOP HOOK",
                      rendering_owner="composite_layer", reserved_zone=[0.1, 0.05, 0.9, 0.2])
    mid = PlanElement("s0_t1", "text", "headline text", verbatim="MID HOOK",
                      rendering_owner="composite_layer", reserved_zone=[0.2, 0.45, 0.8, 0.55])
    sd = SlideDirective(0, "hook", promoted_product_allowed=False, cta_allowed=False,
                        scene=SceneDirective(), elements=[top, mid])
    return TransformationPlan("synthgeo00000000", 1, "direct_response", ["curiosity"], [sd], [])


def test_same_role_different_location_yields_different_intents():
    plan = _regions_plan()
    att = derive_attention(plan, brief_from_plan(plan))
    opens = att.slides[0].attention_openings
    intents = sorted(o.zone_intent for o in opens)
    # both are 'hook_caption' by role, yet their intents differ by GEOMETRY
    assert {o.purpose for o in opens} == {"hook_caption"}
    assert "top" in intents and any(i.startswith("middle") for i in intents), intents
    assert intents[0] != intents[1], intents
    assert all(o.source == "geometry" for o in opens)


def test_low_hook_caption_is_not_forced_to_top():
    """The exact inversion the role table would produce: a hook caption placed low
    must yield a lower/middle intent, never 'top'."""
    low = PlanElement("s0_t0", "text", "headline text", verbatim="LOW HOOK",
                      rendering_owner="composite_layer", reserved_zone=[0.1, 0.78, 0.9, 0.92])
    sd = SlideDirective(0, "hook", promoted_product_allowed=False, cta_allowed=False,
                        scene=SceneDirective(), elements=[low])
    plan = TransformationPlan("synthgeo00000000", 1, "direct_response", ["curiosity"], [sd], [])
    o = derive_attention(plan, brief_from_plan(plan)).slides[0].attention_openings[0]
    assert o.zone_intent == "lower", o.zone_intent          # role table would have said 'top'
    assert o.source == "geometry"


def test_high_price_is_not_forced_to_lower_corner():
    """A price at the TOP must not be forced to 'lower-corner' by role."""
    hi = PlanElement("s0_t0", "text", "price text", verbatim="£50",
                     rendering_owner="composite_layer", reserved_zone=[0.7, 0.06, 0.9, 0.16])
    sd = SlideDirective(0, "reveal", promoted_product_allowed=True, cta_allowed=False,
                        promoted_identity_revealed=True, scene=SceneDirective(), elements=[hi])
    plan = TransformationPlan("synthgeo00000000", 1, "direct_response", ["value"], [sd], [])
    o = derive_attention(plan, brief_from_plan(plan)).slides[0].attention_openings[0]
    assert o.zone_intent == "top-right", o.zone_intent
    assert o.source == "geometry"


# ------------------------------------------- explicit role fallback + provenance
def test_role_fallback_when_no_geometry_is_flagged():
    """No reserved_zone -> position inferred from role, explicitly recorded."""
    el = PlanElement("s0_t0", "text", "headline text", verbatim="NO BOX",
                     rendering_owner="composite_layer", reserved_zone=None)
    sd = SlideDirective(0, "hook", promoted_product_allowed=False, cta_allowed=False,
                        scene=SceneDirective(), elements=[el])
    plan = TransformationPlan("synthgeo00000000", 1, "direct_response", ["curiosity"], [sd], [])
    a = derive_attention(plan, brief_from_plan(plan)).slides[0]
    o = a.attention_openings[0]
    assert o.source == "role_default"
    assert o.zone_intent == _ZONE["hook_caption"]           # falls back to the role default
    assert any("inferred from role" in g for g in a.gaps), a.gaps


# ------------------------------------------------------ fixtures still coherent
def test_colgate_mid_headline_now_tracks_geometry():
    plan = build_plan(SnapshotAnalysisSource.load("colgate"),
                      SnapshotAnalysisSource.load("colgate")._s["slideshow_id"][:8])
    att = derive_attention(plan, brief_from_plan(plan))
    a1 = next(s for s in att.slides if s.slide_index == 1)
    # s1_t0 headline is at y~0.56 (mid) in the source — must NOT be 'top' anymore
    hooks = [o for o in a1.attention_openings if o.purpose == "hook_caption"]
    assert hooks and all(o.source == "geometry" for o in hooks)
    assert all(o.zone_intent != "top" for o in hooks), [o.zone_intent for o in hooks]


def test_provider_request_stays_coordinate_free():
    """The opening reaches the provider as coarse words, never as raw coordinates."""
    from app.transformation.generation_spec import assemble_generation_spec
    from app.transformation.adapters.nano_banana_prompt_adapter import NanoBananaPromptAdapter
    import re
    src = SnapshotAnalysisSource.load("crocs")
    plan = build_plan(src, src._s["slideshow_id"][:8])
    att = derive_attention(plan, brief_from_plan(plan))
    spec = assemble_generation_spec(plan, att, {})
    for s in spec.slides:
        req = NanoBananaPromptAdapter().write(s).provider_request
        # no normalised coordinate triples/decimals from a reserved_zone leak through
        assert not re.search(r"0\.\d+\s*,\s*0\.\d+", req), req[:200]
