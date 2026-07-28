"""
Manifest integrity — the manifest is a VERIFIED record of what translation actually
did, not a self-asserted claim.

Every entry is symmetric and typed:
  * encoded  → exactly one declared realization (text | attachment | collective | noop),
               and NO reason;
  * unsupported → exactly one reason, and NO realization.
A `text` realization's fragment must actually appear in the provider request. The
validator SWITCHES on the realization kind — it never infers it from optional fields.

Deterministic, synthetic + fixture driven, no paid calls.
"""
from tests.fixtures.transformation.snapshot_source import SnapshotAnalysisSource
from app.transformation.plan_builder import build_plan
from app.transformation.attention import derive_attention
from app.transformation.generation_spec import (
    assemble_generation_spec, SlideGenerationSpec, SpecText, SpecScene, SpecAttention, SpecCanvas)
from app.transformation.generation_request import (
    validate_request_manifest, ManifestEntry, RequestManifest, Realization, Requirement, ReqId)
from app.transformation.adapters.nano_banana_prompt_adapter import NanoBananaPromptAdapter
from run_three_families import brief_from_plan


def _fails(checks):
    return [c.name for c in checks if c.status == "fail"]


# ------------------------------------------------------ the phantom is now caught
def test_phantom_encoding_without_realization_is_rejected():
    """An encoded entry with no realization (the old phantom) must FAIL validation."""
    scene = SpecScene(False, None, None, None, (), "", "", "")
    attn = SpecAttention((), (), (), "calm", (), False)
    spec = SlideGenerationSpec(0, False, (), (), scene, attn, (),
                               SpecCanvas("3:4", None, None, None, "target_only"))
    # hand-build a manifest whose entries claim encoded but declare no realization
    phantom = RequestManifest(0, tuple(
        ManifestEntry(r, "encoded") for r in __import__(
            "app.transformation.generation_request", fromlist=["slide_requirements"]
        ).slide_requirements(spec)), ())
    assert any("has a realization" in n for n in _fails(validate_request_manifest(spec, phantom)))


def test_decorative_none_is_now_a_declared_noop_and_accepted():
    """The render_text 'none' case is realized as an explicit noop — accepted BECAUSE declared."""
    scene = SpecScene(False, None, None, None, (), "", "", "")
    attn = SpecAttention((), (), (), "calm", (), False)
    txt = SpecText("t0", "DECOR", "render_in_asset", "none", None, "")
    spec = SlideGenerationSpec(0, False, (), (txt,), scene, attn, (),
                               SpecCanvas("3:4", None, None, None, "target_only"))
    out = NanoBananaPromptAdapter().write(spec)
    e = next(x for x in out.manifest.entries if x.requirement.id.kind == "render_text")
    assert e.status == "encoded" and e.realization.kind == "noop", (e.status, e.realization)
    assert not _fails(validate_request_manifest(spec, out.manifest, out.provider_request))


# ------------------------------------------------------ symmetric status invariant
def test_unsupported_forbids_realization_and_requires_reason():
    req = Requirement(ReqId("gap", "x"), (("reason", "y"),))
    # unsupported carrying a realization → fail
    bad = RequestManifest(0, (ManifestEntry(req, "unsupported", reason="r",
                                            realization=Realization("text", "z")),), ())
    # (bijection will also complain, but the symmetric check must fire)
    assert any("carries no realization" in n for n in _fails(
        validate_request_manifest(_min_spec(), bad)))
    # unsupported with no reason → fail
    bad2 = RequestManifest(0, (ManifestEntry(req, "unsupported", reason=""),), ())
    assert any("has a reason" in n for n in _fails(validate_request_manifest(_min_spec(), bad2)))


def test_encoded_forbids_reason():
    req = Requirement(ReqId("gap", "x"), (("reason", "y"),))
    bad = RequestManifest(0, (ManifestEntry(req, "encoded", reason="oops",
                                            realization=Realization("noop", "n")),), ())
    assert any("carries no reason" in n for n in _fails(validate_request_manifest(_min_spec(), bad)))


def _min_spec():
    return SlideGenerationSpec(0, False, (), (), SpecScene(False, None, None, None, (), "", "", ""),
                               SpecAttention((), (), (), "calm", (), False), (),
                               SpecCanvas("3:4", None, None, None, "target_only"))


# ------------------------------------------------------ realized kinds present in fixtures
def test_reference_realizes_as_attachment_and_overlay_as_collective():
    """Non-text realizations are typed, not phantoms: reference → attachment."""
    from app.transformation.generation_spec import SpecProduct
    prod = SpecProduct("p", "P", ("refA",), True)
    scene = SpecScene(False, None, None, None, (), "", "", "")
    attn = SpecAttention((), (), (), "calm", (), False)
    spec = SlideGenerationSpec(0, True, (prod,), (), scene, attn, (),
                               SpecCanvas("3:4", None, None, None, "target_only"))
    out = NanoBananaPromptAdapter().write(spec)
    ref = next(x for x in out.manifest.entries if x.requirement.id.kind == "reference")
    assert ref.status == "encoded" and ref.realization.kind == "attachment", ref.realization
    assert not _fails(validate_request_manifest(spec, out.manifest, out.provider_request))


# ------------------------------------------------------ whole corpus verifies with realization
def test_all_fixtures_pass_realization_verification_against_the_request():
    for name in ["ninja", "colgate", "crocs", "posture"]:
        src = SnapshotAnalysisSource.load(name)
        plan = build_plan(src, src._s["slideshow_id"][:8])
        att = derive_attention(plan, brief_from_plan(plan))
        spec = assemble_generation_spec(plan, att, {})
        for s in spec.slides:
            out = NanoBananaPromptAdapter().write(s)
            fails = _fails(validate_request_manifest(s, out.manifest, out.provider_request))
            assert not fails, (name, s.slide_index, fails)
            # every encoded entry has a realization; every unsupported has a reason and none
            for e in out.manifest.entries:
                if e.status == "encoded":
                    assert e.realization is not None and not e.reason
                else:
                    assert e.reason and e.realization is None


def test_text_realizations_actually_appear_in_the_request():
    """A recorded text fragment is really in the provider request (non-fragile GATE 5)."""
    src = SnapshotAnalysisSource.load("crocs")
    plan = build_plan(src, src._s["slideshow_id"][:8])
    att = derive_attention(plan, brief_from_plan(plan))
    spec = assemble_generation_spec(plan, att, {})
    for s in spec.slides:
        out = NanoBananaPromptAdapter().write(s)
        for e in out.manifest.entries:
            if e.status == "encoded" and e.realization.kind == "text":
                assert e.realization.payload in out.provider_request, e.realization.payload
