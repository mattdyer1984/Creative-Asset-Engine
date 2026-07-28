"""
Canvas — source aspect is captured as evidence; output aspect is a decided policy
(fixed 3:4), flowed from the spec, never invented as a hardcoded literal.

Capture → carry → consume:
  * capture: source pixel dims measured into the read-surface (here via snapshot);
  * carry: a Canvas on Plan/Spec records source_aspect (evidence) + output_aspect
    (decision) + provenance/gap;
  * consume: the provider request states the output aspect from the canvas — a 3:4
    source is 3:4, a 9:16 source is retargeted to 3:4, and NO request says "9:16".

Deterministic, synthetic + fixture driven, no paid calls.
"""
from tests.fixtures.transformation.snapshot_source import SnapshotAnalysisSource
from app.transformation.plan_builder import build_plan, _aspect_of, OUTPUT_ASPECT
from app.transformation.attention import derive_attention
from app.transformation.generation_spec import assemble_generation_spec
from app.transformation.generation_request import slide_requirements, validate_request_manifest
from app.transformation.adapters.nano_banana_prompt_adapter import NanoBananaPromptAdapter
from run_three_families import brief_from_plan


def _source(dims):
    """In-memory snapshot source: one hook slide with the given source_dims."""
    snap = {
        "slideshow_id": "synthcanvas00000",
        "slides": [{"slide_index": 0, "id": "slide0"}],
        "narrative": {"cta_slide_index": None, "slides": [{"slide_index": 0, "beat": "hook"}]},
        "marketing_text": "",
        "per_slide": {"slide0": {
            "fingerprint": {"visual_style": "clean", "marketing_objective": "sell",
                            "background_environment": "studio", "lighting_style": "soft",
                            "layout_and_composition": "centered", "emotional_appeal": []},
            "scene_regions": [], "ocr_blocks": [], "product_appearances": [],
            "source_dims": dims,
        }},
        "product_references": {},
    }
    return SnapshotAnalysisSource(snap)


def _canvas(dims):
    src = _source(dims)
    plan = build_plan(src, "synthcanvas")
    return plan.slides[0].canvas


def _request(dims):
    src = _source(dims)
    plan = build_plan(src, "synthcanvas")
    att = derive_attention(plan, brief_from_plan(plan))
    spec = assemble_generation_spec(plan, att, {})
    return spec.slides[0], NanoBananaPromptAdapter().write(spec.slides[0]).provider_request


# --------------------------------------------------------------- aspect helper
def test_aspect_helper_reduces():
    assert _aspect_of({"width": 900, "height": 1200}) == "3:4"
    assert _aspect_of({"width": 1080, "height": 1920}) == "9:16"
    assert _aspect_of(None) is None
    assert _aspect_of({"width": 0, "height": 10}) is None


# ------------------------------------------------ output is the decided 3:4 policy
def test_three_four_source_is_measured_and_output_is_3_4():
    cv = _canvas({"width": 1080, "height": 1440})
    assert cv.source_aspect == "3:4"
    assert cv.output_aspect == "3:4" == OUTPUT_ASPECT
    assert cv.fit_behaviour == "identity"
    assert not cv.gaps


def test_nine_sixteen_source_is_evidence_output_still_3_4():
    cv = _canvas({"width": 1080, "height": 1920})
    assert cv.source_aspect == "9:16"          # measured evidence preserved
    assert cv.output_aspect == "3:4"           # decision unchanged
    assert cv.fit_behaviour == "retarget"


def test_unknown_source_is_an_explicit_gap_not_a_default():
    cv = _canvas(None)
    assert cv.source_aspect is None
    assert cv.output_aspect == "3:4"           # policy still applies
    assert any("not captured" in g for g in cv.gaps), cv.gaps


# ---------------------------------------------- the symptom: request is 3:4, not 9:16
def test_request_states_3_4_output_never_9_16_output():
    for dims in ({"width": 1080, "height": 1440}, {"width": 1080, "height": 1920}, None):
        slide, req = _request(dims)
        # OUTPUT is always the decided 3:4 ...
        assert "Output aspect ratio: 3:4" in req, (dims, req[:160])
        # ... and 9:16 is never the OUTPUT (a source-evidence mention is allowed)
        assert "Output aspect ratio: 9:16" not in req and "9:16 TikTok" not in req, (dims, req)
    # where the source is not 9:16, the string 9:16 must not appear at all
    for dims in ({"width": 1080, "height": 1440}, None):
        _, req = _request(dims)
        assert "9:16" not in req, (dims, req)


def test_nine_sixteen_source_gets_a_retarget_note():
    slide, req = _request({"width": 1080, "height": 1920})
    assert "recompose for 3:4" in req, req


# ------------------------------------------ provenance chain source_dims -> spec -> request
def test_provenance_chain_holds():
    src = _source({"width": 1080, "height": 1440})
    plan = build_plan(src, "synthcanvas")
    cv = plan.slides[0].canvas
    prov = " ".join(f"{p.decision} {p.detail}" for p in cv.provenance)
    assert "1080x1440" in prov and "3:4" in prov          # measured -> plan
    att = derive_attention(plan, brief_from_plan(plan))
    spec = assemble_generation_spec(plan, att, {})
    sc = spec.slides[0].canvas
    assert sc.source_aspect == "3:4" and sc.output_aspect == "3:4"   # plan -> spec
    # spec -> request: canvas requirement is present and accounted
    reqs = slide_requirements(spec.slides[0])
    assert any(r.id.kind == "canvas" for r in reqs)
    checks = validate_request_manifest(spec.slides[0],
                                       NanoBananaPromptAdapter().write(spec.slides[0]).manifest)
    assert not [c for c in checks if c.status == "fail"]


# ------------------------------------------------ existing fixtures degrade gracefully
def test_fixtures_without_dims_carry_gap_and_3_4():
    src = SnapshotAnalysisSource.load("colgate")
    plan = build_plan(src, src._s["slideshow_id"][:8])
    for s in plan.slides:
        assert s.canvas.output_aspect == "3:4"
        # these snapshots predate capture → source unknown → explicit gap
        assert s.canvas.source_aspect is None
        assert s.canvas.gaps
