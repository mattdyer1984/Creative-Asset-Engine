"""
Tests for app.services.listing_import (Phase 5.10 of the catalogue layer,
see MIGRATION_PLAN.md's frozen catalogue ADR).

Same orchestration-testing style as tests/test_product_source_import_
service.py: a fake adapter registered via monkeypatch, no real HTTP.
"""

import pytest

from app.models.listing import Listing
from app.models.product import Product
from app.models.product_bundle import ProductBundle
from app.models.product_bundle_member import ProductBundleMember
from app.models.product_source_import import (
    FETCH_STATUS_FAILED,
    FETCH_STATUS_SUCCEEDED,
    ProductSourceImport,
)
from app.product_sources.base import (
    BundleMemberHint,
    NormalizedAttribute,
    NormalizedBundleEvidence,
    NormalizedListingMetadata,
    NormalizedProductEvidence,
    ProductSourceExtraction,
    TextValue,
)
from app.services.listing_import import (
    BundleMemberResolution,
    import_listing,
    resolve_listing_to_existing_bundle,
    resolve_listing_to_existing_product,
    resolve_listing_to_new_bundle,
    resolve_listing_to_new_product,
)


class _FakeSucceedingAdapter:
    def __init__(self, evidence: NormalizedProductEvidence):
        self._evidence = evidence

    def matches(self, url: str) -> bool:
        return True

    def extract(self, url: str) -> ProductSourceExtraction:
        return ProductSourceExtraction(raw={"fake": "raw-data"}, normalized=self._evidence)


class _FakeFailingAdapter:
    def matches(self, url: str) -> bool:
        return True

    def extract(self, url: str) -> ProductSourceExtraction:
        raise ValueError("simulated extraction failure")


def _register_fake(monkeypatch, adapter_instance):
    monkeypatch.setattr("app.services.listing_import.get_product_source_adapter", lambda url: adapter_instance)


def _make_product(db_session, name: str = "Test Product") -> Product:
    product = Product(display_name=name)
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    return product


# --- import_listing ---------------------------------------------------------


def test_import_listing_creates_an_unresolved_listing(db_session, monkeypatch):
    evidence = NormalizedProductEvidence(
        source_type="generic_url",
        source_url="https://shop.example/mystery",
        title="Widget",
        brand="Acme",
    )
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence))

    listing = import_listing(db_session, "https://shop.example/mystery")

    assert listing.id is not None
    assert listing.resolved_product_id is None
    assert listing.resolved_bundle_id is None
    import_row = db_session.query(ProductSourceImport).filter(
        ProductSourceImport.listing_id == listing.id
    ).one()
    assert import_row.product_id is None
    assert import_row.fetch_status == FETCH_STATUS_SUCCEEDED


def test_reimporting_the_same_url_updates_the_same_listing(db_session, monkeypatch):
    """Get-or-create by source_url, per the catalogue ADR's identity section."""
    evidence_v1 = NormalizedProductEvidence(source_type="generic_url", source_url="https://shop.example/p", title="V1")
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence_v1))
    first = import_listing(db_session, "https://shop.example/p")

    evidence_v2 = NormalizedProductEvidence(source_type="generic_url", source_url="https://shop.example/p", title="V2")
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence_v2))
    second = import_listing(db_session, "https://shop.example/p")

    assert first.id == second.id
    assert db_session.query(Listing).count() == 1
    imports = list(
        db_session.query(ProductSourceImport).filter(ProductSourceImport.listing_id == first.id)
    )
    assert len(imports) == 2
    current = [i for i in imports if i.is_current]
    assert len(current) == 1
    assert current[0].normalized_json["title"] == "V2"


