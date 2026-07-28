"""
Enforcement family #4 — upstream product-presence integrity.

Two independent facts must not be collapsed into one boolean:
  * VISUAL PRESENCE — is the promoted product physically in the frame? (detection)
  * IDENTITY REVEAL — is this the narrative beat that reveals/anchors the offer?

The regression: the Crocs hook (slide 0) shows the product on a JD shelf, yet the
narrative beat is "hook". The old rule (`role != 'hook'`) withheld the product,
instructing generation to DELETE a product the source actually shows, and asserted
a false `product_absent_on_hook` invariant. A hook where the product is genuinely
absent (Colgate banknote, Ninja reaction) must still withhold it.

Deterministic, portable-fixture driven, no paid calls.
"""
from tests.fixtures.transformation.snapshot_source import SnapshotAnalysisSource
from app.transformation.plan_builder import build_plan
from app.transformation.attention import derive_attention
from app.transformation.generation_spec import assemble_generation_spec
from app.transformation.adapters.nano_banana_prompt_adapter import NanoBananaPromptAdapter
from run_three_families import brief_from_plan


def _synthetic_source(beats, per_slide_detected):
    """Build an in-memory snapshot source: beats={idx:beat}, per_slide_detected={idx:bool}."""
    slides = [{"slide_index": i, "id": f"slide{i}"} for i in beats]
    per_slide = {}
    for i in beats:
        det = per_slide_detected.get(i, False)
        apps = ([{"product_id": "pX", "display_name": "Widget 3000",
                  "is_current": True}] if det else [])
        per_slide[f"slide{i}"] = {
            "fingerprint": {"visual_style": "clean studio", "marketing_objective": "sell",
                            "background_environment": "studio", "lighting_style": "soft",
                            "layout_and_composition": "centered", "emotional_appeal": []},
            "scene_regions": [], "ocr_blocks": [], "product_appearances": apps,
        }
    snap = {
        "slideshow_id": "synthaaaa00000000",
        "slides": slides,
        "narrative": {"cta_slide_index": None,
                      "slides": [{"slide_index": i, "beat": b} for i, b in beats.items()]},
        "marketing_text": "",
        "per_slide": per_slide,
        "product_references": {"pX": ["refX"]},
    }
    return SnapshotAnalysisSource(snap)


def _plan(name):
    src = SnapshotAnalysisSource.load(name)
    return build_plan(src, src._s["slideshow_id"][:8])


def _slide(plan, idx):
    return next(s for s in plan.slides if s.slide_index == idx)


def _request(plan, idx):
    att = derive_attention(plan, brief_from_plan(plan))
    spec = assemble_generation_spec(plan, att, {})
    sp = next(s for s in spec.slides if s.slide_index == idx)
    return NanoBananaPromptAdapter().write(sp).provider_request


def _inv_names(plan, scope):
    return {i.name for i in plan.invariants if i.scope == scope}


# ------------------------------------------------ the Crocs contradiction (was RED)
def test_crocs_hook_keeps_the_visibly_present_product():
    plan = _plan("crocs")
    s0 = _slide(plan, 0)
    # visual presence is TRUE — the product is on the shelf
    assert s0.promoted_product_allowed is True, s0.promoted_product_allowed
    # but the promoted identity is NOT revealed on the hook
    assert s0.promoted_identity_revealed is False, s0.promoted_identity_revealed
    # a product element exists and survives by PRESENCE, not anchored identity
    prod = [e for e in s0.elements if e.kind == "product"]
    assert prod, "product element must exist when the product is visibly present"
    assert "presence" in prod[0].must_survive and "identity" not in prod[0].must_survive
    # no references are attached on the hook (identity not anchored)
    assert prod[0].reference_ids == []


def test_crocs_hook_does_not_assert_product_absent():
    plan = _plan("crocs")
    names = _inv_names(plan, "slide:0")
    assert "product_absent_on_hook" not in names, names
    assert "promoted_identity_withheld_on_hook" in names, names


def test_crocs_hook_request_shows_product_not_removes_it():
    req = _request(_plan("crocs"), 0)
    assert "must be visible in this frame" in req
    assert "Do NOT show the promoted product" not in req
    assert "must NOT appear" not in req
    assert "kept hidden" not in req and "stays absent" not in req


