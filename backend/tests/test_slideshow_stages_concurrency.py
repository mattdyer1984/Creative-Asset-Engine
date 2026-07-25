"""
Unit tests for app.slideshow_stages.concurrency (real-world-diagnosed
speed fix, see MIGRATION_PLAN.md). Real timing/threading behavior, not
faked - the whole point of this helper is genuine concurrent execution.
"""

import threading
import time

from app.slideshow_stages.concurrency import MAX_CONCURRENT_CALLS, run_concurrently


def test_empty_items_returns_empty_dict_without_starting_a_thread_pool():
    assert run_concurrently([], lambda item: item) == {}


def test_results_are_keyed_by_original_position_regardless_of_completion_order():
    # Deliberately reversed delays so item 0 finishes LAST - proves
    # results are keyed by original index, not completion order.
    delays = [0.06, 0.04, 0.02, 0.0]

    def call(index: int) -> str:
        time.sleep(delays[index])
        return f"result-{index}"

    results = run_concurrently([0, 1, 2, 3], call)

    assert results == {0: "result-0", 1: "result-1", 2: "result-2", 3: "result-3"}


def test_a_failing_call_is_captured_as_the_exception_itself_not_raised():
    def call(item: int) -> int:
        if item == 1:
            raise ValueError("boom")
        return item * 2

    results = run_concurrently([0, 1, 2], call)

    assert results[0] == 0
    assert results[2] == 4
    assert isinstance(results[1], ValueError)
    assert str(results[1]) == "boom"


def test_calls_actually_run_concurrently_not_sequentially():
    """
    Real proof of the whole point of this helper: 4 calls that each
    sleep 0.1s must complete in well under 4 * 0.1s if genuinely
    concurrent - a sequential fallback (or a bug that serializes them)
    would take close to 0.4s.
    """
    barrier = threading.Barrier(4, timeout=2)

    def call(_item: int) -> None:
        barrier.wait()  # only passes if all 4 calls are in flight at once

    start = time.monotonic()
    run_concurrently([0, 1, 2, 3], call)
    elapsed = time.monotonic() - start

    assert elapsed < 1.0  # the barrier itself proves concurrency; this just guards against a hang


def test_never_exceeds_the_configured_concurrency_cap():
    in_flight = 0
    max_in_flight = 0
    lock = threading.Lock()

    def call(_item: int) -> None:
        nonlocal in_flight, max_in_flight
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        time.sleep(0.03)
        with lock:
            in_flight -= 1

    run_concurrently(list(range(MAX_CONCURRENT_CALLS + 3)), call)

    assert max_in_flight <= MAX_CONCURRENT_CALLS
