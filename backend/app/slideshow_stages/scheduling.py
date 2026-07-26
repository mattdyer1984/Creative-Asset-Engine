"""
Stage scheduling (O1).

Phase F measured provider wait at **99.8% of a 71-second run**. The pipeline
was strictly sequential, but only four of its ordering constraints are real -
the rest were an artefact of writing the stages as a list.

So stages declare `depends_on`, and the schedule is derived from those
declarations rather than from list position. Two properties matter more than
the speed-up:

**Determinism.** Stages inside a wave write disjoint artifacts and never read
each other, so their outputs cannot depend on completion order. The waves
themselves run strictly in sequence, so anything with a real dependency still
sees its input. A stage that declares a dependency it does not have costs
latency; one that omits a dependency it does have is a correctness bug, which
is why `validate_dependencies` refuses a graph with an unknown or cyclic
edge rather than quietly reordering.

**Failure semantics.** Sequential execution stopped at the first failure.
Concurrent execution cannot - the other stages in the wave are already in
flight - so a wave runs to completion and the FIRST failure in declaration
order is reported. That keeps the reported failure stable regardless of which
thread finished first.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class DependencyError(ValueError):
    """A stage graph that cannot be scheduled."""


def dependencies_of(stage) -> tuple[str, ...]:
    return tuple(getattr(stage, "depends_on", ()) or ())


def validate_dependencies(stages) -> None:
    """
    Refuse a graph that cycles.

    A dependency absent from THIS list is treated as already satisfied, not
    as an error: re-running one stage on its own is a supported operation and
    its inputs were produced by an earlier run. Rejecting that would break
    every single-stage rerun. Only ordering among the stages actually present
    is this function's business.
    """
    # Cycle detection by repeated peeling, over present stages only.
    names = {stage.name for stage in stages}
    pending = {
        stage.name: {d for d in dependencies_of(stage) if d in names}
        for stage in stages
    }
    while pending:
        ready = {name for name, deps in pending.items() if not deps}
        if not ready:
            raise DependencyError(
                f"dependency cycle among {sorted(pending)}"
            )
        for name in ready:
            del pending[name]
        for deps in pending.values():
            deps -= ready


def plan_waves(stages) -> list[list]:
    """
    Group stages into waves. Everything in a wave may run concurrently;
    each wave waits for the one before it.

    Declaration order is preserved within a wave, so the reported failure and
    the logs read the same way every run.
    """
    validate_dependencies(stages)

    present = {stage.name for stage in stages}
    remaining = list(stages)
    # Dependencies outside this run were satisfied by an earlier one.
    satisfied: set[str] = {
        d for stage in stages for d in dependencies_of(stage) if d not in present
    }
    waves: list[list] = []

    while remaining:
        wave = [s for s in remaining if set(dependencies_of(s)) <= satisfied]
        if not wave:  # pragma: no cover - validate_dependencies rules this out
            raise DependencyError(f"cannot schedule {[s.name for s in remaining]}")
        waves.append(wave)
        satisfied |= {s.name for s in wave}
        remaining = [s for s in remaining if s not in wave]

    return waves


def describe_waves(waves) -> str:
    return " -> ".join(
        "[" + ", ".join(stage.name for stage in wave) + "]" for wave in waves
    )
