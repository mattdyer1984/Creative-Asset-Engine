"""
Provider-independent request contract, typed with identity + payload.

  ReqId(kind, ref)         — stable identity (used for exact-set accounting)
  Requirement(id, payload) — identity + an immutable semantic payload the adapter
                             must translate (e.g. the actual canonical text, the
                             actual scene concept, the owning reference target)

The manifest is exactly bijective with requirement IDENTITIES; each entry is
`encoded` or `unsupported` (single concept, with a reason). Nothing here claims
the provider realised anything. Names no provider; imports no adapter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from .generation_spec import SlideGenerationSpec


@dataclass(frozen=True)
class ReqId:
    kind: str
    ref: str


@dataclass(frozen=True)
class Requirement:
    id: ReqId
    payload: tuple            # ((key, value), ...) — immutable, structured; NOT colon-packed strings

    def get(self, key: str, default=None):
        return dict(self.payload).get(key, default)


@dataclass(frozen=True)
class ManifestEntry:
    requirement: Requirement
    status: str               # encoded | unsupported
    reason: str = ""


@dataclass(frozen=True)
class RequestManifest:
    slide_index: int
    entries: tuple
    variations_requested: tuple


@dataclass(frozen=True)
class AdapterOutput:
    slide_index: int
    provider_name: str
    provider_request: Any     # OPAQUE
    manifest: RequestManifest


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""


def _r(kind, ref, **payload):
    return Requirement(ReqId(kind, ref), tuple(sorted(payload.items())))


def slide_requirements(s: SlideGenerationSpec) -> tuple:
    """Every executable field of the slide as a requirement with an immutable payload."""
    reqs: list[Requirement] = []
    sc = s.scene
    if sc.concept:
        reqs.append(_r("scene_concept", "scene", concept=sc.concept))
    reqs.append(_r("subject_presence", "subject", present=sc.subject_present))
    if sc.subject_present and sc.subject_action:
        reqs.append(_r("subject_action", "subject", action=sc.subject_action))
    if sc.subject_present and sc.subject_emotion:
        reqs.append(_r("subject_emotion", "subject", emotion=tuple(sc.subject_emotion)))
    if sc.environment:
        reqs.append(_r("environment", "scene", environment=sc.environment))
    if sc.lighting:
        reqs.append(_r("lighting", "scene", lighting=sc.lighting))
    reqs.append(_r("dynamics", "slide", energy=s.attention.dynamics))
    reqs.append(_r("product_presence", "slide", product_allowed=s.product_allowed))
    for (ref, weight) in s.attention.focal_order:
        if weight in ("primary", "absent"):
            reqs.append(_r("focal", ref, element=ref, weight=weight))
    for inv in s.attention.contract_invariants:
        reqs.append(_r("invariant", inv, statement=inv))
    seen_openings = set()
    for (purpose, zone, strictness) in s.attention.openings:
        # An opening is a zone-reservation intent; several texts sharing a purpose
        # still reserve ONE zone. Collapse duplicates so identities stay unique.
        key = (purpose, zone)
        if key in seen_openings:
            continue
        seen_openings.add(key)
        reqs.append(_r("opening", f"{purpose}@{zone}", purpose=purpose, zone=zone, strictness=strictness))
    for t in s.texts:
        if t.disposition == "overlay_handoff":
            reqs.append(_r("overlay_exclusion", t.ref, text=t.text))
        elif t.disposition == "render_in_asset":
            reqs.append(_r("render_text", t.ref, fidelity=t.fidelity_required, text=t.text,
                           owner=(t.reference_target or "")))
        else:
            reqs.append(_r("gap", f"text:{t.ref}", reason="text execution unresolved"))
    for p in s.products:
        if p.identity_required:
            reqs.append(_r("product_identity", p.ref, label=p.label))
        for rid in p.reference_ids:
            reqs.append(_r("reference", f"{p.ref}/{rid}", product=p.ref, reference_id=rid))
    for g in s.gaps:
        if not g.startswith(tuple(t.ref for t in s.texts)):   # text gaps already enumerated above
            reqs.append(_r("gap", g, reason=g))
    return tuple(reqs)


def validate_request_manifest(spec: SlideGenerationSpec, manifest: RequestManifest) -> list[Check]:
    """Completeness only: manifest identities are EXACTLY the slide's requirement identities,
    each with a valid status. (Translation correctness is proven adapter-side.)"""
    checks: list[Check] = []
    required = {r.id for r in slide_requirements(spec)}
    accounted = {e.requirement.id for e in manifest.entries}
    for rid in sorted(required, key=lambda x: (x.kind, x.ref)):
        checks.append(Check(f"accounted {rid.kind}:{rid.ref}", "pass" if rid in accounted else "fail"))
    for rid in sorted(accounted - required, key=lambda x: (x.kind, x.ref)):
        checks.append(Check(f"extraneous {rid.kind}:{rid.ref}", "fail"))
    for e in manifest.entries:
        if e.status not in ("encoded", "unsupported"):
            checks.append(Check(f"status invalid {e.requirement.id.kind}", "fail", e.status))
    if len(manifest.entries) != len(accounted):
        checks.append(Check("duplicate manifest entries", "fail"))
    return checks
