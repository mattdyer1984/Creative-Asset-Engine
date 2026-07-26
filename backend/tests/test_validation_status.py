"""
Validation status (Phase F).

Confidence and validation are different concepts. Phase F made the case
concrete: across 47 confidence-bearing decisions on the eight benchmarks, 45
sat in the high band and none in the medium band, so confidence on its own
separated almost nothing. What distinguished the artifacts was whether their
own validators had rejected anything.
"""

import pytest

from app.services.composition_schema import (
    CompositionContract, Device, Relation, RelationEdge, Zone, ZoneRole,
)
from app.services.profile_schema import (
    CapabilityLevel, FamilyClass, TextRole, TypographySystem,
)
from app.services.text_ownership import (
    DecisionSource, HandlingPolicy, Owner, OwnershipPlan, TextOwnership,
)
from app.services.text_classification import TextClass
from app.services.validation_status import (
    ValidationStatus,
    validate_composition_contract,
    validate_ownership,
    validate_typography_system,
)


def _contract(**overrides):
    base = dict(
        device=Device.PRODUCT_HERO, device_confidence=0.9,
        zones=[Zone(zone_id="hero", role=ZoneRole.PRODUCT, bounds=(0.1, 0.1, 0.9, 0.9))],
        relations=[],
    )
    base.update(overrides)
    return CompositionContract(**base)


def test_a_clean_contract_is_validated():
    result = validate_composition_contract(_contract())
    assert result.status is ValidationStatus.VALIDATED
    assert result.findings == []
    assert result.checks_applied, "validated must not mean nothing was checked"


def test_a_low_confidence_device_needs_review():
    result = validate_composition_contract(_contract(device_confidence=0.2))
    assert result.status is ValidationStatus.NEEDS_REVIEW
    assert any("not trusted" in f for f in result.findings)


def test_dropped_items_make_it_partially_validated():
    result = validate_composition_contract(
        _contract(), rejected=["relation 'a' -> 'b' names an undeclared zone"]
    )
    assert result.status is ValidationStatus.PARTIALLY_VALIDATED


def test_an_unresolved_relation_fails():
    contract = _contract(relations=[
        RelationEdge(subject="hero", relation=Relation.ABOVE, object="ghost")
    ])
    assert validate_composition_contract(contract).status is ValidationStatus.FAILED


def test_no_contract_fails_rather_than_passing_vacuously():
    assert validate_composition_contract(None).status is ValidationStatus.FAILED


def test_the_worst_check_wins():
    """An artifact is only as trustworthy as its weakest check."""
    contract = _contract(device_confidence=0.1, relations=[
        RelationEdge(subject="hero", relation=Relation.ABOVE, object="ghost")
    ])
    result = validate_composition_contract(contract, rejected=["something"])
    assert result.status is ValidationStatus.FAILED
    assert len(result.findings) >= 3, "every finding is kept, not just the worst"


def _decision(text, owner=Owner.TYPOGRAPHY, block_id="block-0", zone="z1"):
    return TextOwnership(
        block_id=block_id, text=text, text_class=TextClass.DESIGNED_TYPOGRAPHY,
        owner=owner, handling_policy=HandlingPolicy.PRESERVE_VERBATIM,
        source=DecisionSource.PROJECT_DEFAULT, confidence=1.0, reason="test",
        composition_zone_id=zone,
    )


def test_clean_ownership_is_validated():
    plan = OwnershipPlan(decisions=[_decision("Your upper back")])
    assert validate_ownership(plan, 1).status is ValidationStatus.VALIDATED


def test_a_contested_block_needs_review_by_construction():
    """That is what the review destination MEANS; hiding it defeats it."""
    plan = OwnershipPlan(decisions=[_decision("maybe", owner=Owner.REVIEW)])
    result = validate_ownership(plan, 1)
    assert result.status is ValidationStatus.NEEDS_REVIEW


def test_a_block_count_mismatch_fails():
    plan = OwnershipPlan(decisions=[_decision("one")])
    assert validate_ownership(plan, 3).status is ValidationStatus.FAILED


def test_partially_placed_blocks_are_partially_validated():
    plan = OwnershipPlan(decisions=[
        _decision("placed", block_id="block-0", zone="z1"),
        _decision("unplaced", block_id="block-1", zone=None),
    ])
    assert validate_ownership(plan, 2).status is ValidationStatus.PARTIALLY_VALIDATED


def test_no_blocks_placed_at_all_is_not_partial():
    """Running without a contract is a documented mode, not a partial result."""
    plan = OwnershipPlan(decisions=[
        _decision("a", block_id="block-0", zone=None),
        _decision("b", block_id="block-1", zone=None),
    ])
    assert validate_ownership(plan, 2).status is ValidationStatus.VALIDATED


def _system(**overrides):
    base = dict(
        primary_family_class=FamilyClass.SERIF, capability_level=CapabilityLevel.L1,
        colour_roles={"body": "near-black"},
        text_roles={"h": TextRole(colour_role="body")},
    )
    base.update(overrides)
    return TypographySystem(**base)


def test_a_complete_typography_system_is_validated():
    assert validate_typography_system(_system()).status is ValidationStatus.VALIDATED


def test_an_undefined_colour_role_is_partially_validated():
    """
    The defect Package E5 found live: a colour role nobody defined renders
    near-black and flattens the hierarchy.
    """
    system = _system(text_roles={"h": TextRole(colour_role="accent")})
    result = validate_typography_system(system)
    assert result.status is ValidationStatus.PARTIALLY_VALIDATED
    assert any("accent" in f for f in result.findings)


@pytest.mark.parametrize("level", [CapabilityLevel.L2, CapabilityLevel.L3])
def test_capability_beyond_the_renderer_needs_review_not_failure(level):
    """A correct answer this renderer cannot act on is not a defect."""
    result = validate_typography_system(_system(capability_level=level))
    assert result.status is ValidationStatus.NEEDS_REVIEW


def test_validation_is_not_confidence():
    """
    The distinction this module exists for: a maximally confident decision
    can still be unvalidated, and a validated one can carry no confidence.
    """
    plan = OwnershipPlan(decisions=[_decision("certain but contested", owner=Owner.REVIEW)])
    assert plan.decisions[0].confidence == 1.0
    assert validate_ownership(plan, 1).status is ValidationStatus.NEEDS_REVIEW
