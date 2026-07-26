"""
TikTok import orchestrator — Critical TikTok Slideshow Import Fix (see
MIGRATION_PLAN.md). The single entry point `import_from_url` now calls
for every TikTok URL import, replacing the old direct
`import_slideshows(db, source_type=payload.provider, ...)` dispatch.

Provider order (a direct, explicit user instruction, implemented as
given - see this fix's own MIGRATION_PLAN.md report for the reasoning
and the real costs mitigated below): Downie first, Playwright fallback.
This is the *opposite* of what both importer modules' own docstrings
still say ("PlaywrightTikTokImporter... Recommended over
DownieImporter"; "DownieImporter... Never the primary path") - those
docstrings describe each importer's own judgment about itself, not a
constraint this orchestrator is bound by. Real costs of Downie-first
are mitigated here, not ignored:

- **Provenance loss**: DownieImporter's own EvidencePackage always has
  creator=None/caption=None/hashtags=[] (its automation surface can't
  provide them). When Downie wins, its package is enriched with the
  real values from the already-fetched item struct before persisting -
  picking Downie never means silently losing data that was already in
  hand.
- **Stale signed URLs on the fallback leg**: if Downie is tried first
  and takes up to its own 90s timeout before falling back,
  TikTok's short-TTL signed image URLs from the *original* detection
  fetch could be stale by the time a fallback tries to use them. The
  Playwright fallback therefore does its own fresh fetch - it does NOT
  reuse the `item` from this module's own detection call.
- **Latency**: `detect_tiktok_content`'s own expected count is threaded
  into Downie's `source_config["expected_count"]`, so a well-behaved
  download converges as soon as enough files are stable rather than
  always waiting Downie's full 90s cap - that cap now only bites in a
  genuine "Downie is stuck" case, which is exactly when falling back is
  the right call anyway.

Both importers are only ever reached through `get_importer(name)
.import_source(...)` (the existing registry interface) - this module
never imports `DownieImporter`/`PlaywrightTikTokImporter` directly, so
neither importer needs to know the other, or this orchestrator, exists.
The `expected_count` mechanism is a documented `source_config` dict key
(`"expected_count"`), consistent with `ImportProvider.import_source`'s
own framing of `source_config` as "provider-specific configuration."
"""

import dataclasses

from sqlalchemy.orm import Session

from app.domain import EvidencePackage
from app.importers import get_importer
from app.importers.downie import DownieImportError
from app.services.safe_fetch import normalise_pasted_url
from app.importers.playwright_tiktok import (
    TikTokImportUnsupportedContentError,
    _creator_from_item,
    detect_tiktok_content,
)
from app.models.slideshow import Slideshow
from app.services.import_integrity import ImportIntegrityReport, check_import_integrity, log_integrity_report
from app.services.slideshow_import import persist_evidence_package


class ImportIncompleteError(Exception):
    """
    Raised when every provider attempted either failed outright or
    produced a genuinely incomplete result (see ImportIntegrityReport.
    complete). The pipeline must never continue past this - no
    Slideshow/Slide row is ever persisted, so nothing downstream (OCR,
    Creative Intelligence, generation) can spend real API cost on an
    import that never happened correctly.
    """


def _incomplete_message(expected_count: int, downloaded: int) -> str:
    return f"Slideshow import incomplete: expected {expected_count} slides, downloaded {downloaded}."


def _enrich_with_tiktok_metadata(package: EvidencePackage, item: dict) -> EvidencePackage:
    """
    DownieImporter's own EvidencePackage always has creator=None/
    caption=None/hashtags=[] - its automation surface has no way to
    provide them (see its module docstring). When Downie's result wins
    the integrity gate, overlay the real values from the item struct
    this orchestrator already fetched for detection, reusing the exact
    same extraction PlaywrightTikTokImporter itself uses rather than
    duplicating it.
    """
    return dataclasses.replace(
        package,
        creator=_creator_from_item(item),
        caption=item.get("desc") or None,
        hashtags=[c["title"] for c in item.get("challenges", []) if c.get("title")],
    )


def _attempt_downie(
    url: str, content_type: str, expected_count: int
) -> tuple[EvidencePackage, ImportIntegrityReport]:
    package = get_importer("downie").import_source({"url": url, "expected_count": expected_count})
    report = check_import_integrity("downie", content_type, expected_count, package)
    log_integrity_report(report)
    return package, report


def _attempt_tiktok(
    url: str, content_type: str, expected_count: int
) -> tuple[EvidencePackage, ImportIntegrityReport]:
    package = get_importer("tiktok").import_source({"url": url})
    report = check_import_integrity("tiktok", content_type, expected_count, package)
    log_integrity_report(report)
    return package, report


def import_tiktok_url(
    db: Session, url: str, project_id: str | None, provider: str = "auto"
) -> list[Slideshow]:
    """
    provider: "auto" (Downie -> Playwright fallback, the new default),
    "tiktok" (Playwright only, no fallback), or "downie" (Downie only,
    no fallback) - the forced-single-provider modes exist for the live-
    test matrix ("report results per provider") and for anyone who wants
    to pin one deliberately. All three run the same integrity gate;
    forced modes just don't fall back to the other on failure.
    """
    # Normalise ONCE, here, before anything downstream sees it. The Downie
    # importer validates the raw string it is handed, so a pasted
    # `tiktok.com/@someone/photo/123` - no scheme, exactly what a browser
    # address bar gives you - reached validate_tiktok_url and was refused,
    # surfacing as an unexplained HTTP 500.
    url = normalise_pasted_url(url)

    content = detect_tiktok_content(url)
    if content.content_type == "video":
        raise TikTokImportUnsupportedContentError(
            f"TikTok post at {url} is a video, not a photo-mode slideshow - "
            "see PlaywrightTikTokImporter's module docstring for why this is rejected"
        )

    expected_count = content.expected_slide_count
    attempts: list[ImportIntegrityReport] = []

    if provider in ("auto", "downie"):
        try:
            package, report = _attempt_downie(url, content.content_type, expected_count)
            if report.complete:
                enriched = _enrich_with_tiktok_metadata(package, content.item)
                return persist_evidence_package(db, enriched, "downie", project_id, group_as_one=True)
            attempts.append(report)
        except DownieImportError:
            if provider == "downie":
                raise
            # auto mode: unavailable/timeout/unsupported all mean "move on to the fallback"

        if provider == "downie":
            best = max(attempts, key=lambda r: r.slides_downloaded)
            raise ImportIncompleteError(_incomplete_message(expected_count, best.slides_downloaded))

    package, report = _attempt_tiktok(url, content.content_type, expected_count)
    if report.complete:
        return persist_evidence_package(db, package, "tiktok", project_id, group_as_one=True)
    attempts.append(report)

    best = max(attempts, key=lambda r: r.slides_downloaded)
    raise ImportIncompleteError(_incomplete_message(expected_count, best.slides_downloaded))
