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
from typing import Any, Optional
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


# How an ENCODED requirement was actually realized into the provider request. Recorded
# at the point of realization (adapter enc()), never reconstructed afterwards. Typed so
# the validator SWITCHES on the mechanism instead of inferring it from optional fields.
REALIZATION_KINDS = {
    "text",        # a provider-facing text fragment (payload = the emitted fragment; must appear in the request)
    "attachment",  # realized as an attached asset, not text (payload = the attachment ref)
    "collective",  # realized by a shared/global directive, not a per-entry line (payload = a marker)
    "noop",        # an intentional no-op — deliberately nothing to render (payload = why it is a no-op)
}


@dataclass(frozen=True)
class Realization:
    kind: str                 # one of REALIZATION_KINDS
    payload: str = ""


@dataclass(frozen=True)
class ManifestEntry:
    requirement: Requirement
    status: str                              # encoded | unsupported
    reason: str = ""                         # unsupported ONLY (forbidden on encoded)
    realization: Optional[Realization] = None  # encoded ONLY (forbidden on unsupported)


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
    if s.canvas:
        reqs.append(_r("canvas", "slide", output_aspect=s.canvas.output_aspect,
                       source_aspect=(s.canvas.source_aspect or "")))
    if sc.concept:
        reqs.append(_r("scene_concept", "scene", concept=sc.concept))
    reqs.append(_r("subject_presence", "subject", present=sc.subject_present,
                   extent=(sc.subject_extent or "")))
    if sc.subject_present and sc.subject_action:
        reqs.append(_r("subject_action", "subject", action=sc.subject_action))
    if sc.subject_present and sc.product_subject_relation:
        reqs.append(_r("subject_product_relation", "subject",
                       relation=sc.product_subject_relation))
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


def validate_request_manifest(spec: SlideGenerationSpec, manifest: RequestManifest,
                              provider_request: Any = None) -> list[Check]:
    """Manifest integrity.

    CANONICAL INVARIANT — every entry is a TOTAL PARTITION with no legal third state:
        encoded      => exactly one realization,  and no reason
        unsupported  => exactly one reason,        and no realization
    An entry that satisfies neither branch (encoded-without-realization,
    unsupported-without-reason, or a branch carrying the other's field) is invalid.

    Checks: (1) identities are EXACTLY the slide's requirement identities, each once
    with a valid status; (2) the partition above holds for every entry; (3) when the
    provider request is supplied, a `text` realization's fragment actually appears in
    it (the non-fragile successor to GATE 5's substring probe). The validator SWITCHES
    on the realization kind — it never infers the mechanism from optional fields.

    Scope note: this verifies the RECORDED realization against its declared kind; it
    does not claim to verify every conceivable provider behaviour."""
    checks: list[Check] = []
    required = {r.id for r in slide_requirements(spec)}
    accounted = {e.requirement.id for e in manifest.entries}
    for rid in sorted(required, key=lambda x: (x.kind, x.ref)):
        checks.append(Check(f"accounted {rid.kind}:{rid.ref}", "pass" if rid in accounted else "fail"))
    for rid in sorted(accounted - required, key=lambda x: (x.kind, x.ref)):
        checks.append(Check(f"extraneous {rid.kind}:{rid.ref}", "fail"))
    if len(manifest.entries) != len(accounted):
        checks.append(Check("duplicate manifest entries", "fail"))

    req_text = provider_request if isinstance(provider_request, str) else None
    for e in manifest.entries:
        tag = f"{e.requirement.id.kind}:{e.requirement.id.ref}"
        if e.status == "encoded":
            # encoded REQUIRES exactly one realization, and FORBIDS a reason
            if e.realization is None:
                checks.append(Check(f"encoded {tag} has a realization", "fail", "missing realization"))
            elif e.realization.kind not in REALIZATION_KINDS:
                checks.append(Check(f"encoded {tag} realization kind valid", "fail", e.realization.kind))
            elif e.reason:
                checks.append(Check(f"encoded {tag} carries no reason", "fail", e.reason))
            elif e.realization.kind == "text" and not e.realization.payload:
                checks.append(Check(f"encoded {tag} text realization non-empty", "fail"))
            elif e.realization.kind == "text" and req_text is not None \
                    and e.realization.payload not in req_text:
                checks.append(Check(f"encoded {tag} text realization present in request", "fail",
                                    e.realization.payload[:40]))
        elif e.status == "unsupported":
            # unsupported REQUIRES a reason, and FORBIDS a realization
            if not e.reason:
                checks.append(Check(f"unsupported {tag} has a reason", "fail", "missing reason"))
            if e.realization is not None:
                checks.append(Check(f"unsupported {tag} carries no realization", "fail",
                                    e.realization.kind))
        else:
            checks.append(Check(f"status invalid {tag}", "fail", e.status))
    return checks
