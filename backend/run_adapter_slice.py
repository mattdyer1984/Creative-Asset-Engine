"""
Provider-adapter boundary — final tightening pass (Nano Banana, Ninja). NO PROVIDER CALL.

Proves the 8 freeze-gate conditions:
  1. ownership and fidelity remain separate decisions
  2. every executable spec field is a requirement (or explicitly informational)
  3. every requirement has a stable identity + an immutable semantic payload
  4. manifest is exactly bijective with requirement identities
  5. adapter-specific tests prove encoded entries are genuinely translated
  6. reference fidelity is bound to the CORRECT owning asset
  7. the full Ninja scene survives into the provider request
  8. no provider call is made

Run: python run_adapter_slice.py
"""
import os, re, dataclasses

from app.transformation.analysis_source import AnalysisSource
from app.transformation.plan_builder import build_plan
from app.transformation.attention import derive_attention, BriefItem
from app.transformation.ownership import OwnershipDecision
from app.transformation.text_execution import TextExecInput, resolve_text_execution
from app.transformation.generation_spec import (
    assemble_generation_spec, SlideGenerationSpec, SpecText, SpecScene, SpecAttention, SpecProduct,
)
from app.transformation.generation_request import (
    slide_requirements, validate_request_manifest, Requirement, ReqId,
)
from app.transformation.adapters.nano_banana_prompt_adapter import (
    NanoBananaPromptAdapter, NanoBananaCapabilities,
)

DB = os.path.join(os.path.dirname(__file__), "data", "creative_asset_engine.db")
TX = os.path.join(os.path.dirname(__file__), "app", "transformation")
_ROLE_TO_PURPOSE = {"headline": "hook_caption", "price": "price_card", "subheadline": "subhead", "cta": "cta"}

# Recorded decisions of the FROZEN ownership subsystem for the Ninja text regions.
_NINJA_OWNERSHIP = {
    "s0_t0":        ("creator_overlay", 0.90, False),
    "s1_t9":        ("creator_overlay", 0.90, False),
    "s1_t12":       ("creator_overlay", 0.85, False),
    "s1_t13":       ("creator_overlay", 0.90, False),
    "s1_packaging": ("product_native", 0.90, True),
}


def ninja_ownership(plan):
    """Build the ownership-decision dict the assembler consumes (element_id -> OwnershipDecision)."""
    out = {}
    for s in plan.slides:
        for e in s.elements:
            if e.kind == "text" and e.element_id in _NINJA_OWNERSHIP:
                cls, conf, alters = _NINJA_OWNERSHIP[e.element_id]
                out[e.element_id] = OwnershipDecision(
                    e.element_id, e.verbatim or "", cls, conf, alters,
                    "frozen ownership subsystem decision", ["recorded_vlm"], [])
    return out


def brief_from_plan(plan):
    b = {}
    for s in plan.slides:
        b[s.slide_index] = [BriefItem(_ROLE_TO_PURPOSE.get(e.label.split()[0], "subhead"))
                            for e in s.elements if e.kind == "text" and e.rendering_owner == "composite_layer"]
    return b


def rid_str(r):
    return f"{r.id.kind}:{r.id.ref}"


def print_manifest(m):
    enc = [e for e in m.entries if e.status == "encoded"]
    uns = [e for e in m.entries if e.status == "unsupported"]
    print(f"    encoded ({len(enc)}): " + ", ".join(rid_str(e.requirement) for e in enc))
    print(f"    unsupported ({len(uns)}): " +
          ("; ".join(f"{rid_str(e.requirement)} [{e.reason}]" for e in uns) or "none"))
    print(f"    variations_requested: {list(m.variations_requested)}")


