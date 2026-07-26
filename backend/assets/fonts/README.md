# Bundled font faces

Empty by design in the repository. Run `python scripts/fetch_fonts.py` to
install the redistributable set, or drop your own licensed faces here using
the filenames in `VENDORED_FACES` (`app/services/typography.py`).

Every face must be redistributable under its licence. Nothing here is
committed until its SHA-256 is pinned in `scripts/fetch_fonts.py`, so an
unverified binary cannot reach the renderer.

`assert_fonts_are_portable()` refuses to start a deployment that would render
from host fonts: output that depends on which machine drew it makes benchmark
scores incomparable across machines.
