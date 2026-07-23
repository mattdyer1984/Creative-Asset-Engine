"""
Unit tests for Listing, ProductBundle, and ProductBundleMember - Phase
5.8 of the catalogue layer (see MIGRATION_PLAN.md's frozen catalogue
ADR). Additive schema only; no service/API code exists yet to exercise,
so these are model-level round-trip tests, mirroring
tests/test_product_source_import_model.py's style for Phase 5.1's
equivalent change.
"""

from app.models.listing import Listing
from app.models.product import Product
from app.models.product_bundle import ProductBundle
from app.models.product_bundle_member import ProductBundleMember
from app.models.product_source_import import FETCH_STATUS_SUCCEEDED, ProductSourceImport


def _make_product(db_session, name: str = "Test Product") -> Product:
    product = Product(display_name=name)
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    return product


def test_listing_round_trips_unresolved(db_session):
    """A freshly-imported Listing has no resolution yet - both FKs null."""
    listing = Listing(
        source_type="generic_url",
        source_url="https://example.com/products/widget-set",
        price_amount=29.99,
        price_currency="USD",
        seller_name="Widget Co",
        rating=4.5,
        units_sold=1200,
        shipping_info="Free shipping",
    )
    db_session.add(listing)
    db_session.commit()
    db_session.refresh(listing)

    assert listing.id is not None
    assert listing.resolved_product_id is None
    assert listing.resolved_bundle_id is None
    assert listing.price_amount == 29.99
    assert listing.seller_name == "Widget Co"
    assert listing.created_at is not None


def test_listing_resolves_to_a_product(db_session):
    product = _make_product(db_session)
    listing = Listing(
        source_type="generic_url",
        source_url="https://example.com/products/widget",
        resolved_product_id=product.id,
    )
    db_session.add(listing)
    db_session.commit()
    db_session.refresh(listing)

    assert listing.resolved_product_id == product.id
    assert listing.resolved_bundle_id is None


def test_listing_resolves_to_a_bundle(db_session):
    bundle = ProductBundle(display_name="Widget Gift Set")
    db_session.add(bundle)
    db_session.flush()

    listing = Listing(
        source_type="generic_url",
        source_url="https://example.com/products/widget-gift-set",
        resolved_bundle_id=bundle.id,
    )
    db_session.add(listing)
    db_session.commit()
    db_session.refresh(listing)

    assert listing.resolved_bundle_id == bundle.id
    assert listing.resolved_product_id is None


def test_two_listings_can_resolve_to_the_same_product(db_session):
    """
    The whole point of Listing existing separately from Product - the same
    physical item sold on two marketplaces is two Listings, one Product.
    """
    product = _make_product(db_session)
    listing_a = Listing(
        source_type="generic_url",
        source_url="https://marketplace-a.example.com/widget",
        resolved_product_id=product.id,
    )
    listing_b = Listing(
        source_type="generic_url",
        source_url="https://marketplace-b.example.com/widget",
        resolved_product_id=product.id,
    )
    db_session.add_all([listing_a, listing_b])
    db_session.commit()

    assert listing_a.resolved_product_id == listing_b.resolved_product_id == product.id


def test_product_bundle_round_trips_with_members_and_quantity(db_session):
    """
    quantity supports the multipack case for free (Phase 5.8's naming
    discussion, see MIGRATION_PLAN.md) - no separate entity needed.
    """
    bottle = _make_product(db_session, "Sunrise Orange Juice")
    bundle = ProductBundle(display_name="3-Pack")
    db_session.add(bundle)
    db_session.flush()

    member = ProductBundleMember(bundle_id=bundle.id, product_id=bottle.id, quantity=3)
    db_session.add(member)
    db_session.commit()
    db_session.refresh(member)

    assert member.bundle_id == bundle.id
    assert member.product_id == bottle.id
    assert member.quantity == 3


def test_product_bundle_with_multiple_distinct_members(db_session):
    """The real bundle case: N distinct Products, not just quantity>1 of one."""
    goat = _make_product(db_session, "G.O.A.T. Man")
    ceo = _make_product(db_session, "CEO Man")
    bundle = ProductBundle(display_name="Bella Vita Luxury Set")
    db_session.add(bundle)
    db_session.flush()

    db_session.add_all(
        [
            ProductBundleMember(bundle_id=bundle.id, product_id=goat.id, quantity=1),
            ProductBundleMember(bundle_id=bundle.id, product_id=ceo.id, quantity=1),
        ]
    )
    db_session.commit()

    members = (
        db_session.query(ProductBundleMember)
        .filter(ProductBundleMember.bundle_id == bundle.id)
        .all()
    )
    assert {m.product_id for m in members} == {goat.id, ceo.id}


def test_product_bundle_member_quantity_defaults_to_one(db_session):
    product = _make_product(db_session)
    bundle = ProductBundle(display_name="Simple Bundle")
    db_session.add(bundle)
    db_session.flush()

    member = ProductBundleMember(bundle_id=bundle.id, product_id=product.id)
    db_session.add(member)
    db_session.commit()
    db_session.refresh(member)

    assert member.quantity == 1


def test_product_source_import_listing_id_defaults_to_none(db_session):
    """
    The existing product_id-direct flow (Phase 5.6) is completely
    unaffected by the new nullable listing_id column - existing rows and
    behavior are unchanged.
    """
    product = _make_product(db_session)
    import_row = ProductSourceImport(
        product_id=product.id,
        source_type="generic_url",
        source_url="https://example.com/products/widget",
        fetch_status=FETCH_STATUS_SUCCEEDED,
    )
    db_session.add(import_row)
    db_session.commit()
    db_session.refresh(import_row)

    assert import_row.listing_id is None
    assert import_row.product_id == product.id


def test_product_source_import_can_be_scoped_to_an_unresolved_listing(db_session):
    """
    The new path (Phase 5.10+): a fetch scoped to a Listing whose
    resolution isn't known yet - product_id is None until a human
    resolves it, per the catalogue ADR (resolution is never automatic).
    """
    listing = Listing(
        source_type="generic_url",
        source_url="https://example.com/products/mystery-listing",
    )
    db_session.add(listing)
    db_session.flush()

    import_row = ProductSourceImport(
        product_id=None,
        listing_id=listing.id,
        source_type="generic_url",
        source_url=listing.source_url,
        fetch_status=FETCH_STATUS_SUCCEEDED,
    )
    db_session.add(import_row)
    db_session.commit()
    db_session.refresh(import_row)

    assert import_row.listing_id == listing.id
    assert import_row.product_id is None


def test_product_source_import_scoped_to_a_listing_can_still_carry_product_id(db_session):
    """
    Once a Listing resolves, product_id is backfilled onto its imports so
    the existing merge service (Phase 5.5) picks them up unchanged - no
    new code needed there.
    """
    product = _make_product(db_session)
    listing = Listing(
        source_type="generic_url",
        source_url="https://example.com/products/widget",
        resolved_product_id=product.id,
    )
    db_session.add(listing)
    db_session.flush()

    import_row = ProductSourceImport(
        product_id=product.id,
        listing_id=listing.id,
        source_type="generic_url",
        source_url=listing.source_url,
        fetch_status=FETCH_STATUS_SUCCEEDED,
    )
    db_session.add(import_row)
    db_session.commit()
    db_session.refresh(import_row)

    assert import_row.listing_id == listing.id
    assert import_row.product_id == product.id
