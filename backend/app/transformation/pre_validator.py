"""
Pre-generation validation — deterministic checks over the Plan alone.
Strengthened (point 5): unique ids, valid enums, no unresolved OCR uncertainty
on critical text, a confirmed deterministic rendering owner for every required
overlay, explicit reserved layout for composited text, CTA expectation, and a
hard Plan-SUFFICIENCY gate (the provider request must build with nothing
unresolved).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .plan import (
    TransformationPlan, MUST_SURVIVE, SHOULD_IMPROVE, COMMERCIAL_IMPORTANCE,
    TEXT_STATUS, RENDERING_OWNER, PRESERVATION_MODE,
)
from .generation_adapter import build_generation_request

_DETERMINISTIC_OWNERS = {"composite_layer", "interface_renderer"}


@dataclass
class Check:
    name: str
    status: str            # "pass" | "fail" | "deferred"
    detail: str = ""


@dataclass
class ValidationResult:
    checks: list[Check] = field(default_factory=list)
    phase: str = "validation"

    @property
    def passed(self) -> bool:
        return not any(c.status == "fail" for c in self.checks)

    def report(self) -> str:
        sym = {"pass": "ok", "fail": "XX", "deferred": "--"}
        head = "PASS" if self.passed else "FAIL"
        lines = [f"{head} ({self.phase})"]
        for c in self.checks:
            lines.append(f"  [{sym[c.status]}] {c.name}{(' — ' + c.detail) if c.detail else ''}")
        return "\n".join(lines)


def _ok(cond, name, detail=""):
    return Check(name, "pass" if cond else "fail", detail)


def validate_pre(plan: TransformationPlan) -> ValidationResult:
    checks: list[Check] = []
    idx = plan.element_index()

    # unique element ids
    ids = [e.element_id for s in plan.slides for e in s.elements]
    checks.append(_ok(len(ids) == len(set(ids)), "element ids are unique",
                      "" if len(ids) == len(set(ids)) else "duplicates present"))

    # valid enum values
    enum_bad = []
    for e in idx.values():
        if not set(e.must_survive) <= MUST_SURVIVE: enum_bad.append(f"{e.element_id}.must_survive")
        if not set(e.should_improve) <= SHOULD_IMPROVE: enum_bad.append(f"{e.element_id}.should_improve")
        if e.commercial_importance not in COMMERCIAL_IMPORTANCE: enum_bad.append(f"{e.element_id}.commercial_importance")
        if e.text_status not in (TEXT_STATUS | {None}): enum_bad.append(f"{e.element_id}.text_status")
        if e.rendering_owner not in (RENDERING_OWNER | {None}): enum_bad.append(f"{e.element_id}.rendering_owner")
        if e.preservation_mode not in (PRESERVATION_MODE | {None}): enum_bad.append(f"{e.element_id}.preservation_mode")
    checks.append(_ok(not enum_bad, "all enum values valid", "" if not enum_bad else str(enum_bad)))

    # provenance on every decision
    noprov = [e.element_id for e in idx.values() if not e.provenance]
    checks.append(_ok(not noprov, "every decision has provenance", "" if not noprov else str(noprov)))

    for s in plan.slides:
        # no unresolved OCR uncertainty on any element demanding exact_text
        uncertain_exact = [e.element_id for e in s.elements
                           if "exact_text" in e.must_survive and e.text_status == "uncertain"]
        checks.append(_ok(not uncertain_exact,
                          f"slide{s.slide_index}: no uncertain OCR required as exact",
                          "" if not uncertain_exact else str(uncertain_exact)))

        # required overlays must have a confirmed deterministic rendering owner
        for eid in s.required_text_element_ids:
            e = idx.get(eid)
            ok = bool(e) and e.rendering_owner in _DETERMINISTIC_OWNERS
            checks.append(_ok(ok, f"slide{s.slide_index}: required '{eid}' has deterministic renderer",
                              "" if ok else f"rendering_owner={getattr(e,'rendering_owner',None)!r}"))
            # each exact commercial value element carries atomic values
            if e and e.text_status == "exact_commercial_value":
                checks.append(_ok(bool(e.commercial_values),
                                  f"slide{s.slide_index}: '{eid}' has atomic commercial values",
                                  str([v["value"] for v in e.commercial_values])))

        # every composite text has an explicit reserved zone
        for e in s.elements:
            if e.kind == "text" and e.rendering_owner == "composite_layer":
                checks.append(_ok(bool(e.reserved_zone),
                                  f"slide{s.slide_index}: composite '{e.element_id}' has reserved zone",
                                  "" if e.reserved_zone else "no text-safe layout"))

        # CTA expectation
        if not s.cta_allowed:
            cta = [e.element_id for e in s.elements if "cta" in e.label.lower()]
            checks.append(_ok(not cta, f"slide{s.slide_index}: no CTA where disallowed",
                              "" if not cta else str(cta)))

        # product only where allowed
        if not s.promoted_product_allowed:
            prod = [e.element_id for e in s.elements if e.kind == "product"]
            checks.append(_ok(not prod, f"slide{s.slide_index}: no product where disallowed",
                              "" if not prod else str(prod)))

        # originality budget
        checks.append(_ok(s.originality_levers_required >= 3,
                          f"slide{s.slide_index}: originality levers required >= 3",
                          f"required={s.originality_levers_required}"))

        # HARD Plan-sufficiency gate: the provider request must build with nothing unresolved
        req = build_generation_request(plan, s.slide_index)
        checks.append(_ok(not req.unresolved,
                          f"slide{s.slide_index}: provider request fully resolved from Plan",
                          "" if not req.unresolved else "; ".join(req.unresolved)))

    # invariants well-formed
    checks.append(_ok(all(inv.name and inv.scope for inv in plan.invariants),
                      "invariants present and named", f"{len(plan.invariants)} invariant(s)"))

    return ValidationResult(checks=checks, phase="pre-generation")