def test_import_listing_denormalizes_commercial_facts_onto_the_listing(db_session, monkeypatch):
    evidence = NormalizedProductEvidence(
        source_type="generic_url",
        source_url="https://shop.example/p",
        title="Widget",
        listing=NormalizedListingMetadata(
            price_amount=29.99, price_currency="USD", seller_name="Widget Co", rating=4.5, units_sold=1200
        ),
    )
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence))

    listing = import_listing(db_session, "https://shop.example/p")

    assert listing.price_amount == 29.99
    assert listing.price_currency == "USD"
    assert listing.seller_name == "Widget Co"
    assert listing.rating == 4.5
    assert listing.units_sold == 1200


def test_import_listing_failure_is_recorded_not_raised(db_session, monkeypatch):
    _register_fake(monkeypatch, _FakeFailingAdapter())

    listing = import_listing(db_session, "https://shop.example/broken")

    import_row = db_session.query(ProductSourceImport).filter(
        ProductSourceImport.listing_id == listing.id
    ).one()
    assert import_row.fetch_status == FETCH_STATUS_FAILED
    assert "simulated extraction failure" in import_row.error
    assert listing.resolved_product_id is None


def test_bundle_evidence_is_fetch_status_succeeded_not_partial(db_session, monkeypatch):
    """
    Regression guard for the real gap found while building this
    sub-phase (see MIGRATION_PLAN.md's Phase 5.10 report): bundle
    evidence deliberately leaves brand/attributes/images empty at the top
    level, so fetch_status_for_evidence must also check `bundle` itself,
    not just those three fields.
    """
    evidence = NormalizedProductEvidence(
        source_type="generic_url",
        source_url="https://shop.example/bundle",
        bundle=NormalizedBundleEvidence(
            title="Gift Set",
            member_hints=[BundleMemberHint(label="Item A"), BundleMemberHint(label="Item B")],
        ),
    )
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence))

    listing = import_listing(db_session, "https://shop.example/bundle")

    import_row = db_session.query(ProductSourceImport).filter(
        ProductSourceImport.listing_id == listing.id
    ).one()
    assert import_row.fetch_status == FETCH_STATUS_SUCCEEDED


# --- resolve_listing_to_existing_product / resolve_listing_to_new_product ---


def test_resolve_to_existing_product_backfills_product_id_onto_imports(db_session, monkeypatch):
    evidence = NormalizedProductEvidence(source_type="generic_url", source_url="https://shop.example/p", title="Widget")
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence))
    listing = import_listing(db_session, "https://shop.example/p")
    product = _make_product(db_session)

    resolved = resolve_listing_to_existing_product(db_session, listing.id, product.id)

    assert resolved.resolved_product_id == product.id
    import_row = db_session.query(ProductSourceImport).filter(
        ProductSourceImport.listing_id == listing.id
    ).one()
    assert import_row.product_id == product.id


def test_resolve_to_new_product_creates_and_links_a_product(db_session, monkeypatch):
    evidence = NormalizedProductEvidence(source_type="generic_url", source_url="https://shop.example/p", title="Widget")
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence))
    listing = import_listing(db_session, "https://shop.example/p")

    resolved = resolve_listing_to_new_product(db_session, listing.id, "Brand New Widget")

    product = db_session.get(Product, resolved.resolved_product_id)
    assert product.display_name == "Brand New Widget"


def test_resolve_to_existing_product_rejects_unknown_product(db_session, monkeypatch):
    evidence = NormalizedProductEvidence(source_type="generic_url", source_url="https://shop.example/p")
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence))
    listing = import_listing(db_session, "https://shop.example/p")

    with pytest.raises(ValueError, match="does not exist"):
        resolve_listing_to_existing_product(db_session, listing.id, "does-not-exist")


def test_resolving_an_already_resolved_listing_raises(db_session, monkeypatch):
    evidence = NormalizedProductEvidence(source_type="generic_url", source_url="https://shop.example/p")
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence))
    listing = import_listing(db_session, "https://shop.example/p")
    product = _make_product(db_session)
    resolve_listing_to_existing_product(db_session, listing.id, product.id)

    with pytest.raises(ValueError, match="already resolved"):
        resolve_listing_to_new_product(db_session, listing.id, "Another Product")


