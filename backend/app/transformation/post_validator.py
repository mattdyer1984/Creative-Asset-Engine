"""
Post-generation validation — derived from the Plan, run against an observed
result. Strengthened (point 5):
  - trusted_exact copy must appear in FULL (canonical), not a 24-char prefix;
  - each exact commercial value is checked INDIVIDUALLY;
  - no_cta is enforced;
  - originality and visual-quality are marked DEFERRED (unproven in Stage A),
    never passed from a hand-entered count.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .plan import TransformationPlan
from .pre_validator import Check, ValidationResult


@dataclass
class ObservedOutput:
    slide_index: int
    detected_text: list[str] = field(default_factory=list)
    product_present: bool = False
    distinct_products: int = 0
    cta_detected: bool = False
    # image-dependent signals are Stage B; left None here on purpose
    originality_levers_changed: int | None = None
    product_identity_ok: bool | None = None


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def validate_post(plan: TransformationPlan, observed: dict[int, ObservedOutput]) -> ValidationResult:
    checks: list[Check] = []
    idx = plan.element_index()

    for s in plan.slides:
        obs = observed.get(s.slide_index)
        if obs is None:
            checks.append(Check(f"slide{s.slide_index}: output present", "fail", "no observed output"))
            continue
        hay = " ".join(_norm(t) for t in obs.detected_text)

        for eid in s.required_text_element_ids:
            e = idx.get(eid)
            if not e:
                continue
            if e.text_status == "trusted_exact" and e.verbatim:
                needle = _norm(e.verbatim)
                ok = needle in hay
                checks.append(Check(f"slide{s.slide_index}: exact copy '{eid}' present in full",
                                    "pass" if ok else "fail",
                                    "" if ok else f"missing/garbled: {e.verbatim[:48]!r}"))
            if e.text_status == "exact_commercial_value":
                for v in e.commercial_values:
                    present = _norm(v["value"]) in hay
                    checks.append(Check(f"slide{s.slide_index}: value {v['value']} present",
                                        "pass" if present else "fail"))

        checks.append(Check(f"slide{s.slide_index}: product presence matches plan",
                            "pass" if obs.product_present == s.promoted_product_allowed else "fail",
                            f"observed={obs.product_present} allowed={s.promoted_product_allowed}"))

        if not s.cta_allowed:
            checks.append(Check(f"slide{s.slide_index}: no CTA present",
                                "pass" if not obs.cta_detected else "fail"))

        # image-dependent — deferred to Stage B, never a fake pass
        checks.append(Check(f"slide{s.slide_index}: originality (executional change)", "deferred",
                            "needs real generation"))
        checks.append(Check(f"slide{s.slide_index}: product identity fidelity", "deferred",
                            "needs real generation"))
        checks.append(Check(f"slide{s.slide_index}: visual quality uplift", "deferred",
                            "needs real generation"))

    for inv in plan.invariants:
        if inv.name == "single_promoted_product":
            got = max((o.distinct_products for o in observed.values()), default=0)
            checks.append(Check("invariant: single_promoted_product", "pass" if got <= inv.spec.get("distinct_promoted", 1) else "fail",
                                f"observed distinct={got}"))
        elif inv.name == "commercial_values_present":
            hay_all = " ".join(_norm(t) for o in observed.values() for t in o.detected_text)
            missing = [v for v in inv.spec.get("values", []) if _norm(v) not in hay_all]
            checks.append(Check("invariant: commercial_values_present", "pass" if not missing else "fail",
                                "" if not missing else f"missing {missing}"))
        elif inv.name == "no_cta":
            any_cta = any(o.cta_detected for o in observed.values())
            checks.append(Check("invariant: no_cta", "pass" if not any_cta else "fail"))

    return ValidationResult(checks=checks, phase="post-generation")
