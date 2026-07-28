"""
Enforcement family #4 — upstream subject-evidence integrity.

The visible body region, the OBSERVED action, and the product relationship must
survive faithfully from the analysis scene regions into the provider request:

  * extent preserves what is actually visible (a hand is not a full person);
  * the observed action names the object analysis actually reports (a banknote
    stays a banknote — it is never silently renamed "the product");
  * product_subject_relation is bound ONLY when the evidence explicitly links the
    interaction to the promoted product; otherwise it is None (a gap state).

Deterministic, portable-fixture driven, no paid calls.
"""
from tests.fixtures.transformation.snapshot_source import SnapshotAnalysisSource
from app.transformation.plan_builder import build_plan, _subject_from_regions
from app.transformation.attention import derive_attention
from app.transformation.generation_spec import assemble_generation_spec
from app.transformation.adapters.nano_banana_prompt_adapter import NanoBananaPromptAdapter
from run_three_families import brief_from_plan


def _slide(name, idx):
    src = SnapshotAnalysisSource.load(name)
    plan = build_plan(src, src._s["slideshow_id"][:8])
    att = derive_attention(plan, brief_from_plan(plan))
    spec = assemble_generation_spec(plan, att, {})
    s = next(s for s in spec.slides if s.slide_index == idx)
    return s.scene, NanoBananaPromptAdapter().write(s).provider_request


# --------------------------------------------------------------- extent survives
def test_ninja_hand_is_not_a_full_person():
    sc, req = _slide("ninja", 1)
    assert sc.subject_extent == "hand", sc.subject_extent
    assert "hand" in req and "A person is present" not in req


def test_colgate_hand_not_dropped():
    sc, req = _slide("colgate", 0)
    assert sc.subject_present and sc.subject_extent == "hand", sc.subject_extent
    assert "No human subject" not in req


def test_crocs_hand_extent_is_hand_and_forearm():
    sc, req = _slide("crocs", 1)
    assert sc.subject_present and sc.subject_extent == "hand and forearm", sc.subject_extent
    assert "No human subject" not in req


def test_crocs_legs_extent_is_lower_legs():
    sc, req = _slide("crocs", 2)
    assert sc.subject_extent == "lower legs", sc.subject_extent


# ------------------------------------------------- entity binding: action vs relation
def test_colgate_banknote_is_not_renamed_the_product():
    """The hand holds a £20 note, not the promoted Colgate product."""
    sc, req = _slide("colgate", 0)
    # observed action names the banknote, faithfully
    assert sc.subject_action and "note" in sc.subject_action.lower(), sc.subject_action
    assert "product" not in (sc.subject_action or "").lower(), sc.subject_action
    # NO product relationship is asserted (the note is a prop, not the product)
    assert sc.product_subject_relation is None, sc.product_subject_relation
    # and the request never claims the product is held by the subject
    assert "The promoted product is held" not in req


def test_ninja_hand_holds_the_product():
    sc, req = _slide("ninja", 1)
    assert sc.product_subject_relation == "holding", sc.product_subject_relation
    assert sc.subject_action and "tub" in sc.subject_action.lower(), sc.subject_action
    assert "held in the subject's hand" in req


def test_crocs_hand_holds_the_product():
    sc, req = _slide("crocs", 1)
    assert sc.product_subject_relation == "holding", sc.product_subject_relation
    assert "held in the subject's hand" in req


def test_crocs_legs_wear_the_product():
    sc, req = _slide("crocs", 2)
    assert sc.product_subject_relation == "wearing", sc.product_subject_relation
    assert "worn by the subject" in req
    assert "holding and presenting" not in req


# ------------------------------------------- synthetic regressions (no fixture needed)
def _regions(*notes):
    return [{"region_type": "human_subject", "notes": n} for n in notes]


def test_face_plus_hand_is_not_full_figure():
    """Mixed face + hand regions must not collapse to a whole person."""
    present, extent, action, relation = _subject_from_regions(_regions(
        "Close selfie of the subject's face and head, smiling at the camera.",
        "A single raised hand near the cheek, gesturing.",
    ))
    assert present
    assert extent != "full figure", extent
    assert extent == "face and hand", extent


def test_non_product_props_are_never_renamed_the_product():
    """Banknotes, phones, and shopping bags must stay themselves, with no relation."""
    for note, keyword in [
        ("Hand holding a smartphone up towards the camera.", "smartphone"),
        ("Hand clutching a shopping bag by its handles.", "bag"),
        ("Fingers holding a folded banknote / £20 note.", "banknote"),
        ("A hand gripping a leather wallet.", "wallet"),
    ]:
        present, extent, action, relation = _subject_from_regions(_regions(note))
        assert present, note
        assert action and keyword in action.lower(), (note, action)
        assert "the product" not in (action or "").lower(), (note, action)
        assert relation is None, (note, relation)


def test_explicit_product_hold_binds_relation():
    """When analysis names 'the product', the relation IS bound."""
    present, extent, action, relation = _subject_from_regions(_regions(
        "Hand and forearm holding and presenting the product to the camera.",
    ))
    assert present
    assert relation == "holding", relation
    assert extent == "hand and forearm", extent
