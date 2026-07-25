"""
Bounded-concurrency helper for per-slide analysis stage provider calls
(real-world-diagnosed speed fix, see MIGRATION_PLAN.md). Real timing
data from a real 2-slide slideshow's /analyze run showed every per-slide
stage (OCR, Product Isolation, Product Lock Profile, Creative
Fingerprint, Scene Intelligence) looping over slides sequentially, one
blocking AI provider call at a time - each stage's own wall-clock time
scaled linearly with slide count, even though every slide's own call is
fully independent of every other's.

Deliberately narrow: runs ONLY the slow, I/O-bound provider call
concurrently via a thread pool (Python threads release the GIL during
network I/O, so this gives a real wall-clock win without an async
rewrite) - every DB write a calling stage makes (start_analysis_run,
ProductAppearance updates, mark_succeeded/mark_failed, etc.) stays
exactly where it was, on that stage's own single, sequential loop,
since a SQLAlchemy Session is not thread-safe and must never be touched
from a worker thread. Callers pass a plain function with no `db`
parameter in its closure.

Real, disclosed tradeoff: because every item's call now fires
regardless of whether an earlier item's own (sequential, DB-writing)
processing will end up failing the whole stage, a failure can "waste"
the cost of a later item's call that the old, sequential loop would
never have attempted once it hit the first failure. Accepted because
calls succeeding is the overwhelmingly common case, and the wall-clock
win on that common path is real and significant.
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")

# A small, fixed cap - real provider rate limits are a real constraint
# even though this module itself never touches the DB; kept modest
# rather than "however many slides exist."
MAX_CONCURRENT_CALLS = 4


def run_concurrently(
    items: list[T], call: Callable[[T], R], *, max_workers: int = MAX_CONCURRENT_CALLS
) -> dict[int, R | Exception]:
    """
    Runs `call(item)` for every item in `items` concurrently (bounded by
    `max_workers`, MAX_CONCURRENT_CALLS by default), returning a dict
    keyed by each item's position in the original list. Never raises - a
    failed call is stored as the Exception instance itself, for the
    caller's own existing per-item error handling (raise it back inside
    its normal sequential loop) to handle in the same order and with the
    same semantics as before this helper existed.

    max_workers (Optimisation & Stability Pass, Tier 3.2, see
    MIGRATION_PLAN.md) - an override, not a second cap layered on top of
    MAX_CONCURRENT_CALLS: some call sites (image generation) have their
    own, separately-verified, empirically-derived ceiling
    (providers.yaml's concurrency_limits.image_generation) rather than
    sharing every other stage's generic default.
    """
    if not items:
        return {}
    results: dict[int, R | Exception] = {}
    with ThreadPoolExecutor(max_workers=min(len(items), max_workers)) as executor:
        future_to_index = {executor.submit(call, item): index for index, item in enumerate(items)}
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                results[index] = future.result()
            except Exception as exc:  # noqa: BLE001 - intentionally captured, not re-raised, see docstring
                results[index] = exc
    return results
