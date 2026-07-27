"""
Three-family generality test — build the immutable GenerationSpecification, the
provider request and the typed RequestManifest for ONE representative slide of
each creative family. NO PROVIDER CALL is made here (credentials + reference
images live only in the user's environment). This script emits everything the
local generation runbook needs, and a machine-readable dump for the report.

  1. Ninja CREAMi        — product-led reveal      (imported plan, slide 1)
  2. Cologne "VS" ident. — comparison / identity   (hand-built plan, central slide)
  3. Posture infographic — educational             (imported plan, slide 1)

Run: python run_three_families.py
"""
import os, json, re, dataclasses

from app.transformation.analysis_source import AnalysisSource
from app.transformation.plan_builder import build_plan
from app.transformation.attention import derive_attention, BriefItem
from app.transformation.ownership import OwnershipDecision
from app.transformation.plan import (
    TransformationPlan, SlideDirective, SceneDirective, PlanElement, Invariant, Provenance,
)
from app.transformation.generation_spec import assemble_generation_spec
from app.transformation.generation_request import slide_requirements, validate_request_manifest
from app.transformation.adapters.nano_banana_prompt_adapter import NanoBananaPromptAdapter

DB = os.path.join(os.path.dirname(__file__), "data", "creative_asset_engine.db")
OUT = os.path.join(os.path.dirname(__file__), "three_family_requests.json")
_ROLE_TO_PURPOSE = {"headline": "hook_caption", "price": "price_card", "subheadline": "subhead", "cta": "cta"}


def brief_from_plan(plan):
    b = {}
    for s in plan.slides:
        b[s.slide_index] = [BriefItem(_ROLE_TO_PURPOSE.get(e.label.split()[0], "subhead"))
                            for e in s.elements if e.kind == "text" and e.rendering_owner == "composite_layer"]
    return b


def od(region_id, text, cls, conf, alters):
    return OwnershipDecision(region_id, text, cls, conf, alters,
                             "recorded ownership decision", ["recorded_vlm"], [])


# ------------------------------------------------------------------- NINJA
def ninja():
    plan = build_plan(AnalysisSource(DB), "8a1f583a")
    own = {
        "s1_t9":  od("s1_t9", "", "creator_overlay", 0.90, False),
        "s1_t12": od("s1_t12", "", "creator_overlay", 0.85, False),
        "s1_t13": od("s1_t13", "", "creator_overlay", 0.90, False),
        "s1_packaging": od("s1_packaging", "", "product_native", 0.90, True),
    }
    return "Ninja CREAMi — product-led reveal", plan, own, 1


# --------------------------------------------------------------- POSTURE
def posture():
    plan = build_plan(AnalysisSource(DB), "e3fbf713")
    s = plan.slides[1]
    # NOTE: the raw analysis for this slide is deliberately NOT pre-cleaned. It infers a
    # product that is not on the slide and misses the illustrated figure (subject_present
    # False). Per the working model, those are Analysis-layer defects to be discovered via
    # the generated image, not masked beforehand. Ownership only records who owns the
    # baked-in educational copy (design_integral); it does not decide fidelity.
    own = {e.element_id: od(e.element_id, e.verbatim or "", "design_integral", 0.88, True)
           for e in s.elements if e.kind == "text"}
    return "Posture infographic — educational", plan, own, 1