# ---------------------------------------- genuine absence still withholds (control)
def test_colgate_hook_still_withholds_absent_product():
    plan = _plan("colgate")
    s0 = _slide(plan, 0)
    assert s0.promoted_product_allowed is False
    assert "product_absent_on_hook" in _inv_names(plan, "slide:0")
    req = _request(plan, 0)
    assert "Do NOT show the promoted product" in req


def test_ninja_hook_still_withholds_absent_product():
    plan = _plan("ninja")
    s0 = _slide(plan, 0)
    assert s0.promoted_product_allowed is False
    assert "product_absent_on_hook" in _inv_names(plan, "slide:0")


# ------------------------------------------------ reveal still anchors identity
def test_crocs_reveal_anchors_product_identity():
    plan = _plan("crocs")
    s1 = _slide(plan, 1)             # reveal
    assert s1.promoted_product_allowed is True
    assert s1.promoted_identity_revealed is True
    prod = [e for e in s1.elements if e.kind == "product"]
    assert prod and "identity" in prod[0].must_survive


def test_ninja_reveal_anchors_product_identity():
    plan = _plan("ninja")
    s1 = _slide(plan, 1)             # reveal
    assert s1.promoted_product_allowed is True
    assert s1.promoted_identity_revealed is True
    prod = [e for e in s1.elements if e.kind == "product"]
    assert prod and "identity" in prod[0].must_survive


# ------------------------- follow-up 1: reveal without detection = explicit conflict
def test_reveal_without_detection_records_conflict_not_silent_presence():
    """A reveal beat with no detected appearance must NOT masquerade as observed
    presence: the requirement may still require the product, but the evidence
    record must be truthful (observed=False, required=True, explicit conflict)."""
    src = _synthetic_source(
        beats={0: "hook", 1: "reveal"},
        per_slide_detected={0: False, 1: False},   # reveal (idx 1) has NO detection
    )
    plan = build_plan(src, "synthaaaa")
    s1 = _slide(plan, 1)
    # the requirement may still require the product to appear ...
    assert s1.promoted_product_allowed is True
    # ... but there is NO detected product to anchor, so NO product element / references
    assert [e for e in s1.elements if e.kind == "product"] == []
    # and the evidence record is truthful: an explicit conflict is provenance-recorded
    prov = " ".join(f"{p.decision} {p.detail}" for p in s1.provenance)
    assert "product_presence_conflict" in prov, prov
    assert "observed_visual_presence=False" in prov and "required_visual_presence=True" in prov, prov


def test_detected_reveal_has_no_false_conflict():
    """A reveal WITH detection is observed-present and carries no conflict."""
    src = _synthetic_source(beats={0: "hook", 1: "reveal"},
                            per_slide_detected={0: False, 1: True})
    plan = build_plan(src, "synthaaaa")
    s1 = _slide(plan, 1)
    prov = " ".join(f"{p.decision} {p.detail}" for p in s1.provenance)
    assert "product_presence_conflict" not in prov
    assert "observed_visual_presence=True" in prov


# ------------------------- follow-up 2: curiosity mechanism survives on the Crocs hook
def test_crocs_hook_preserves_curiosity_via_identity_withheld():
    """Removing the false deletion cue must NOT remove the curiosity mechanism:
    the Crocs hook keeps a curiosity relationship, now via identity concealment."""
    plan = _plan("crocs")
    att = derive_attention(plan, brief_from_plan(plan))
    a0 = next(s for s in att.slides if s.slide_index == 0)
    rel_names = {r.relationship for r in a0.communication_relationships}
    # product is visible -> it is NOT "withheld" (absent) ...
    assert "product_withheld" not in rel_names, rel_names
    # ... but the promoted identity IS withheld -> curiosity preserved
    assert "promoted_identity_withheld" in rel_names, rel_names


def test_colgate_hook_curiosity_is_true_product_withheld():
    """A genuinely absent hook still uses product_withheld (visual absence)."""
    plan = _plan("colgate")
    att = derive_attention(plan, brief_from_plan(plan))
    a0 = next(s for s in att.slides if s.slide_index == 0)
    rel_names = {r.relationship for r in a0.communication_relationships}
    assert "product_withheld" in rel_names, rel_names
    assert "promoted_identity_withheld" not in rel_names, rel_names
