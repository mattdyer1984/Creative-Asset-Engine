"""
Listing import + resolution (Phase 5.10 of the catalogue layer, see
MIGRATION_PLAN.md's frozen catalogue ADR). The new, unknown-URL entry
point: unlike app.services.product_source_import.import_product_source
(Phase 5.3/5.6), which already knows which Product a URL is about (the
human navigated to that Product's page before pasting the URL), a
Listing import starts with no resolution at all - the whole reason
Listing exists is that "which Product/Bundle is this" isn't known at
fetch time.

Resolution is never automatic (per the ADR's identity section) - the two
exceptions are the ones the ADR itself carves out: linking to an
already-chosen existing Product/Bundle (the human is instructing, not
the system inferring) is a plain, explicit action; nothing here ever
guesses a match from parsed content on its own.

Once resolved to a Product, every ProductSourceImport row scoped to this
Listing gets its product_id backfilled - at that point Phase 5.5's
existing merge service (assemble_product_profile) picks the evidence up
completely unchanged, no new code needed there. A Listing resolved to a
Bundle deliberately does NOT backfill product_id anywhere - the bundle
listing's evidence describes the whole bundle, not any one member, so
there is no single correct product_id to backfill it to. Each member
Product's own Profile is assembled independently from that member's own
evidence sources, never from the bundle listing's evidence directly -
same "Bundle View is composed from member ProductProfiles, never a new
merge" principle as the ADR's Bundle philosophy section.

Scope note: member-hint resolution here is atomic (one call resolves
every member of a bundle at once), not a per-hint incremental flow - no
real UI/API consumer exists yet to validate what incremental resolution
should even look like (that's Phase 5.11/5.12's job); building genuine
incremental state tracking before there's a concrete need would be
exactly the kind of speculative complexity this project avoids
elsewhere. Revisit if 5.12's real UI exposes a concrete need for partial
resolution.

Reference-image download for Listing-scoped evidence is deliberately not
implemented in this sub-phase: ProductReferenceImage.product_id is (and
stays) non-nullable, so there's nothing to attach an image to before
resolution - and after resolution to a Bundle, there's no single product
to attach a bundle-listing-level image to either. Left as a documented
gap, not solved here (see MIGRATION_PLAN.md's Suggested future
improvements).
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.listing import Listing
from app.models.product import Product
from app.models.product_bundle import ProductBundle
from app.models.product_bundle_member import ProductBundleMember
from app.models.product_source_import import (
    FETCH_STATUS_FAILED,
    ProductSourceImport,
)
from app.product_sources.registry import get_product_source_adapter
from app.services.product_source_import import fetch_status_for_evidence


def import_listing(db: Session, url: str) -> Listing:
    """
    Fetches and normalizes `url`, persisting the result against a stable
    Listing identity (get-or-create by source_url - re-importing the same
    URL updates the same Listing, not a new one, per the ADR's identity
    section). Never resolves anything - the returned Listing may already
    be resolved from a prior call, or still be pending; this function
    only ever refreshes the fetch/commercial data, never the resolution.
    """
    listing = _get_or_create_listing(db, url)

    try:
        adapter = get_product_source_adapter(url)
        extraction = adapter.extract(url)
    except Exception as exc:
        _persist_failed_import(db, listing, exc)
        db.commit()
        db.refresh(listing)
        return listing

    evidence = extraction.normalized

    db.query(ProductSourceImport).filter(
        ProductSourceImport.listing_id == listing.id,
        ProductSourceImport.is_current.is_(True),
    ).update({"is_current": False})

    import_row = ProductSourceImport(
        product_id=None,
        listing_id=listing.id,
        source_type=evidence.source_type,
        source_url=url,
        fetch_status=fetch_status_for_evidence(evidence),
        raw_response_json=extraction.raw,
        normalized_json=evidence.model_dump(mode="json"),
    )
    db.add(import_row)

    if evidence.listing is not None:
        listing_meta = evidence.listing
        listing.price_amount = listing_meta.price_amount
        listing.price_currency = listing_meta.price_currency
        listing.seller_name = listing_meta.seller_name
        listing.rating = listing_meta.rating
        listing.units_sold = listing_meta.units_sold
        listing.shipping_info = listing_meta.shipping_info

    db.commit()
    db.refresh(listing)
    return listing


def resolve_listing_to_existing_product(db: Session, listing_id: str, product_id: str) -> Listing:
    """The human has chosen an already-known Product this Listing represents."""
    listing = _require_unresolved_listing(db, listing_id)
    product = db.get(Product, product_id)
    if product is None:
        raise ValueError(f"Product '{product_id}' does not exist")

    listing.resolved_product_id = product.id
    _backfill_product_id_onto_imports(db, listing_id, product.id)
    db.commit()
    db.refresh(listing)
    return listing


def resolve_listing_to_new_product(db: Session, listing_id: str, display_name: str) -> Listing:
    """The human has decided this Listing represents a genuinely new Product."""
    listing = _require_unresolved_listing(db, listing_id)
    product = Product(display_name=display_name)
    db.add(product)
    db.flush()

    listing.resolved_product_id = product.id
    _backfill_product_id_onto_imports(db, listing_id, product.id)
    db.commit()
    db.refresh(listing)
    return listing


def resolve_listing_to_existing_bundle(db: Session, listing_id: str, bundle_id: str) -> Listing:
    """The human recognizes this Listing as (re-)selling an already-known ProductBundle."""
    listing = _require_unresolved_listing(db, listing_id)
    bundle = db.get(ProductBundle, bundle_id)
    if bundle is None:
        raise ValueError(f"ProductBundle '{bundle_id}' does not exist")

    listing.resolved_bundle_id = bundle.id
    db.commit()
    db.refresh(listing)
    return listing


@dataclass
class BundleMemberResolution:
    """
    One resolved member of a bundle being created from a Listing -
    exactly one of the two fields set, mirroring the resolved_product_id/
    resolved_bundle_id "exactly one" pattern used throughout the
    catalogue layer.
    """

    existing_product_id: str | None = None
    new_product_display_name: str | None = None
    quantity: int = 1


def resolve_listing_to_new_bundle(
    db: Session,
    listing_id: str,
    bundle_display_name: str,
    member_resolutions: list[BundleMemberResolution],
) -> Listing:
    """
    The human has reviewed the Listing's (adapter-suggested or manually
    entered) member hints and resolved each one to either an existing or
    a brand-new Product - see the module docstring's scope note on why
    this is atomic, not per-hint incremental.
    """
    listing = _require_unresolved_listing(db, listing_id)
    if not member_resolutions:
        raise ValueError("A bundle needs at least one resolved member")

    bundle = ProductBundle(display_name=bundle_display_name)
    db.add(bundle)
    db.flush()

    for resolution in member_resolutions:
        product_id = _resolve_member_product_id(db, resolution)
        db.add(ProductBundleMember(bundle_id=bundle.id, product_id=product_id, quantity=resolution.quantity))

    listing.resolved_bundle_id = bundle.id
    db.commit()
    db.refresh(listing)
    return listing


def _resolve_member_product_id(db: Session, resolution: BundleMemberResolution) -> str:
    if resolution.existing_product_id and resolution.new_product_display_name:
        raise ValueError("A member resolution must set exactly one of the two product fields, not both")
    if resolution.existing_product_id:
        product = db.get(Product, resolution.existing_product_id)
        if product is None:
            raise ValueError(f"Product '{resolution.existing_product_id}' does not exist")
        return product.id
    if resolution.new_product_display_name:
        product = Product(display_name=resolution.new_product_display_name)
        db.add(product)
        db.flush()
        return product.id
    raise ValueError("A member resolution must set exactly one of the two product fields, not neither")


def _get_or_create_listing(db: Session, url: str) -> Listing:
    listing = db.scalars(select(Listing).where(Listing.source_url == url)).first()
    if listing is not None:
        return listing
    listing = Listing(source_type="unknown", source_url=url)
    db.add(listing)
    db.flush()
    return listing


def _require_unresolved_listing(db: Session, listing_id: str) -> Listing:
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise ValueError(f"Listing '{listing_id}' does not exist")
    if listing.resolved_product_id is not None or listing.resolved_bundle_id is not None:
        raise ValueError(f"Listing '{listing_id}' is already resolved")
    return listing


def _backfill_product_id_onto_imports(db: Session, listing_id: str, product_id: str) -> None:
    db.query(ProductSourceImport).filter(ProductSourceImport.listing_id == listing_id).update(
        {"product_id": product_id}
    )


def _persist_failed_import(db: Session, listing: Listing, exc: Exception) -> None:
    db.query(ProductSourceImport).filter(
        ProductSourceImport.listing_id == listing.id,
        ProductSourceImport.is_current.is_(True),
    ).update({"is_current": False})

    import_row = ProductSourceImport(
        product_id=None,
        listing_id=listing.id,
        source_type="unknown",
        source_url=listing.source_url,
        fetch_status=FETCH_STATUS_FAILED,
        error=str(exc),
    )
    db.add(import_row)
