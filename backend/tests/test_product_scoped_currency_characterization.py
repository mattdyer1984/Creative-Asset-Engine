"""
Characterization tests for a known, pre-existing bug in the current
Creative-centric data model (flagged in the architecture review that
preceded the Slideshow/Slide migration): "current" state for
product-scoped artifacts is tracked two different ways at once.

- ProductReferenceImage.is_current is scoped to product_id only - there
  is no per-Creative pointer to "which reference images did *this*
  creative's isolation run produce." The assembled Blueprint's
  product_reference_images field is populated by a bare
  `WHERE product_id=... AND is_current=True` query (see
  services/creative_blueprint.py).
- ProductLockProfile is *also* is_current-scoped to product_id, but each
  CreativeBlueprint additionally pins current_product_lock_profile_id to
  the exact row its own stage run produced, and the assembled Blueprint
  fetches that row directly by id - not via the is_current flag.

Net effect: two Creatives assigned to the same Product interfere with
each other's assembled Blueprint for reference images (no per-creative
pin exists), but NOT for the lock profile itself (a per-creative pin
does exist, even though its is_current flag ends up lying).

These tests PIN DOWN that current (buggy, asymmetric) behavior - they do
not assert it's correct. Phase 2 of the Slideshow/Slide migration
replaces this entire mechanism with ProductAppearance, at which point
the scenario described here (a Creative-level pointer racing a
Product-level is_current flag) stops existing and this file should be
deleted, not "fixed". Until then it's a deliberate regression trip-wire:
if this behavior changes before Phase 2 lands, something unrelated broke it.
"""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.db import get_db
from app.main import app
from tests.fakes import FakeAIProviderRegistry


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _import_creative(client) -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (300, 300), color=(210, 160, 120)).save(buffer, format="JPEG")
    creative = client.post(
        "/api/creatives/import",
        files={"files": ("test.jpg", io.BytesIO(buffer.getvalue()), "image/jpeg")},
    ).json()[0]
    return creative["id"]


def test_two_creatives_on_the_same_product_interfere_via_reference_images(client, monkeypatch):
    """
    A and B are both assigned to Product P. Running Product Isolation for
    B after A silently changes what A's OWN assembled Blueprint shows for
    product_reference_images, even though nothing about A was touched -
    because that field is read via a product-scoped is_current query with
    no per-creative pin, not via any pointer on A's own Blueprint.
    """
    monkeypatch.setattr(
        "app.stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )

    product = client.post("/api/products", json={"display_name": "Sunrise Orange Juice"}).json()
    creative_a = _import_creative(client)
    creative_b = _import_creative(client)
    client.post(f"/api/creatives/{creative_a}/assign-product", json={"product_id": product["id"]})
    client.post(f"/api/creatives/{creative_b}/assign-product", json={"product_id": product["id"]})

    client.post(f"/api/creatives/{creative_a}/stages/product_isolation/rerun")

    blueprint_a = client.get(f"/api/creatives/{creative_a}/blueprint").json()
    assert len(blueprint_a["product_reference_images"]) == 1
    reference_image_from_a = blueprint_a["product_reference_images"][0]
    assert reference_image_from_a["source_creative_id"] == creative_a

    # B's isolation run flips A's reference image to is_current=False as a
    # side effect (both share product_id=P), with nothing recorded on A's
    # own Blueprint to say "keep showing what A produced."
    client.post(f"/api/creatives/{creative_b}/stages/product_isolation/rerun")

    blueprint_a_after = client.get(f"/api/creatives/{creative_a}/blueprint").json()
    assert len(blueprint_a_after["product_reference_images"]) == 1
    reference_image_now_shown_for_a = blueprint_a_after["product_reference_images"][0]

    # Characterizing the bug: A's Blueprint now shows B's reference image,
    # not its own - the row id changed, and it's now sourced from B.
    assert reference_image_now_shown_for_a["id"] != reference_image_from_a["id"]
    assert reference_image_now_shown_for_a["source_creative_id"] == creative_b


def test_lock_profile_pointer_stays_pinned_despite_is_current_flipping(client, monkeypatch):
    """
    Contrast case: ProductLockProfile IS pinned per-Creative (via
    CreativeBlueprint.current_product_lock_profile_id, fetched by id, not
    by the is_current flag) - so A's assembled Blueprint keeps showing
    the profile A's own stage run produced even after B's run flips
    is_current for the whole Product. The *content* shown is correct;
    only the row's own is_current flag ends up lying.
    """
    monkeypatch.setattr(
        "app.stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )

    product = client.post("/api/products", json={"display_name": "Sunrise Orange Juice"}).json()
    creative_a = _import_creative(client)
    creative_b = _import_creative(client)
    client.post(f"/api/creatives/{creative_a}/assign-product", json={"product_id": product["id"]})
    client.post(f"/api/creatives/{creative_b}/assign-product", json={"product_id": product["id"]})

    client.post(f"/api/creatives/{creative_a}/stages/product_lock_profile/rerun")
    profile_a_id = client.get(f"/api/creatives/{creative_a}/blueprint").json()["product_lock_profile"]["id"]

    client.post(f"/api/creatives/{creative_b}/stages/product_lock_profile/rerun")

    blueprint_a_after = client.get(f"/api/creatives/{creative_a}/blueprint").json()
    # Unlike reference images, A's own lock profile id is still what's shown...
    assert blueprint_a_after["product_lock_profile"]["id"] == profile_a_id
    # ...even though its is_current flag has been flipped off by B's run,
    # despite still being the row actively referenced by A's Blueprint.
    assert blueprint_a_after["product_lock_profile"]["is_current"] is False
