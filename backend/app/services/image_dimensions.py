"""
Source image dimension measurement — the single place image pixel dimensions are
measured from bytes or a file. Kept tiny and dependency-light so it can run at the
earliest ingestion boundary (where the original bytes are guaranteed to exist) and
in the backfill, with no coupling to the analysis pipeline.

Measurement is EVIDENCE: it either succeeds with integer (width, height), or it
fails explicitly. It never guesses or defaults.
"""
from __future__ import annotations

import os
from io import BytesIO
from typing import Optional, Tuple

# Persisted dimension states — a genuinely distinguishable set so a NULL width can
# never be confused with "not yet attempted". The state is a deterministic function of
# TWO persisted columns, never a single nullable field:
#
#   (source_width, source_height)         dimension_measurement_source     -> state
#   ---------------------------------     ----------------------------        -----
#   both valid positive ints              (any)                            -> measured
#   exactly one present                   (any)                            -> malformed
#   both NULL                             NULL / empty                     -> not-attempted
#   both NULL                             endswith "file-missing"          -> file-missing
#   both NULL                             endswith "unreadable"            -> unreadable
#   both NULL                             set, but neither marker          -> attempted (unknown)
#
# "not-attempted" (source NULL) is therefore unambiguously distinct from the two
# recorded-failure states (source carries an explicit marker).
STATE_MEASURED = "measured"
STATE_FILE_MISSING = "file-missing"
STATE_UNREADABLE = "unreadable"
STATE_NOT_ATTEMPTED = "not-attempted"
STATE_MALFORMED = "malformed"
STATE_ATTEMPTED_UNKNOWN = "attempted-unknown"


def persisted_dimension_state(source_width, source_height, measurement_source) -> str:
    """Classify a slide's persisted dimension evidence into exactly one state, from the
    (width, height) pair and the provenance marker together — see the table above."""
    if is_valid_pair(source_width, source_height):
        return STATE_MEASURED
    if is_malformed_pair(source_width, source_height):
        return STATE_MALFORMED
    src = (measurement_source or "").strip()
    if not src:
        return STATE_NOT_ATTEMPTED
    if src.endswith(STATE_FILE_MISSING):
        return STATE_FILE_MISSING
    if src.endswith(STATE_UNREADABLE):
        return STATE_UNREADABLE
    return STATE_ATTEMPTED_UNKNOWN


def measure_dimensions(image_bytes: bytes) -> Optional[Tuple[int, int]]:
    """(width, height) measured from raw image bytes, or None if unreadable."""
    if not image_bytes:
        return None
    try:
        from PIL import Image
        with Image.open(BytesIO(image_bytes)) as im:
            w, h = im.size
        return (int(w), int(h))
    except Exception:
        return None


def measure_source_file(path: Optional[str]) -> Tuple[str, Optional[Tuple[int, int]]]:
    """Measure from a stored file, returning an explicit (state, dims):
        ("measured", (w, h)) | ("file-missing", None) | ("unreadable", None)
    Never raises; the state distinguishes a genuinely absent file from a present
    but corrupt/unsupported one."""
    if not path or not os.path.exists(path):
        return (STATE_FILE_MISSING, None)
    try:
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size
        return (STATE_MEASURED, (int(w), int(h)))
    except Exception:
        return (STATE_UNREADABLE, None)


def is_valid_pair(width, height) -> bool:
    """A dimension pair is valid only when BOTH are positive integers. Exactly one
    present is malformed evidence — never used to derive an aspect."""
    return isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0


def is_malformed_pair(width, height) -> bool:
    """Exactly one of width/height present (the malformed state)."""
    return (width is None) != (height is None)
