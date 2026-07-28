"""
Backfill source pixel dimensions for existing slide rows.

Idempotent, resumable, safe to rerun, and NON-DESTRUCTIVE to already-persisted valid
dimensions. Explicit about failures — a row whose file is gone or unreadable records
that state (`backfill:file-missing` / `backfill:unreadable`) rather than being left
indistinguishable from "never attempted". The decision is a pure function so it is
unit-testable without a database.
"""
from __future__ import annotations

from typing import Optional, Tuple

from app.services.image_dimensions import (
    measure_source_file, is_valid_pair, persisted_dimension_state,
    STATE_MEASURED, STATE_FILE_MISSING, STATE_UNREADABLE, STATE_ATTEMPTED_UNKNOWN,
)

# action -> what the driver does with the row
ACTION_SKIP = "skip"                # already has valid persisted dims — never overwritten
ACTION_SKIP_FAILURE = "skipped-recorded-failure"  # a recorded failure left untouched (default)

# States that are a RECORDED failure — left untouched on rerun unless retry_failures.
_RECORDED_FAILURE = {STATE_FILE_MISSING, STATE_UNREADABLE, STATE_ATTEMPTED_UNKNOWN}


def decide_backfill(source_width, source_height, stored_file_path) -> Tuple[str, Optional[dict]]:
    """Pure decision for one row. Returns (action, fields_to_set | None):

        ("skip",         None)                      # valid dims already persisted
        ("measured",     {width, height, source})   # measured from the file now
        ("file-missing", {source})                  # attempted; file absent
        ("unreadable",   {source})                  # attempted; file present but unreadable

    Non-destructive: a row with a valid persisted pair is always skipped."""
    if is_valid_pair(source_width, source_height):
        return (ACTION_SKIP, None)
    state, dims = measure_source_file(stored_file_path)
    if state == STATE_MEASURED:
        return (STATE_MEASURED, {"source_width": dims[0], "source_height": dims[1],
                                 "dimension_measurement_source": "backfill"})
    if state == STATE_FILE_MISSING:
        return (STATE_FILE_MISSING, {"dimension_measurement_source": "backfill:file-missing"})
    return (STATE_UNREADABLE, {"dimension_measurement_source": "backfill:unreadable"})


def backfill_source_dimensions(db, commit_every: int = 200, retry_failures: bool = False) -> dict:
    """Driver: apply `decide_backfill` to every slide lacking valid persisted dims.

    Idempotent + non-destructive: measured rows are never rewritten (excluded by the
    query), and by default a RECORDED failure (file-missing / unreadable /
    attempted-unknown) is left EXACTLY as-is on rerun — so a second run over already-
    processed data changes nothing at all (not even a timestamp). Resumable: a run that
    stops partway leaves measured/failed rows recorded, and a rerun continues with the
    still-`not-attempted` (and `malformed`) rows. `retry_failures=True` explicitly opts
    into re-attempting recorded failures (e.g. after missing files are restored).
    Returns a per-outcome summary."""
    from app.models._shared import utcnow
    from app.models.slide import Slide

    summary = {STATE_MEASURED: 0, STATE_FILE_MISSING: 0, STATE_UNREADABLE: 0,
               ACTION_SKIP_FAILURE: 0}
    pending = 0
    # Non-measured rows only (measured have BOTH dims set) — measured are never rewritten.
    q = db.query(Slide).filter((Slide.source_width.is_(None)) | (Slide.source_height.is_(None)))
    for slide in q.yield_per(commit_every):
        state = persisted_dimension_state(
            slide.source_width, slide.source_height, slide.dimension_measurement_source)
        if state in _RECORDED_FAILURE and not retry_failures:
            summary[ACTION_SKIP_FAILURE] += 1          # untouched — no write, no timestamp churn
            continue
        action, fields = decide_backfill(
            slide.source_width, slide.source_height, slide.stored_file_path)
        if action == ACTION_SKIP:                      # defensive; the query already excludes valid
            continue
        summary[action] = summary.get(action, 0) + 1
        for k, v in (fields or {}).items():
            setattr(slide, k, v)
        slide.dimension_measured_at = utcnow()
        pending += 1
        if pending >= commit_every:
            db.commit()
            pending = 0
    if pending:
        db.commit()
    return summary
