"""
Source-dimension persistence — deterministic tests for the read-surface contract
and the measurement/backfill logic. No app/ORM/network needed: AnalysisSource reads
raw sqlite, so a temp DB + temp image files exercise the full precedence.

Covers the required cases:
  * persisted present               -> returned WITHOUT opening the file
  * persisted absent + valid file   -> measured from file
  * persisted absent + missing file -> None / explicit unknown
  * only one persisted dimension    -> malformed; fallback attempted (no aspect from partial)
  * persisted conflicts with file   -> persisted authoritative; discrepancy observable
"""
import os
import sqlite3
import tempfile

from PIL import Image

from app.transformation.analysis_source import AnalysisSource
from app.services.image_dimensions import (
    measure_dimensions, measure_source_file, is_valid_pair, is_malformed_pair,
    persisted_dimension_state,
    STATE_MEASURED, STATE_FILE_MISSING, STATE_UNREADABLE, STATE_NOT_ATTEMPTED,
    STATE_MALFORMED, STATE_ATTEMPTED_UNKNOWN)
from app.services.backfill_source_dimensions import decide_backfill, ACTION_SKIP


def _png(path, w, h):
    Image.new("RGB", (w, h), (10, 20, 30)).save(path, "PNG")
    return path


def _db(rows):
    """Temp sqlite with a minimal `slides` table; rows = list of dicts."""
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    c = sqlite3.connect(path)
    c.execute("""create table slides (id text primary key, source_width integer,
                 source_height integer, dimension_measurement_source text,
                 stored_file_path text)""")
    for r in rows:
        c.execute("insert into slides (id, source_width, source_height, "
                  "dimension_measurement_source, stored_file_path) values (?,?,?,?,?)",
                  (r["id"], r.get("w"), r.get("h"), r.get("src"), r.get("path")))
    c.commit(); c.close()
    return path


# ---------------------------------------------------------------- measurement
def test_measure_from_bytes_and_file(tmp_path=None):
    p = _png(tempfile.mktemp(suffix=".png"), 900, 1200)
    with open(p, "rb") as f:
        assert measure_dimensions(f.read()) == (900, 1200)
    assert measure_source_file(p) == (STATE_MEASURED, (900, 1200))
    assert measure_source_file("/no/such/file.png") == (STATE_FILE_MISSING, None)
    assert measure_dimensions(b"not an image") is None
    bad = tempfile.mktemp(suffix=".png"); open(bad, "wb").write(b"garbage")
    assert measure_source_file(bad) == (STATE_UNREADABLE, None)


def test_valid_and_malformed_pairs():
    assert is_valid_pair(10, 20) and not is_valid_pair(0, 20) and not is_valid_pair(10, None)
    assert is_malformed_pair(10, None) and is_malformed_pair(None, 20)
    assert not is_malformed_pair(10, 20) and not is_malformed_pair(None, None)


# ------------------------------------------------ AnalysisSource read precedence
def test_persisted_present_returned_without_opening_file():
    # stored_file_path points at a NON-EXISTENT file, yet dims come back -> file not opened
    db = _db([{"id": "s1", "w": 1080, "h": 1440, "src": "ingest", "path": "/gone/x.png"}])
    src = AnalysisSource(db)
    assert src.source_dims("s1") == {"width": 1080, "height": 1440}
    st = src.source_dimension_state("s1")
    assert st["source"] == "persisted" and st["resolved"] == (1080, 1440)


def test_persisted_absent_valid_file_measured():
    p = _png(tempfile.mktemp(suffix=".png"), 720, 960)
    db = _db([{"id": "s2", "w": None, "h": None, "src": None, "path": p}])
    src = AnalysisSource(db)
    assert src.source_dims("s2") == {"width": 720, "height": 960}
    assert src.source_dimension_state("s2")["source"] == "file"