def test_resolving_an_unknown_listing_raises(db_session):
    with pytest.raises(ValueError, match="does not exist"):
        resolve_listing_to_new_product(db_session, "does-not-exist", "Widget")


# --- resolve_listing_to_existing_bundle / resolve_listing_to_new_bundle -----


def test_resolve_to_existing_bundle_does_not_backfill_product_id(db_session, monkeypatch):
    """
    The real point of the module's own design note: a bundle listing's
    evidence describes the whole bundle, not any one member - there is no
    single correct product_id to backfill it to, so it must stay None.
    """
    evidence = NormalizedProductEvidence(source_type="generic_url", source_url="https://shop.example/bundle")
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence))
    listing = import_listing(db_session, "https://shop.example/bundle")

    bundle = ProductBundle(display_name="Existing Set")
    db_session.add(bundle)
    db_session.commit()

    resolved = resolve_listing_to_existing_bundle(db_session, listing.id, bundle.id)

    assert resolved.resolved_bundle_id == bundle.id
    import_row = db_session.query(ProductSourceImport).filter(
        ProductSourceImport.listing_id == listing.id
    ).one()
    assert import_row.product_id is None


def test_resolve_to_new_bundle_creates_bundle_and_members_mixing_existing_and_new(db_session, monkeypatch):
    evidence = NormalizedProductEvidence(
        source_type="generic_url",
        source_url="https://shop.example/bella-vita-set",
        bundle=NormalizedBundleEvidence(
            title="Bella Vita Luxury Set",
            member_hints=[
                BundleMemberHint(
                    label="G.O.A.T. Man",
                    attributes={"brand": NormalizedAttribute(value=TextValue(text="Bella Vita"), confidence=0.9)},
                ),
                BundleMemberHint(label="CEO Man"),
            ],
        ),
    )
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence))
    listing = import_listing(db_session, "https://shop.example/bella-vita-set")

    existing_product = _make_product(db_session, "G.O.A.T. Man")

    resolved = resolve_listing_to_new_bundle(
        db_session,
        listing.id,
        "Bella Vita Luxury Set",
        [
            BundleMemberResolution(existing_product_id=existing_product.id),
            BundleMemberResolution(new_product_display_name="CEO Man"),
        ],
    )

    bundle = db_session.get(ProductBundle, resolved.resolved_bundle_id)
    assert bundle.display_name == "Bella Vita Luxury Set"
    members = list(
        db_session.query(ProductBundleMember).filter(ProductBundleMember.bundle_id == bundle.id)
    )
    assert len(members) == 2
    member_product_ids = {m.product_id for m in members}
    assert existing_product.id in member_product_ids
    new_product_ids = member_product_ids - {existing_product.id}
    assert len(new_product_ids) == 1
    new_product = db_session.get(Product, new_product_ids.pop())
    assert new_product.display_name == "CEO Man"


def test_resolve_to_new_bundle_rejects_empty_member_list(db_session, monkeypatch):
    evidence = NormalizedProductEvidence(source_type="generic_url", source_url="https://shop.example/bundle")
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence))
    listing = import_listing(db_session, "https://shop.example/bundle")

    with pytest.raises(ValueError, match="at least one"):
        resolve_listing_to_new_bundle(db_session, listing.id, "Empty Set", [])


def test_member_resolution_rejects_both_fields_set(db_session, monkeypatch):
    evidence = NormalizedProductEvidence(source_type="generic_url", source_url="https://shop.example/bundle")
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence))
    listing = import_listing(db_session, "https://shop.example/bundle")
    product = _make_product(db_session)

    with pytest.raises(ValueError, match="exactly one"):
        resolve_listing_to_new_bundle(
            db_session,
            listing.id,
            "Set",
            [BundleMemberResolution(existing_product_id=product.id, new_product_display_name="Also New")],
        )


