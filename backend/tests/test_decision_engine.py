"""
Unit tests for the Decision Engine (Phase 10.2 of AI Creative Engine
vNext, see MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §11).
No real provider call - decide_generation_plan only reads
default_registry.image_generation()'s static provider/model attributes.
"""

import pytest

from app.services.decision_engine import decide_generation_plan


def test_fast_balanced_maximum_map_to_the_specified_candidate_counts():
    assert decide_generation_plan("fast").candidate_count == 1
    assert decide_generation_plan("balanced").candidate_count == 3
    assert decide_generation_plan("maximum").candidate_count == 5


def test_unknown_quality_mode_raises():
    with pytest.raises(ValueError, match="Unknown quality_mode"):
        decide_generation_plan("ludicrous")


def test_plan_carries_the_configured_provider_and_model():
    plan = decide_generation_plan("fast")
    assert plan.provider
    assert plan.model
    assert plan.quality_mode == "fast"


def test_retry_fields_default_to_none_and_are_carried_through_when_given():
    plan = decide_generation_plan("fast")
    assert plan.retry_of_generation_attempt_id is None
    assert plan.retry_reason is None

    retry_plan = decide_generation_plan(
        "fast", retry_of_generation_attempt_id="attempt-1", retry_reason="nothing accepted"
    )
    assert retry_plan.retry_of_generation_attempt_id == "attempt-1"
    assert retry_plan.retry_reason == "nothing accepted"


def test_to_dict_round_trips_every_field():
    plan = decide_generation_plan("balanced", retry_of_generation_attempt_id="attempt-1")
    as_dict = plan.to_dict()
    assert as_dict["quality_mode"] == "balanced"
    assert as_dict["candidate_count"] == 3
    assert as_dict["retry_of_generation_attempt_id"] == "attempt-1"