def test_persisted_absent_missing_file_is_unknown():
    db = _db([{"id": "s3", "w": None, "h": None, "src": None, "path": "/gone/y.png"}])
    src = AnalysisSource(db)
    assert src.source_dims("s3") is None
    assert src.source_dimension_state("s3")["source"] == "unknown"


def test_partial_persisted_is_malformed_and_falls_back():
    p = _png(tempfile.mktemp(suffix=".png"), 640, 800)
    # only width persisted -> malformed -> must NOT be used; falls back to the file
    db = _db([{"id": "s4", "w": 999, "h": None, "src": "ingest", "path": p}])
    src = AnalysisSource(db)
    assert src.source_dims("s4") == {"width": 640, "height": 800}   # file, not the partial 999
    st = src.source_dimension_state("s4")
    assert st["malformed"] is True and st["persisted"] is None and st["source"] == "file"


def test_persisted_conflicts_with_file_persisted_wins_and_is_observable():
    p = _png(tempfile.mktemp(suffix=".png"), 800, 600)      # file says 800x600
    db = _db([{"id": "s5", "w": 1080, "h": 1440, "src": "ingest", "path": p}])  # persisted says 1080x1440
    src = AnalysisSource(db)
    assert src.source_dims("s5") == {"width": 1080, "height": 1440}  # persisted authoritative
    st = src.source_dimension_state("s5")
    assert st["conflict"] is True and st["persisted"] == (1080, 1440) and st["file"] == (800, 600)


# ---------------------------------------------------------------- backfill logic
def test_decide_backfill_states_and_idempotency():
    p = _png(tempfile.mktemp(suffix=".png"), 500, 700)
    # valid persisted -> skip (non-destructive, and idempotent on rerun)
    assert decide_backfill(500, 700, p) == (ACTION_SKIP, None)
    # not attempted + valid file -> measured
    action, fields = decide_backfill(None, None, p)
    assert action == STATE_MEASURED and fields["source_width"] == 500 and fields["source_height"] == 700
    assert fields["dimension_measurement_source"] == "backfill"
    # missing file -> explicit file-missing state
    assert decide_backfill(None, None, "/gone/z.png")[0] == STATE_FILE_MISSING
    # unreadable file -> explicit unreadable state
    bad = tempfile.mktemp(suffix=".png"); open(bad, "wb").write(b"nope")
    assert decide_backfill(None, None, bad)[0] == STATE_UNREADABLE
    # partial persisted is not "valid" -> re-attempted (falls into measurement), never skipped
    assert decide_backfill(999, None, p)[0] == STATE_MEASURED


def test_four_way_state_is_unambiguously_distinguishable():
    # measured
    assert persisted_dimension_state(800, 600, "ingest:slideshow_import") == STATE_MEASURED
    assert persisted_dimension_state(800, 600, None) == STATE_MEASURED          # dims win regardless of source
    # malformed (exactly one present) — never confused with the others
    assert persisted_dimension_state(800, None, "ingest:slideshow_import") == STATE_MALFORMED
    assert persisted_dimension_state(None, 600, None) == STATE_MALFORMED
    # never-attempted: both NULL AND no provenance marker
    assert persisted_dimension_state(None, None, None) == STATE_NOT_ATTEMPTED
    assert persisted_dimension_state(None, None, "") == STATE_NOT_ATTEMPTED
    # recorded failures: both NULL but an explicit marker — distinct from not-attempted
    assert persisted_dimension_state(None, None, "backfill:file-missing") == STATE_FILE_MISSING
    assert persisted_dimension_state(None, None, "ingest:slideshow_import:unreadable") == STATE_UNREADABLE
    assert persisted_dimension_state(None, None, "backfill:unreadable") == STATE_UNREADABLE
    # attempted but no recognised marker -> its own state, still not "not-attempted"
    assert persisted_dimension_state(None, None, "ingest:slideshow_import") == STATE_ATTEMPTED_UNKNOWN
