"""
Multi-product — the authoritative collection of promoted products is preserved
through the whole transformation pipeline, never collapsed to a singleton.

The invariant under test:
    every promoted product represented in the evidence remains represented
    throughout Plan → Spec → requirements → adapter → manifest.

The four single-product assumptions (detected[0], products[0], prod[0], the
slideshow invariant == 1) are all repaired to iterate the collection. The one
consumer that cannot be made deterministic from current evidence — binding a
product_native text to its OWN product among several — is left as an explicit gap
(a separate upstream capture task), never mis-collapsed to products[0].

Deterministic, synthetic + fixture driven, no paid calls.
"""
from tests.fixtures.transformation.snapshot_source import SnapshotAnalysisSource
from app.transformation.plan_builder import build_plan
from app.transformation.attention import derive_attention
from app.transformation.generation_spec import assemble_generation_spec
from app.transformation.generation_request import slide_requirements, validate_request_manifest
from app.transformation.adapters.nano_banana_prompt_adapter import (
    NanoBananaPromptAdapter, NanoBananaCapabilities)
from app.transformation.ownership import OwnershipDecision
from run_three_families import brief_from_plan


def _multi_source(n, with_product_native_text=False):
    """A reveal slide with N distinct current product appearances (each its own product)."""
    apps = [{"product_id": f"p{k}", "display_name": f"Product {k}", "is_current": True}
            for k in range(n)]
    ocr = []
    if with_product_native_text:
        ocr = [{"text": "BRAND", "role": "logo_text", "surface": "physical",
                "bounding_box": {"x_min": 0.1, "y_min": 0.1, "x_max": 0.3, "y_max": 0.2}}]
    snap = {
        "slideshow_id": "multiprod0000000",
        "slides": [{"slide_index": 0, "id": "slide0"}],
        "narrative": {"cta_slide_index": None, "slides": [{"slide_index": 0, "beat": "reveal"}]},
        "marketing_text": "",
        "per_slide": {"slide0": {
            "fingerprint": {"visual_style": "studio", "marketing_objective": "sell",
                            "background_environment": "table", "lighting_style": "soft",
                            "layout_and_composition": "row", "emotional_appeal": []},
            "scene_regions": [], "ocr_blocks": ocr, "product_appearances": apps,
            "source_dims": None, "text_ownership": {},
        }},
        "product_references": {f"p{k}": [f"ref{k}"] for k in range(n)},
    }
    return SnapshotAnalysisSource(snap)


def _pipeline(src, ownership=None):
    plan = build_plan(src, "multiprod")
    att = derive_attention(plan, brief_from_plan(plan))
    spec = assemble_generation_spec(plan, att, ownership or {})
    return plan, att, spec


# --------------------------- N products preserved through the whole pipeline
def test_n_products_preserved_end_to_end():
    N = 3
    plan, att, spec = _pipeline(_multi_source(N))
    s0p = next(s for s in plan.slides if s.slide_index == 0)
    prod_els = [e for e in s0p.elements if e.kind == "product"]
    assert len(prod_els) == N, [e.element_id for e in prod_els]          # N product elements

    sp = spec.slides[0]
    assert len(sp.products) == N                                          # N in the spec
    reqs = slide_requirements(sp)
    assert len([r for r in reqs if r.id.kind == "product_identity"]) == N  # N identity reqs
    assert len([r for r in reqs if r.id.kind == "reference"]) == N         # N reference reqs

    # N focal anchors (every promoted product)
    a0 = next(a for a in att.slides if a.slide_index == 0)
    prod_focus = [f for f in a0.focal_order if f.element_ref.startswith("s0_product")]
    assert len(prod_focus) == N, prod_focus

    # manifest accounts for all N, and both identities are realized in the request
    out = NanoBananaPromptAdapter(NanoBananaCapabilities(max_references=8)).write(sp)
    assert not [c for c in validate_request_manifest(sp, out.manifest, out.provider_request)
                if c.status == "fail"]
    for k in range(N):
        assert f"Product {k}" in out.provider_request


def test_slideshow_invariant_counts_distinct_promoted():
    _, _, _ = _pipeline(_multi_source(3))
    plan = build_plan(_multi_source(3), "multiprod")
    inv = next(i for i in plan.invariants if i.name == "distinct_promoted_products")
    assert inv.spec["distinct_promoted"] == 3, inv.spec


# --------------------------- the binding gap (evidence insufficient, not mis-bound)
def test_product_native_text_binding_is_a_gap_not_products0():
    src = _multi_source(2, with_product_native_text=True)
    # brand text owned by the product (product_native) on a 2-product slide
    plan = build_plan(src, "multiprod")
    tid = next(e.element_id for e in plan.slides[0].elements if e.kind == "text")
    own = {tid: OwnershipDecision(tid, "BRAND", "product_native", 0.95, True, "", ["recorded"], [])}
    _, _, spec = _pipeline(src, ownership=own)
    sp = spec.slides[0]
    # the owning target was NOT collapsed to products[0]; an explicit gap is recorded
    txt = next(t for t in sp.texts if t.ref == tid)
    assert txt.reference_target is None, txt.reference_target
    assert any("owning-product unresolved" in g for g in sp.gaps), sp.gaps


def test_single_product_binding_is_unchanged():
    src = _multi_source(1, with_product_native_text=True)
    plan = build_plan(src, "multiprod")
    tid = next(e.element_id for e in plan.slides[0].elements if e.kind == "text")
    own = {tid: OwnershipDecision(tid, "BRAND", "product_native", 0.95, True, "", ["recorded"], [])}
    _, _, spec = _pipeline(src, ownership=own)
    sp = spec.slides[0]
    txt = next(t for t in sp.texts if t.ref == tid)
    assert txt.reference_target == "s0_product", txt.reference_target      # binds to the sole product


# --------------------------- existing single-product fixtures are unaffected
def test_fixtures_single_product_ids_and_counts_unchanged():
    for name in ["ninja", "colgate", "crocs", "posture"]:
        src = SnapshotAnalysisSource.load(name)
        plan = build_plan(src, src._s["slideshow_id"][:8])
        for s in plan.slides:
            prods = [e for e in s.elements if e.kind == "product"]
            # every fixture slide has at most one product today -> keeps the `s{idx}_product` id
            assert len(prods) <= 1
            if prods:
                assert prods[0].element_id == f"s{s.slide_index}_product"