# --------------------------------------------------------------- COLOGNE
def cologne():
    """Hand-built REAL plan for the central comparison slide (DB analysis was incomplete:
    the 'ARABIAN COLOGNE VS BRITISH COLOGNE' creative has OCR but no scene analysis)."""
    prov = [Provenance("hand-built", "operator", "central comparison slide, real OCR + creative")]
    elements = [
        PlanElement("c_product", "product", "Bella Vita cologne", must_survive=["identity"],
                    commercial_importance="high", preservation_mode="product_reference",
                    reference_ids=["2f1b7cb8-e610-409b-ba6d-1d4e6344a840"],   # real Bella Vita front reference
                    provenance=prov),
        PlanElement("c_label_a", "text", "headline text", must_survive=["meaning"],
                    verbatim="ARABIAN COLOGNE", text_status="meaning_preserve",
                    rendering_owner="composite_layer", commercial_importance="medium"),
        PlanElement("c_label_b", "text", "headline text", must_survive=["meaning"],
                    verbatim="VS BRITISH COLOGNE", text_status="meaning_preserve",
                    rendering_owner="composite_layer", commercial_importance="medium"),
        PlanElement("c_react_a", "text", "other text", must_survive=["meaning"],
                    verbatim="YOU SMELL INCREDIBLE, CAN I GET YOUR NUMBER?",
                    text_status="meaning_preserve", rendering_owner="composite_layer"),
        PlanElement("c_react_b", "text", "other text", must_survive=["meaning"],
                    verbatim="I'M NOT INTERESTED.", text_status="meaning_preserve",
                    rendering_owner="composite_layer"),
    ]
    scene = SceneDirective(
        concept="Split A/B comparison: two men in the same setting, each after using a different cologne; "
                "the left man receives an admiring reaction, the right man is rebuffed.",
        subject_present=True, subject_action="reacting to each other after an introduction",
        subject_emotion=["confidence", "attraction", "rejection"],
        environment="A stylish social setting (bar / night-out), two mirrored halves",
        lighting="Warm, flattering evening light, equal on both halves",
        framing="vertical 9:16, balanced left/right split",
        change_directives=["change models", "change venue styling", "change palette", "change camera angle"],
        gaps=["which cologne wins is carried by the overlay captions, not the image alone"],
        provenance=prov,
    )
    slide = SlideDirective(
        slide_index=0, role="comparison", promoted_product_allowed=True, cta_allowed=False,
        scene=scene, elements=elements, originality_levers_required=4, provenance=prov,
    )
    plan = TransformationPlan(
        slideshow_id="cologne-vs-handbuilt", plan_version=1, processing_mode="comparison",
        mechanisms_to_preserve=["identity", "comparison", "desirability"],
        slides=[slide],
        invariants=[Invariant("two_subjects_equal_weight", "slide",
                              {"note": "both men must read as equally important"}, prov)],
    )
    own = {
        "c_label_a": od("c_label_a", "ARABIAN COLOGNE", "creator_overlay", 0.88, False),
        "c_label_b": od("c_label_b", "VS BRITISH COLOGNE", "creator_overlay", 0.88, False),
        "c_react_a": od("c_react_a", "YOU SMELL...", "creator_overlay", 0.90, False),
        "c_react_b": od("c_react_b", "I'M NOT INTERESTED.", "creator_overlay", 0.90, False),
    }
    return "Cologne VS — comparison / identity", plan, own, 0


def req_to_dict(r):
    return {"kind": r.id.kind, "ref": r.id.ref, "payload": dict(r.payload)}


def main():
    adapter = NanoBananaPromptAdapter()
    report = []
    for name, plan, own, idx in (ninja(), cologne(), posture()):
        attention = derive_attention(plan, brief_from_plan(plan))
        spec = assemble_generation_spec(plan, attention, own)
        slide = next(s for s in spec.slides if s.slide_index == idx)
        out = adapter.write(slide)
        checks = validate_request_manifest(slide, out.manifest)
        bad = [(c.name, c.detail) for c in checks if c.status != "pass"]

        enc = [f"{e.requirement.id.kind}:{e.requirement.id.ref}" for e in out.manifest.entries if e.status == "encoded"]
        uns = [(f"{e.requirement.id.kind}:{e.requirement.id.ref}", e.reason)
               for e in out.manifest.entries if e.status == "unsupported"]

        print("=" * 78); print(name, f"(slide {idx})"); print("=" * 78)
        print(out.provider_request)
        print(f"\n  manifest: {len(enc)} encoded, {len(uns)} unsupported; validation "
              f"{'PASS' if not bad else 'FAIL ' + str(bad)} ({len(checks)} checks)")
        for u in uns:
            print(f"    UNSUPPORTED {u[0]}: {u[1]}")
        print(f"  overlay handoff texts (added by creator later): "
              f"{[t.ref for t in slide.texts if t.disposition == 'overlay_handoff']}")
        print(f"  gaps: {list(slide.gaps)}\n")

        report.append({
            "family": name, "slide_index": idx, "slideshow_id": spec.slideshow_id,
            "provider_request": out.provider_request,
            "requirements": [req_to_dict(r) for r in slide_requirements(slide)],
            "manifest": {
                "variations_requested": list(out.manifest.variations_requested),
                "encoded": enc,
                "unsupported": [{"id": u[0], "reason": u[1]} for u in uns],
                "validation_pass": not bad,
            },
            "overlay_handoff": [{"ref": t.ref, "text": t.text} for t in slide.texts
                                if t.disposition == "overlay_handoff"],
            "render_in_asset": [{"ref": t.ref, "fidelity": t.fidelity_required,
                                 "reference_target": t.reference_target, "text": t.text}
                                for t in slide.texts if t.disposition == "render_in_asset"],
            "gaps": list(slide.gaps),
        })

    with open(OUT, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
