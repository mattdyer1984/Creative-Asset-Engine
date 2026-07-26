"""
Stage scheduling (O1).

Phase F measured provider wait at 99.8% of a 71-second run while the pipeline
was strictly sequential. Speed is the point, but determinism is the risk, so
most of these tests are about ordering and failure semantics rather than
timing.
"""

import pytest

from app.slideshow_stages.pipeline import SLIDESHOW_STAGE_PIPELINE
from app.slideshow_stages.scheduling import (
    DependencyError,
    dependencies_of,
    describe_waves,
    plan_waves,
    validate_dependencies,
)


class _Stage:
    def __init__(self, name, depends_on=()):
        self.name = name
        self.depends_on = depends_on

    def run(self, db, slideshow):  # pragma: no cover - never executed here
        raise AssertionError


def test_independent_stages_share_a_wave():
    waves = plan_waves([_Stage("a"), _Stage("b"), _Stage("c")])
    assert [[s.name for s in w] for w in waves] == [["a", "b", "c"]]


def test_a_dependency_forces_a_later_wave():
    waves = plan_waves([_Stage("a"), _Stage("b", ("a",)), _Stage("c", ("b",))])
    assert [[s.name for s in w] for w in waves] == [["a"], ["b"], ["c"]]


def test_declaration_order_is_preserved_within_a_wave():
    """
    So the logs and the reported failure read the same way every run. A
    schedule that reordered stages run to run would make a flaky failure
    impossible to reproduce.
    """
    stages = [_Stage("z"), _Stage("y"), _Stage("x")]
    for _ in range(5):
        assert [s.name for s in plan_waves(stages)[0]] == ["z", "y", "x"]


def test_a_cycle_is_refused():
    with pytest.raises(DependencyError, match="cycle"):
        plan_waves([_Stage("a", ("b",)), _Stage("b", ("a",))])


def test_a_dependency_outside_this_run_is_treated_as_already_satisfied():
    """
    Re-running one stage alone is supported and its inputs came from an
    earlier run. Rejecting that would break every single-stage rerun.
    """
    waves = plan_waves([_Stage("creative_fingerprint", ("ocr",))])
    assert [[s.name for s in w] for w in waves] == [["creative_fingerprint"]]


# --------------------------------------------------------------------------
# The real pipeline
# --------------------------------------------------------------------------


def test_the_real_pipeline_schedules_into_four_waves():
    waves = plan_waves(SLIDESHOW_STAGE_PIPELINE)
    assert len(waves) == 4, describe_waves(waves)
    assert [s.name for s in waves[0]] == [
        "ocr", "product_isolation", "scene_intelligence", "composition_contract",
    ]
    assert waves[-1][0].name == "text_ownership"


def test_every_real_stage_declares_its_dependencies():
    """
    An omitted dependency is a correctness bug: the stage would be scheduled
    into an earlier wave and read an artifact that does not exist yet. A
    declared-but-unreal dependency only costs latency.
    """
    for stage in SLIDESHOW_STAGE_PIPELINE:
        assert hasattr(stage, "depends_on"), f"{stage.name} declares no dependencies"


def test_the_schedule_never_places_a_stage_before_its_dependency():
    """The invariant the whole optimisation rests on."""
    waves = plan_waves(SLIDESHOW_STAGE_PIPELINE)
    position = {
        stage.name: index for index, wave in enumerate(waves) for stage in wave
    }
    for stage in SLIDESHOW_STAGE_PIPELINE:
        for dependency in dependencies_of(stage):
            assert position[dependency] < position[stage.name], (
                f"{stage.name} is scheduled at or before {dependency}"
            )


def test_the_schedule_is_stable_across_repeated_planning():
    """Determinism: the same pipeline must always produce the same waves."""
    first = describe_waves(plan_waves(SLIDESHOW_STAGE_PIPELINE))
    for _ in range(10):
        assert describe_waves(plan_waves(SLIDESHOW_STAGE_PIPELINE)) == first


def test_text_ownership_runs_after_everything_it_reads():
    """
    It reads OCR blocks, the contract and the profile. Scheduling it early
    would produce ownership from wording alone - a weaker answer that still
    looks complete, which is the failure mode hardest to notice.
    """
    waves = plan_waves(SLIDESHOW_STAGE_PIPELINE)
    position = {s.name: i for i, wave in enumerate(waves) for s in wave}
    for upstream in ("ocr", "composition_contract", "creative_profile"):
        assert position[upstream] < position["text_ownership"]


def test_validate_accepts_the_real_pipeline():
    validate_dependencies(SLIDESHOW_STAGE_PIPELINE)