def test_member_resolution_rejects_neither_field_set(db_session, monkeypatch):
    evidence = NormalizedProductEvidence(source_type="generic_url", source_url="https://shop.example/bundle")
    _register_fake(monkeypatch, _FakeSucceedingAdapter(evidence))
    listing = import_listing(db_session, "https://shop.example/bundle")

    with pytest.raises(ValueError, match="exactly one"):
        resolve_listing_to_new_bundle(db_session, listing.id, "Set", [BundleMemberResolution()])


# --- Product-URL reference acquisition (Priority 1) -------------------


def test_resolving_a_listing_acquires_its_product_images(db_session, monkeypatch):
    """
    The gap: `import_product_source` has always downloaded the listing's
    images, but the Create flow resolves a LISTING, and that path only
    stamped product_id onto the import rows. Measured across the whole dev
    database, 78 of 79 reference images were slideshow crops and not one
    came from a product URL - while 13 imports carried a usable image URL
    and a clean 1400x1400 listing image sat unused in normalized_json.
    """
    from app.models.listing import Listing
    from app.models.product import Product
    from app.models.product_reference_image import ProductReferenceImage
    from app.models.product_source_import import ProductSourceImport
    from app.services import listing_import as module

    saved: list[str] = []

    def _fake_download(db, product_id, import_id, url, *, transport):
        image = ProductReferenceImage(
            product_id=product_id,
            source_product_source_import_id=import_id,
            isolation_method="product_url",
            file_path=f"/tmp/{len(saved)}.webp",
        )
        db.add(image)
        db.flush()
        saved.append(url)

    monkeypatch.setattr(
        "app.services.product_source_import._try_download_and_save_reference_image",
        _fake_download,
    )

    listing = Listing(source_type="generic_url", source_url="https://shop.example/p/1")
    product = Product(display_name="Probe")
    db_session.add_all([listing, product])
    db_session.flush()
    db_session.add(
        ProductSourceImport(
            listing_id=listing.id, product_id=product.id, is_current=True,
            source_type="generic_url", source_url="https://shop.example/p/1",
            fetch_status="succeeded",
            normalized_json={"images": [{"url": "https://cdn.example/clean-front.webp"}]},
        )
    )
    db_session.flush()

    acquired = module._acquire_reference_images_from_listing(db_session, listing.id, product.id)

    assert acquired == 1
    assert saved == ["https://cdn.example/clean-front.webp"]
    row = db_session.query(ProductReferenceImage).filter_by(product_id=product.id).one()
    assert row.isolation_method == "product_url"
    assert row.source_slide_id is None, "a URL reference is not slideshow-derived"


def test_a_failing_image_download_does_not_fail_the_resolve(db_session, monkeypatch):
    """One bad image URL must not block resolving the product."""
    from app.models.listing import Listing
    from app.models.product import Product
    from app.models.product_source_import import ProductSourceImport
    from app.services import listing_import as module

    def _boom(*args, **kwargs):
        raise RuntimeError("CDN unreachable")

    monkeypatch.setattr(
        "app.services.product_source_import._try_download_and_save_reference_image", _boom
    )

    listing = Listing(source_type="generic_url", source_url="https://shop.example/p/2")
    product = Product(display_name="Probe 2")
    db_session.add_all([listing, product])
    db_session.flush()
    db_session.add(
        ProductSourceImport(
            listing_id=listing.id, product_id=product.id, is_current=True,
            source_type="generic_url", source_url="https://shop.example/p/2",
            fetch_status="succeeded",
            normalized_json={"images": [{"url": "https://cdn.example/dead.webp"}]},
        )
    )
    db_session.flush()

    # Must NOT raise: acquiring references is enrichment, and losing one
    # image cannot cost the user the product they just resolved.
    assert module._acquire_reference_images_from_listing(db_session, listing.id, product.id) == 0