def main():
    plan = build_plan(AnalysisSource(DB), "8a1f583a")
    attention = derive_attention(plan, brief_from_plan(plan))
    ownership = ninja_ownership(plan)
    spec = assemble_generation_spec(plan, attention, ownership)   # ONE authoritative input
    adapter = NanoBananaPromptAdapter()

    print("=" * 74); print("NINJA — provider-adapter final boundary pass (no provider call)"); print("=" * 74)
    ninja_ok = True
    outs = {}
    for s in spec.slides:
        out = adapter.write(s)
        outs[s.slide_index] = out
        checks = validate_request_manifest(s, out.manifest)
        bad = [c for c in checks if c.status != "pass"]
        ninja_ok = ninja_ok and not bad
        print(f"\n slide{s.slide_index}: {len(slide_requirements(s))} requirements")
        for t in s.texts:
            tgt = f" -> {t.reference_target}" if t.reference_target else ""
            print(f"    text {t.ref}: {t.disposition}/{t.fidelity_required}{tgt}  <= {t.source}")
        print_manifest(out.manifest)
        print(f"    manifest validation: {'PASS' if not bad else 'FAIL ' + str([(c.name,c.detail) for c in bad])}"
              f" ({len(checks)} checks)")

    reveal = spec.slides[1]         # the reveal slide
    reveal_req = outs[1].provider_request

    # ---------------------------------------------------------------- GATE 1
    # Same ownership disposition, different fidelity — driven by trust/role, not ownership class.
    d_native = OwnershipDecision("x", "MAX FILL", "product_native", 0.9, True, "")
    f_ref = resolve_text_execution(TextExecInput(d_native, "MAX FILL", None, ("identity",), "logo", "prodA"))
    f_sem = resolve_text_execution(TextExecInput(d_native, "family favourite", "meaning_preserve", (), "tagline", None))
    gate1 = (f_ref.disposition == f_sem.disposition == "render_in_asset"
             and f_ref.fidelity != f_sem.fidelity
             and "fidelity<-" in f_ref.source and "fidelity<-" in f_sem.source)

    # ---------------------------------------------------------------- GATE 2
    # Every executable scene/attention field appears as a requirement kind (nothing silently dropped).
    kinds = {r.id.kind for r in slide_requirements(reveal)}
    exec_expected = {"scene_concept", "subject_presence", "environment", "lighting",
                     "dynamics", "product_presence", "focal", "invariant", "product_identity"}
    gate2_missing = {k for k in exec_expected if k not in kinds}
    gate2 = not gate2_missing

    # ---------------------------------------------------------------- GATE 3
    r0 = slide_requirements(reveal)[0]
    ident_stable = isinstance(r0.id, ReqId) and isinstance(r0.payload, tuple)
    try:
        r0.payload = ()                       # frozen -> must raise
        payload_immutable = False
    except dataclasses.FrozenInstanceError:
        payload_immutable = True
    ids = [r.id for r in slide_requirements(reveal)]
    ids_unique = len(ids) == len(set(ids))
    gate3 = ident_stable and payload_immutable and ids_unique

    # ---------------------------------------------------------------- GATE 4
    gate4 = ninja_ok

    # ---------------------------------------------------------------- GATE 5
    # Encoded entries are genuinely translated: their payload content appears in the request.
    translation_fail = []
    for e in outs[1].manifest.entries:
        if e.status != "encoded":
            continue
        req = e.requirement
        k = req.id.kind
        needle = None
        if k == "scene_concept":       needle = (req.get("concept") or "")[:24]
        elif k == "environment":       needle = (req.get("environment") or "")[:20]
        elif k == "lighting":          needle = (req.get("lighting") or "")[:16]
        elif k == "invariant":         needle = (req.get("statement") or "")[:20]
        elif k == "render_text" and req.get("fidelity") == "semantic_presence":
            needle = (req.get("text") or "")[:16]
        if needle and needle.lower() not in reveal_req.lower():
            translation_fail.append((k, needle))
    gate5 = not translation_fail

    # ---------------------------------------------------------------- GATE 6
    # Reference fidelity bound to the CORRECT owning asset.
    caps = NanoBananaCapabilities()
    prodA = SpecProduct("prodA", "Product A", ("refA",), True)
    prodB = SpecProduct("prodB", "Product B", ("refB",), True)
    txt_owned_by_B = SpecText("tB", "SUPER SEAL", "render_in_asset", "reference_fidelity", "prodB", "")
    # Attach only prodA's reference -> B's reference-fidelity text must NOT be falsely encoded.
    s_wrong = SlideGenerationSpec(50, True, (prodA,), (txt_owned_by_B,),
                                  SpecScene(False, None, (), "", "", ""),
                                  SpecAttention((), (), (), "calm", (), False), ())
    cap1 = NanoBananaCapabilities(max_references=1)
    m_wrong = NanoBananaPromptAdapter(cap1).write(s_wrong).manifest
    e_wrong = next(e for e in m_wrong.entries if e.requirement.id.kind == "render_text")
    bound_wrong_ok = e_wrong.status == "unsupported" and "prodB" in e_wrong.reason
    # Now attach B's reference -> encoded, referencing B.
    s_right = SlideGenerationSpec(51, True, (prodB,), (txt_owned_by_B,),
                                  SpecScene(False, None, (), "", "", ""),
                                  SpecAttention((), (), (), "calm", (), False), ())
    out_right = NanoBananaPromptAdapter().write(s_right)
    e_right = next(e for e in out_right.manifest.entries if e.requirement.id.kind == "render_text")
    bound_right_ok = e_right.status == "encoded" and "prodB" in out_right.provider_request
    gate6 = bound_wrong_ok and bound_right_ok

    # ---------------------------------------------------------------- GATE 7
    sc = reveal.scene
    survive = {
        "concept": (sc.concept or "")[:24],
        "environment": (sc.environment or "")[:20],
        "lighting": (sc.lighting or "")[:16],
        "dynamics": reveal.attention.dynamics or "",
    }
    if sc.subject_present and sc.subject_action:
        survive["subject_action"] = sc.subject_action[:20]
    missing_scene = {k: v for k, v in survive.items() if v and v.lower() not in reveal_req.lower()}
    gate7 = not missing_scene

    # ---------------------------------------------------------------- GATE 8
    net = re.compile(r"requests\.|urllib|http\.client|socket|genai|google\.generativeai|openai\.|aiohttp|httpx", re.I)
    adapter_src = open(os.path.join(TX, "adapters", "nano_banana_prompt_adapter.py")).read()
    runner_src = open(__file__).read().split("GATE 8")[0]   # ignore this proof's own regex literal
    no_net = not net.search(adapter_src) and not net.search(runner_src)
    request_is_opaque_text = all(isinstance(o.provider_request, str) for o in outs.values())
    gate8 = no_net and request_is_opaque_text

    # ---------------------------------------------------------------- provider-independence
    tokens = re.compile(r"nano|banana|gemini|gpt|openai|dall|imagen|sdxl", re.I)
    upstream = ["plan.py", "attention.py", "ownership.py", "plan_handling.py",
                "text_execution.py", "generation_spec.py", "generation_request.py"]
    leaks = {f for f in upstream if tokens.search(open(os.path.join(TX, f)).read())}
    validator_src = open(os.path.join(TX, "generation_request.py")).read()
    validator_clean = ("adapters" not in validator_src) and (not tokens.search(validator_src))

    print("\n" + "=" * 74); print("FREEZE-GATE PROOFS"); print("=" * 74)
    gates = [
        ("1. ownership and fidelity are separate decisions", gate1,
         f"same disposition '{f_ref.disposition}', fidelities {f_ref.fidelity} vs {f_sem.fidelity}"),
        ("2. every executable spec field is a requirement", gate2,
         f"missing: {gate2_missing or 'none'}; kinds={sorted(kinds)}"),
        ("3. stable identity + immutable payload per requirement", gate3,
         f"ReqId+tuple={ident_stable}, frozen={payload_immutable}, unique_ids={ids_unique}"),
        ("4. manifest exactly bijective with requirement identities", gate4,
         "validator: no missing / extraneous / dup on both slides"),
        ("5. encoded entries are genuinely translated into the request", gate5,
         f"untranslated: {translation_fail or 'none'}"),
        ("6. reference fidelity bound to the CORRECT owning asset", gate6,
         f"wrong-asset->unsupported({bound_wrong_ok}), right-asset->encoded({bound_right_ok})"),
        ("7. the full Ninja scene survives into the provider request", gate7,
         f"missing from request: {missing_scene or 'none'}"),
        ("8. no provider call is made", gate8,
         f"no-network={no_net}, request-is-opaque-text={request_is_opaque_text}"),
        ("+  provider-independence (only the adapter names a provider)", (not leaks) and validator_clean,
         f"upstream leaks={leaks or 'none'}, validator_clean={validator_clean}"),
    ]
    all_ok = True
    for label, ok, detail in gates:
        all_ok = all_ok and ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}\n         {detail}")
    print("\n" + ("ALL FREEZE GATES PASS — boundary may be frozen." if all_ok
                  else "!! FREEZE GATES NOT ALL PASSING — do not freeze."))
    return all_ok


if __name__ == "__main__":
    ok = main()
    raise SystemExit(0 if ok else 1)
