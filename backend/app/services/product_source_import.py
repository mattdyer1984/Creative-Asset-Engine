"""
Product Source import orchestration (Phase 5.3 of Product Intelligence,
see MIGRATION_PLAN.md). Resolves the right adapter for a URL, fetches +
normalizes, persists a ProductSourceImport (both raw and normalized
data), and downloads any discovered images into ProductReferenceImage
rows.

On any failure - unknown/unreachable URL, adapter error, oversized
response - records a ProductSourceImport with fetch_status=
FETCH_STATUS_FAILED and the error message, rather than raising. This
matches the "the artifact records the attempt, including failures"
discipline used everywhere else in this codebase (see e.g.
app.stages.execution's mark_failed).

A single image failing to download does not fail the whole import - the
primary value of a Product Source fetch is the structured evidence
(title/brand/attributes), images are a secondary enrichment. A failed
image is simply skipped, not retried or surfaced as a partial-fetch
status (no caller has needed that granularity yet).

fetch_status=FETCH_STATUS_PARTIAL vs. FETCH_STATUS_SUCCEEDED: found via
live testing against a real TikTok Shop URL (Phase 5.4's spike, then
Phase 5.7's live-verification), not anticipated in the original plan.
The HTTP fetch itself can succeed (200 OK) against a page that is
genuinely just a bot-detection wall - GenericUrlAdapter has no error to
raise, but nothing useful was extracted either (no title, no attributes,
no images). Marking that FETCH_STATUS_SUCCEEDED would be misleading - a
user importing such a URL would reasonably read "succeeded" as "real
data was found." See fetch_status_for_evidence below.
"""

import httpx
from sqlalchemy.orm import Session

from app.models.product_reference_image import ProductReferenceImage
from app.models.product_source_import import (
    FETCH_STATUS_FAILED,
    FETCH_STATUS_PARTIAL,
    FETCH_STATUS_SUCCEEDED,
    ProductSourceImport,
)
from app.product_sources.base import NormalizedProductEvidence
from app.product_sources.registry import get_product_source_adapter
from app.storage import save_product_reference_image
from app.services.safe_fetch import fetch_public, looks_like_image

IMAGE_FETCH_TIMEOUT_SECONDS = 10.0
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def import_product_source(
    db: Session,
    product_id: str,
    url: str,
    *,
    image_download_transport: httpx.BaseTransport | None = None,
) -> ProductSourceImport:
    try:
        adapter = get_product_source_adapter(url)
        extraction = adapter.extract(url)
    except Exception as exc:
        return _persist_failed_import(db, product_id, url, exc)

    db.query(ProductSourceImport).filter(
        ProductSourceImport.product_id == product_id,
        ProductSourceImport.is_current.is_(True),
    ).update({"is_current": False})

    import_row = ProductSourceImport(
        product_id=product_id,
        source_type=extraction.normalized.source_type,
        source_url=url,
        fetch_status=fetch_status_for_evidence(extraction.normalized),
        raw_response_json=extraction.raw,
        normalized_json=extraction.normalized.model_dump(mode="json"),
    )
    db.add(import_row)
    db.flush()

    for image in extraction.normalized.images:
        _try_download_and_save_reference_image(
            db, product_id, import_row.id, image.url, transport=image_download_transport
        )

    db.commit()
    db.refresh(import_row)
    return import_row


def fetch_status_for_evidence(evidence: NormalizedProductEvidence) -> str:
    """
    See the module docstring's note on FETCH_STATUS_PARTIAL. Deliberately
    excludes `title` alone from counting as "found something": a bare
    page `<title>` is present even on pages that are genuinely just a
    bot-detection wall (confirmed live - TikTok Shop's "Security Check"
    interstitial has one) or a 404, so it's too weak a signal on its own.
    `brand`/`attributes` only ever come from real structured markup
    (JSON-LD); `images` is a step above a bare title too, whether from
    JSON-LD or OpenGraph.

    Promoted from a private helper to a shared one, and extended to also
    check `bundle`, in Phase 5.10 (catalogue layer, see MIGRATION_PLAN.md's
    frozen catalogue ADR) - a real gap found before it shipped: bundle
    evidence (Phase 5.9) deliberately leaves the top-level
    brand/attributes/images empty (see app.product_sources.generic's own
    docstring on why), so a successfully-detected bundle would have been
    misreported as FETCH_STATUS_PARTIAL without this check, even though
    real evidence (the member hints) was genuinely found. Used by both
    the existing per-product import (below) and app.services.listing_import
    (Phase 5.10).
    """
    found_anything = bool(
        evidence.brand
        or evidence.attributes
        or evidence.images
        or (evidence.bundle and evidence.bundle.member_hints)
    )
    return FETCH_STATUS_SUCCEEDED if found_anything else FETCH_STATUS_PARTIAL


def _persist_failed_import(db: Session, product_id: str, url: str, exc: Exception) -> ProductSourceImport:
    db.query(ProductSourceImport).filter(
        ProductSourceImport.product_id == product_id,
        ProductSourceImport.is_current.is_(True),
    ).update({"is_current": False})

    import_row = ProductSourceImport(
        product_id=product_id,
        # The adapter that would have known its own source_type never
        # returned - "unknown" makes clear this failed before
        # normalization, not that it succeeded with an unrecognized type.
        source_type="unknown",
        source_url=url,
        fetch_status=FETCH_STATUS_FAILED,
        error=str(exc),
    )
    db.add(import_row)
    db.commit()
    db.refresh(import_row)
    return import_row


def _try_download_and_save_reference_image(
    db: Session,
    product_id: str,
    product_source_import_id: str,
    image_url: str,
    *,
    transport: httpx.BaseTransport | None,
) -> None:
    try:
        content = _download_bounded(image_url, transport=transport)
    except Exception:
        return  # A single image failing does not fail the whole import - see module docstring.

    image = ProductReferenceImage(
        product_id=product_id,
        analysis_run_id=None,
        source_product_source_import_id=product_source_import_id,
        isolation_method="product_url",
        file_path="",  # placeholder, set below once we have the row's id
    )
    db.add(image)
    db.flush()

    stored_path = save_product_reference_image(product_id, image.id, content)
    image.file_path = str(stored_path)


def _download_bounded(url: str, *, transport: httpx.BaseTransport | None) -> bytes:
    """
    SSRF-protected image download (Phase 0 remediation, WP-0C).

    This is the SECOND-ORDER case and the more subtle of the two: these
    URLs are not typed by the user, they are extracted from the fetched
    page's own JSON-LD/OpenGraph - i.e. from content an attacker
    controls if they control the page. A hostile product page could
    therefore point <meta property="og:image"> at
    http://169.254.169.254/... and have the server fetch it. Same shared
    validator as the page fetch itself; see safe_fetch's docstring.

    Also verifies the bytes really are an image before they are saved -
    a Content-Type header is attacker-controlled and proves nothing.
    """
    result = fetch_public(
        url,
        max_bytes=MAX_IMAGE_BYTES,
        timeout=IMAGE_FETCH_TIMEOUT_SECONDS,
        transport=transport,
    )
    if not looks_like_image(result.content, result.content_type):
        raise ValueError(
            f"Content at {url} is not a recognised image format "
            f"(content-type claimed {result.content_type!r})."
        )
    return result.content
