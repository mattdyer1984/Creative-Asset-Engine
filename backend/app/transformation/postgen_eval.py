"""
Post-generation evaluation — the SAME evaluation for every creative family.

Reads a generated image + the typed RequestManifest and decides what the result
actually satisfied. Two kinds of check:

  * DETERMINISTIC (run anywhere): technical usability, and manifest reconciliation
    — every `encoded` requirement is expected in the image; every `unsupported`
    requirement MUST be handled by a declared alternate path (overlay handoff,
    composite layer, or reference provision), never silently dropped.
  * PERCEPTUAL (needs a vision model): creative-contract preservation, immediate
    communication clarity, fidelity, overlay-zone cleanliness, originality. Each
    is expressed as a precise yes/no question + the evidence to cite, so a VLM
    scorer returns a comparable verdict across all three families.

`evaluate(...)` runs the deterministic checks immediately and, if a
`vlm_score(question:str, image_path:str, refs:list[str]) -> (bool, str)` callable
is supplied, the perceptual ones too. No provider is imported here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


SHARED_CRITERIA = (
    "creative_contract_preservation",
    "immediate_communication_clarity",
    "fidelity_product_reference_text",
    "overlay_readiness",
    "visual_originality",
    "technical_usability",
)

# The owning-layer taxonomy failures are classified against (source of truth = image).
OWNING_LAYERS = ("Analysis", "Ownership", "Attention", "GenerationSpecification",
                 "Adapter", "Provider limitation")

# A failed criterion's MOST LIKELY owning layer(s) — a starting hypothesis to confirm
# against the generated image, not a verdict. Cross-family recurrence promotes to architecture.
_CRITERION_LAYERS = {
    "creative_contract_preservation": ("Attention", "Adapter"),
    "immediate_communication_clarity": ("Analysis", "Adapter", "Provider limitation"),
    "fidelity_product_reference_text": ("Analysis", "Adapter", "Provider limitation"),
    "overlay_readiness": ("Adapter", "Provider limitation"),
    "visual_originality": ("Adapter", "Provider limitation"),
    "technical_usability": ("Adapter", "Provider limitation"),
    "product_is_dominant": ("Attention", "Adapter"),
    "product_identity_match": ("Analysis", "Provider limitation"),
    "two_subjects_present": ("Analysis", "Attention"),
    "subjects_equal_weight": ("Attention", "GenerationSpecification"),
    "comparison_legible": ("Attention", "Adapter"),
    "subject_hierarchy_clear": ("Analysis", "Attention"),
    "explanatory_reads": ("Analysis", "Adapter"),
    "no_garbled_baked_text": ("GenerationSpecification", "Provider limitation"),
}


@dataclass
class CriterionResult:
    criterion: str
    kind: str                       # deterministic | perceptual
    status: str                     # pass | fail | needs_vlm | n/a
    evidence: str = ""
    question: str = ""              # for perceptual criteria: the exact VLM question
    candidate_layers: tuple = ()    # if this fails, the layer(s) to suspect first


@dataclass
class Evaluation:
    family: str
    slide_index: int
    results: list[CriterionResult] = field(default_factory=list)

    def add(self, *a, **k):
        self.results.append(CriterionResult(*a, **k))

    @property
    def failed(self):
        return [r for r in self.results if r.status == "fail"]

    @property
    def pending(self):
        return [r for r in self.results if r.status == "needs_vlm"]


def _image_dims(image_path: str):
    try:
        from PIL import Image
        with Image.open(image_path) as im:
            return im.size          # (w, h)
    except Exception:
        return None


def _reconcile_manifest(entry: dict, ev: Evaluation):
    """Every unsupported requirement must map to a declared alternate execution path."""
    handoff_refs = {t["ref"] for t in entry.get("overlay_handoff", [])}
    for u in entry["manifest"]["unsupported"]:
        uid, reason = u["id"], u["reason"]
        kind = uid.split(":", 1)[0]
        if kind == "render_text":
            # exact/reference text the model can't guarantee -> composite layer must supply it
            ev.add(f"unsupported::{uid}", "deterministic", "needs_vlm",
                   f"must be satisfied by COMPOSITE layer, not generation: {reason}")
        elif kind == "overlay_exclusion" or uid.split(":", 1)[1] in handoff_refs:
            ev.add(f"unsupported::{uid}", "deterministic", "pass",
                   "declared overlay handoff — added by creator after generation")
        elif kind == "product_identity" or kind == "reference":
            ev.add(f"unsupported::{uid}", "deterministic", "fail",
                   f"identity/reference could not be anchored — provide a reference asset before generating: {reason}")
        elif kind == "gap":
            ev.add(f"unsupported::{uid}", "deterministic", "needs_vlm",
                   f"acknowledged upstream gap — verify by eye whether it mattered: {reason}")
        else:
            ev.add(f"unsupported::{uid}", "deterministic", "needs_vlm", reason)


# Creative-specific perceptual questions (added ON TOP of the shared criteria).
_CREATIVE_QUESTIONS = {
    "product-led reveal": [
        ("product_is_dominant", "Is the promoted product the single dominant focal point of the image?"),
        ("product_identity_match", "Does the product match the attached reference exactly (shape, colour, proportions)?"),
    ],
    "comparison / identity": [
        ("two_subjects_present", "Are there exactly two human subjects, both clearly visible?"),
        ("subjects_equal_weight", "Do the two subjects read as equally important (neither dominates by size/placement)?"),
        ("comparison_legible", "Is a side-by-side A/B comparison relationship immediately obvious?"),
    ],
    "educational": [
        ("subject_hierarchy_clear", "Is the illustrated subject and what it depicts immediately clear?"),
        ("explanatory_reads", "Would the explanatory point read in under one second on a phone?"),
        ("no_garbled_baked_text", "Is there any garbled/nonsense baked-in text that a viewer would notice at a glance?"),
    ],
}


def _family_key(family: str) -> str:
    f = family.lower()
    if "reveal" in f:
        return "product-led reveal"
    if "comparison" in f or "identity" in f:
        return "comparison / identity"
    if "educational" in f or "posture" in f or "infographic" in f:
        return "educational"
    return ""


def evaluate(entry: dict, image_path: Optional[str] = None,
             vlm_score: Optional[Callable[[str, str, list], tuple]] = None) -> Evaluation:
    ev = Evaluation(entry["family"], entry["slide_index"])
    fam = _family_key(entry["family"])

    # ---- technical usability (deterministic) --------------------------------
    if image_path:
        dims = _image_dims(image_path)
        if dims is None:
            ev.add("technical_usability", "deterministic", "fail", "image not readable / corrupt")
        else:
            w, h = dims
            ratio = round(h / w, 3) if w else 0
            ok = h > w and abs(ratio - 16 / 9) < 0.12 and min(w, h) >= 768
            ev.add("technical_usability", "deterministic", "pass" if ok else "fail",
                   f"{w}x{h}, ratio h/w={ratio} (target ~1.778, vertical, >=768 short side)")
    else:
        ev.add("technical_usability", "deterministic", "needs_vlm", "no image yet — run local generation")

    # ---- manifest reconciliation (deterministic) ----------------------------
    _reconcile_manifest(entry, ev)

    # ---- perceptual shared criteria -----------------------------------------
    invariants = [r["ref"] for r in entry["requirements"] if r["kind"] == "invariant"]
    perceptual = [
        ("creative_contract_preservation",
         f"Does the image preserve ALL of these invariants: {invariants}?"),
        ("immediate_communication_clarity",
         "Does the core message read within one second at phone size?"),
        ("fidelity_product_reference_text",
         "Are product identity and any reference/exact text faithful (or absent if none required)?"),
        ("overlay_readiness",
         "Are the reserved zones actually clear AND is there NO baked-in overlay/caption/price text?"),
        ("visual_originality",
         "Is the image visibly different from a generic/stock source framing (would it evade a duplicate filter)?"),
    ]
    for crit, q in perceptual + _CREATIVE_QUESTIONS.get(fam, []):
        layers = _CRITERION_LAYERS.get(crit, ())
        if vlm_score and image_path:
            ok, why = vlm_score(q, image_path, [])
            ev.add(crit, "perceptual", "pass" if ok else "fail", why, question=q, candidate_layers=layers)
        else:
            ev.add(crit, "perceptual", "needs_vlm", "", question=q, candidate_layers=layers)
    return ev


def group_failures_by_layer(evals: list) -> dict:
    """Given evaluations across families, group failed criteria by candidate owning layer.
    A layer appearing across >1 family is the signal for a provider-independent change."""
    by_layer = {layer: [] for layer in OWNING_LAYERS}
    for ev in evals:
        for r in ev.failed:
            for layer in (r.candidate_layers or ("Adapter",)):
                by_layer.setdefault(layer, []).append(f"{ev.family}:{r.criterion}")
    return {k: v for k, v in by_layer.items() if v}


def render(ev: Evaluation) -> str:
    lines = [f"### {ev.family} (slide {ev.slide_index})"]
    for r in ev.results:
        mark = {"pass": "PASS", "fail": "FAIL", "needs_vlm": "VLM?", "n/a": " n/a"}[r.status]
        layer = f"  <owning-layer candidates: {', '.join(r.candidate_layers)}>" if (
            r.candidate_layers and r.status in ("fail", "needs_vlm")) else ""
        lines.append(f"  [{mark}] {r.criterion} ({r.kind}) {('- ' + r.evidence) if r.evidence else ''}{layer}")
        if r.question and r.status == "needs_vlm":
            lines.append(f"         Q: {r.question}")
    return "\n".join(lines)
