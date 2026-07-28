"""
Ownership — the Plan consumes the authoritative ownership artifact for rendering
responsibility, instead of reconstructing it from OCR surface/role/text.

  * artifact present → rendering_owner comes from handling_policy
    (optional_overlay → composite_layer; preserve_visual_role → provider_scene);
  * artifact absent  → OCR heuristic fallback, recorded as an explicit gap;
  * "required exact" is gated on a deterministic renderer, so scene-owned price
    text (the "£20" on the banknote) is no longer a required composite overlay,
    while its commercial-value evidence is preserved.

Deterministic, synthetic + fixture driven, no paid calls.
"""
from tests.fixtures.transformation.snapshot_source import SnapshotAnalysisSource
from app.transformation.plan_builder import build_plan
from app.transformation.pre_validator import validate_pre


def _source(blocks, ownership):
    """One slide; blocks = list of OCR dicts; ownership = {block_index: {...}} or {}."""
    snap = {
        "slideshow_id": "synthowner000000",
        "slides": [{"slide_index": 0, "id": "slide0"}],
        "narrative": {"cta_slide_index": None, "slides": [{"slide_index": 0, "beat": "reveal"}]},
        "marketing_text": "",
        "per_slide": {"slide0": {
            "fingerprint": {"visual_style": "clean", "marketing_objective": "sell",
                            "background_environment": "studio", "lighting_style": "soft",
                            "layout_and_composition": "centered", "emotional_appeal": []},
            "scene_regions": [], "ocr_blocks": blocks, "product_appearances": [],
            "source_dims": None,
            "text_ownership": {str(k): v for k, v in ownership.items()},
        }},
        "product_references": {},
    }
    return SnapshotAnalysisSource(snap)


def _bb(y): return {"x_min": 0.1, "y_min": y, "x_max": 0.9, "y_max": y + 0.08}


def _el(plan, eid):
    s = plan.slides[0]
    return next((e for e in s.elements if e.element_id == eid), None)


# --------------------------------------------------- artifact present → consumed
def test_caption_overlay_is_composited_from_artifact():
    blocks = [{"text": "50% OFF TODAY", "role": "headline", "surface": "overlay", "bounding_box": _bb(0.05)}]
    plan = build_plan(_source(blocks, {0: {"owner": "caption", "handling_policy": "optional_overlay",
                                           "text_class": "platform_caption", "confidence": 1.0}}), "synthowner")
    e = _el(plan, "s0_t0")
    assert e.rendering_owner == "composite_layer", e.rendering_owner
    prov = " ".join(p.decision + p.detail for p in e.provenance)
    assert "consumed from ownership artifact" in prov, prov


def test_scene_price_is_provider_rendered_and_not_required():
    """The '£20' on the note: owned by the image (preserve_visual_role) → provider_scene,
    and NOT promoted to a required composite overlay, though it keeps its value evidence."""
    blocks = [{"text": "£20", "role": "other", "surface": "physical", "bounding_box": _bb(0.4)}]
    plan = build_plan(_source(blocks, {0: {"owner": "image", "handling_policy": "preserve_visual_role",
                                           "text_class": "product_native", "confidence": 1.0}}), "synthowner")
    e = _el(plan, "s0_t0")
    assert e.rendering_owner == "provider_scene", e.rendering_owner
    assert e.element_id not in plan.slides[0].required_text_element_ids
    # commercial-value evidence is preserved (not discarded)
    assert any(v["value"] for v in e.commercial_values), e.commercial_values
    prov = " ".join(p.decision + p.detail for p in e.provenance)
    assert "consumed from ownership artifact" in prov


def test_artifact_overrides_the_ocr_surface_heuristic():
    """A physical-surface block the OCR heuristic would call provider_scene, but which
    the artifact marks a separable caption, follows the ARTIFACT."""
    blocks = [{"text": "LINK IN BIO", "role": "other", "surface": "physical", "bounding_box": _bb(0.85)}]
    plan = build_plan(_source(blocks, {0: {"owner": "caption", "handling_policy": "optional_overlay",
                                           "text_class": "platform_caption", "confidence": 0.95}}), "synthowner")
    assert _el(plan, "s0_t0").rendering_owner == "composite_layer"


# --------------------------------------------------- artifact absent → gap + fallback
def test_absent_artifact_falls_back_to_ocr_and_records_gap():
    blocks = [{"text": "HELLO", "role": "headline", "surface": "overlay", "bounding_box": _bb(0.05)}]
    plan = build_plan(_source(blocks, {}), "synthowner")   # no ownership
    e = _el(plan, "s0_t0")
    assert e.rendering_owner == "composite_layer"           # OCR fallback still works
    prov = " ".join(p.decision + p.detail for p in e.provenance)
    assert "inferred from OCR" in prov and "GAP" in prov, prov


# --------------------------------------------------- the Colgate residual is resolved
def test_colgate_s0_t1_no_longer_required_and_prevalidates():
    plan = build_plan(SnapshotAnalysisSource.load("colgate"),
                      SnapshotAnalysisSource.load("colgate")._s["slideshow_id"][:8])
    s0 = next(s for s in plan.slides if s.slide_index == 0)
    # the "£20" element is provider_scene (OCR fallback) and NOT required
    e = next(e for e in s0.elements if e.element_id == "s0_t1")
    assert e.rendering_owner == "provider_scene"
    assert "s0_t1" not in s0.required_text_element_ids
    # its value evidence survives
    assert any(v["value"] for v in e.commercial_values)
    # the previously-failing pre-validator check now passes for Colgate
    res = validate_pre(plan)
    fails = [c.name for c in res.checks if c.status not in ("ok", "pass", "deferred")]
    assert res.passed, fails


def test_fixtures_record_ownership_provenance_on_every_text():
    """Every text element carries an explicit ownership-source provenance line."""
    for name in ["ninja", "colgate", "crocs", "posture"]:
        plan = build_plan(SnapshotAnalysisSource.load(name),
                          SnapshotAnalysisSource.load(name)._s["slideshow_id"][:8])
        for s in plan.slides:
            for e in s.elements:
                # per-OCR-block text elements only (the _packaging aggregate is a
                # separate on-product feature roll-up, not a single OCR block)
                if e.kind != "text" or e.element_id.endswith("_packaging"):
                    continue
                prov = " ".join(p.decision for p in e.provenance)
                assert ("ownership artifact" in prov or "inferred from OCR" in prov), (name, e.element_id, prov)
