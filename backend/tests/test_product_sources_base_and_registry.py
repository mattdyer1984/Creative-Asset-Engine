"""
Tests for app.product_sources.base (the shared Protocol, typed value
union, and canonical vocabulary) and app.product_sources.registry (URL
dispatch) - Phase 5.2 of Product Intelligence, see MIGRATION_PLAN.md.

No concrete adapters exist yet (that's 5.3/5.4) - registry tests use
trivial fake adapters defined locally, exercising exactly the dispatch
contract real adapters will need to satisfy.
"""

import pytest
from pydantic import ValidationError

from app.product_sources.base import (
    CANONICAL_FIELD_VOCABULARY,
    ColorValue,
    DimensionValue,
    ListValue,
    NormalizedAttribute,
    NormalizedProductEvidence,
    NumberValue,
    ProductSourceExtraction,
    TextValue,
    validate_attribute_value,
)
from app.product_sources.registry import PRODUCT_SOURCE_ADAPTERS, get_product_source_adapter


# --- Typed value union -------------------------------------------------


def test_color_value_round_trips_label_and_hex():
    value = ColorValue(label="crimson", hex="#DC143C")
    assert value.kind == "color"
    assert value.model_dump() == {"kind": "color", "label": "crimson", "hex": "#DC143C"}


def test_color_value_hex_is_optional():
    value = ColorValue(label="crimson")
    assert value.hex is None


def test_normalized_attribute_discriminates_by_kind_when_parsed_from_a_dict():
    """
    The whole point of the discriminated union: constructing
    NormalizedAttribute from raw dict data (e.g. deserializing
    normalized_json read back from the DB) must resolve to the right
    concrete type based on the "kind" tag, not just accept anything.
    """
    attr = NormalizedAttribute.model_validate(
        {"value": {"kind": "dimension", "length": 10.0, "width": 5.0, "height": 3.0, "unit": "cm"}, "confidence": 0.9}
    )
    assert isinstance(attr.value, DimensionValue)
    assert attr.value.unit == "cm"


def test_normalized_attribute_confidence_bounds_enforced():
    with pytest.raises(ValidationError):
        NormalizedAttribute(value=TextValue(text="x"), confidence=1.5)


# --- Canonical vocabulary ------------------------------------------------


def test_vocabulary_seeded_from_exactly_the_fields_already_named():
    """
    Revision #5's discipline: the vocabulary is deliberately small,
    seeded from named fields, not speculatively expanded. This test
    exists to make an accidental unreviewed expansion visible as a
    failing test, not to forbid legitimate growth (update the expected
    set if a field is deliberately, rarely added).
    """
    expected_immutable = {
        "brand", "product_category", "shape", "dimensions", "capacity",
        "materials", "color", "branding_text", "packaging",
    }
    expected_contextual = {
        "camera_angle", "composition", "lighting", "background", "props",
        "marketing_context",
    }
    assert set(CANONICAL_FIELD_VOCABULARY) == expected_immutable | expected_contextual

    immutable = {f for f, d in CANONICAL_FIELD_VOCABULARY.items() if d.classification == "immutable"}
    contextual = {f for f, d in CANONICAL_FIELD_VOCABULARY.items() if d.classification == "contextual"}
    assert immutable == expected_immutable
    assert contextual == expected_contextual


def test_validate_attribute_value_accepts_matching_shape():
    validate_attribute_value("color", ColorValue(label="red"))
    validate_attribute_value("materials", ListValue(items=["glass", "aluminium"]))
    validate_attribute_value("capacity", NumberValue(value=500, unit="ml"))


def test_validate_attribute_value_rejects_mismatched_shape():
    with pytest.raises(ValueError, match="expects a color value"):
        validate_attribute_value("color", TextValue(text="red"))


def test_validate_attribute_value_rejects_unknown_field():
    with pytest.raises(ValueError, match="is not a canonical field"):
        validate_attribute_value("shop_rating", NumberValue(value=4.8))


# --- ProductSourceExtraction (extract()'s return type) ---------------------


def test_product_source_extraction_bundles_raw_and_normalized():
    extraction = ProductSourceExtraction(
        raw={"@type": "Product", "name": "Widget"},
        normalized=NormalizedProductEvidence(source_type="generic_url", source_url="https://example.com/p"),
    )
    assert extraction.raw == {"@type": "Product", "name": "Widget"}
    assert extraction.normalized.source_type == "generic_url"


# --- NormalizedProductEvidence --------------------------------------------


def test_normalized_product_evidence_defaults_are_empty_not_none():
    evidence = NormalizedProductEvidence(source_type="generic_url", source_url="https://example.com/p")
    assert evidence.images == []
    assert evidence.attributes == {}
    assert evidence.variants == []


# --- Registry dispatch -----------------------------------------------------


class _FakeSpecificAdapter:
    def matches(self, url: str) -> bool:
        return "specific-platform.example" in url

    def extract(self, url: str) -> ProductSourceExtraction:
        return ProductSourceExtraction(
            raw={}, normalized=NormalizedProductEvidence(source_type="fake_specific", source_url=url)
        )


class _FakeGenericAdapter:
    def matches(self, url: str) -> bool:
        return True

    def extract(self, url: str) -> ProductSourceExtraction:
        return ProductSourceExtraction(
            raw={}, normalized=NormalizedProductEvidence(source_type="fake_generic", source_url=url)
        )


@pytest.fixture()
def fake_registry(monkeypatch):
    fakes = [_FakeSpecificAdapter, _FakeGenericAdapter]
    monkeypatch.setattr("app.product_sources.registry.PRODUCT_SOURCE_ADAPTERS", fakes)
    return fakes


def test_registry_dispatches_to_the_specific_adapter_when_it_matches(fake_registry):
    adapter = get_product_source_adapter("https://specific-platform.example/product/1")
    assert isinstance(adapter, _FakeSpecificAdapter)


def test_registry_falls_through_to_the_generic_catch_all(fake_registry):
    adapter = get_product_source_adapter("https://some-other-store.example/product/1")
    assert isinstance(adapter, _FakeGenericAdapter)


def test_registry_raises_a_clear_error_if_nothing_matches(monkeypatch):
    """Only reachable if the generic fallback isn't registered - a real misconfiguration, not a URL problem."""
    monkeypatch.setattr("app.product_sources.registry.PRODUCT_SOURCE_ADAPTERS", [_FakeSpecificAdapter])
    with pytest.raises(ValueError, match="No Product Source adapter matches"):
        get_product_source_adapter("https://unmatched.example/x")


def test_real_registry_is_empty_until_5_3_and_5_4_land():
    """Documents the current, honest state - no concrete adapters exist yet."""
    assert PRODUCT_SOURCE_ADAPTERS == []
