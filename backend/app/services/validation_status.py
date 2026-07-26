"""
Validation status (Phase F).

**Confidence and validation are different concepts and must stay separate.**

Confidence is how sure the producer was. Validation is whether anything
checked. A model can be certain and wrong; a deterministic rule can be
correct and carry no confidence at all. Collapsing them loses the distinction
that matters most in review: *did anyone verify this, or does it merely sound
sure?*

Phase F made the case concrete. Across 47 confidence-bearing decisions on the
eight benchmarks, 45 sat in the high band and none in the medium band -
confidence was almost constant, so on its own it separated nothing. What
actually distinguished the artifacts was whether their own validators had
rejected anything, which is what this records.

The four statuses:

    validated            every check that applies to this artifact passed
    partially_validated  it is usable, but something was dropped or unproven
    needs_review         a human has to look before this is relied on
    failed               a check failed outright; do not build on it
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ValidationStatus(StrEnum):
    VALIDATED = "validated"
    PARTIALLY_VALIDATED = "partially_validated"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


#: Worst-wins ordering. An artifact is only as trustworthy as its weakest
#: check, so combining statuses never averages them.
_SEVERITY = {
    ValidationStatus.VALIDATED: 0,
    ValidationStatus.PARTIALLY_VALIDATED: 1,
    ValidationStatus.NEEDS_REVIEW: 2,
    ValidationStatus.FAILED: 3,
}


class Validation(BaseModel):
    """A status, and the checks that produced it."""

    model_config = ConfigDict(extra="forbid")

    status: ValidationStatus = ValidationStatus.VALIDATED
    #: One line per check that did NOT pass cleanly. A validated artifact has
    #: an empty list, which is itself the evidence.
    findings: list[str] = Field(default_factory=list)
    #: What was checked, so "validated" cannot mean "nothing was checked".
    checks_applied: list[str] = Field(default_factory=list)

    def combine(self, status: ValidationStatus, finding: str) -> "Validation":
        if status is not ValidationStatus.VALIDATED:
            self.findings.append(finding)
        if _SEVERITY[status] > _SEVERITY[self.status]:
            self.status = status
        return self


def validate_composition_contract(contract, rejected: list[str] | None = None) -> Validation:
    """
    A contract is validated when its own structural rules all held.

    `rejected` is what the stage dropped from the provider's response. An
    empty contract with nothing rejected is a different fact from one that
    lost six zones, and both are different from a confident one.
    """
    validation = Validation(checks_applied=[
        "device recognised", "relation endpoints resolve",
        "zones survived validation", "device confidence",
    ])

    if contract is None:
        return validation.combine(ValidationStatus.FAILED, "no contract was produced")

    if not contract.zones:
        validation.combine(ValidationStatus.FAILED, "the contract declares no zones")

    unresolved = contract.unresolved_relations()
    if unresolved:
        validation.combine(
            ValidationStatus.FAILED,
            f"{len(unresolved)} relation(s) name an undeclared zone",
        )

    if not contract.is_confident:
        validation.combine(
            ValidationStatus.NEEDS_REVIEW,
            f"device {contract.device} at confidence {contract.device_confidence:.2f} - "
            "spatial ownership will be routed from geometry that is not trusted",
        )

    for finding in rejected or []:
        validation.combine(
            ValidationStatus.PARTIALLY_VALIDATED, f"dropped from the response: {finding}"
        )

    return validation


def validate_typography_system(system, dropped_roles: list[str] | None = None) -> Validation:
    """
    Validated when the system is complete enough to render from.

    Capability above L1 is `needs_review` rather than a failure: it is a
    correct answer that this renderer cannot act on, which a person needs to
    know about but is not a defect in the analysis.
    """
    from app.services.profile_schema import CapabilityLevel

    validation = Validation(checks_applied=[
        "text roles present", "colour roles resolve", "capability within the renderer",
    ])

    if system is None:
        return validation.combine(ValidationStatus.FAILED, "no typography system")

    if not system.text_roles:
        validation.combine(ValidationStatus.FAILED, "no text roles were inferred")

    unresolved = [
        role.colour_role for role in system.text_roles.values()
        if role.colour_role not in system.colour_roles
    ]
    for name in sorted(set(unresolved)):
        validation.combine(
            ValidationStatus.PARTIALLY_VALIDATED,
            f"colour role {name!r} is used but never defined - it will render near-black",
        )

    if system.capability_level is not CapabilityLevel.L1:
        validation.combine(
            ValidationStatus.NEEDS_REVIEW,
            f"capability {system.capability_level} exceeds the L1 renderer - "
            "typography is routed to the image rather than drawn",
        )

    for role in dropped_roles or []:
        validation.combine(
            ValidationStatus.PARTIALLY_VALIDATED, f"role {role!r} failed validation"
        )

    return validation


def validate_ownership(plan, expected_block_count: int | None = None) -> Validation:
    """
    Validated when every block has exactly one owner and none needs a human.

    A block routed to review is `needs_review` by construction - that is what
    the destination means, and an artifact that hid it would defeat the point
    of having the destination at all.
    """
    from app.services.text_ownership import DuplicateOwnership, assert_single_ownership

    validation = Validation(checks_applied=[
        "single ownership", "every block accounted for", "no block awaiting review",
    ])

    try:
        assert_single_ownership(plan)
    except DuplicateOwnership as exc:
        validation.combine(ValidationStatus.FAILED, str(exc))

    if expected_block_count is not None and len(plan.decisions) != expected_block_count:
        validation.combine(
            ValidationStatus.FAILED,
            f"{len(plan.decisions)} decision(s) for {expected_block_count} block(s)",
        )

    for decision in plan.needs_review:
        validation.combine(
            ValidationStatus.NEEDS_REVIEW,
            f"{decision.text[:40]!r} is contested and awaits review",
        )

    unplaced = [d for d in plan.decisions if d.composition_zone_id is None]
    if unplaced and len(unplaced) != len(plan.decisions):
        validation.combine(
            ValidationStatus.PARTIALLY_VALIDATED,
            f"{len(unplaced)} block(s) were not placed by the composition contract",
        )

    return validation


def validate_profile(profile, text_mode_confidence: float | None) -> Validation:
    """
    Validated when the project's text mode rests on evidence, not a default.

    The threshold is the classifier's own review band, not a new number: a
    mode chosen below it is exactly the case the ADR says to surface.
    """
    from app.services.text_classification import REVIEW_CONFIDENCE

    validation = Validation(checks_applied=[
        "text mode has deciding evidence", "text mode confidence above the review band",
    ])

    if profile is None:
        return validation.combine(ValidationStatus.FAILED, "no profile was produced")

    if text_mode_confidence is None:
        validation.combine(
            ValidationStatus.NEEDS_REVIEW, "text mode was recorded with no confidence"
        )
    elif text_mode_confidence < REVIEW_CONFIDENCE:
        validation.combine(
            ValidationStatus.NEEDS_REVIEW,
            f"text mode confidence {text_mode_confidence:.2f} is below the review band "
            f"({REVIEW_CONFIDENCE}) - the project default was applied, not a finding",
        )

    return validation
