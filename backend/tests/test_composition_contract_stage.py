"""
Composition Contract Stage (ADR 0001 §9, Package E).

The stage Packages B-D were waiting on. Its risk is not that the model
answers badly - it is that a bad answer LOOKS authoritative, because a
contract is structure. So most of these tests are about what happens to a
response that cannot be trusted.
"""

import pytest

from app.models.analysis_run import ANALYSIS_TYPE_COMPOSITION_CONTRACT, AnalysisRun
from app.models.provider_call import ProviderCall
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.services.composition_contract import contract_of, get_current_contract
from app.services.composition_schema import Device, Relation, ZoneRole
from app.slideshow_stages.composition_contract_stage import (
    COMPOSITION_CONTRACT_SCHEMA,
    MINIMUM_ZONE_SURVIVAL,
    SlideCompositionContractStage,
    build_contract,
)
from tests.benchmark_loader import CASES, load_contract, load_ground_truth


def _response(**overrides):
    base = {
        "device": "shelf-snapshot",
        "device_confidence": 0.9,
        "zones": [
            {"id": "product", "role": "product",
             "x_min": 0.18, "y_min": 0.12, "x_max": 0.82, "y_max": 0.70},
            {"id": "caption", "role": "text",
             "x_min": 0.12, "y_min": 0.50, "x_max": 0.88, "y_max": 0.64},
            {"id": "price-label", "role": "price",
             "x_min": 0.20, "y_min": 0.72, "x_max": 0.60, "y_max": 0.82},
        ],
        "relations": [
            {"subject": "price-label", "relation": "attached-to", "object": "product"},
        ],
        "emphasis": ["caption", "product", "price-label"],
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# A good response
# --------------------------------------------------------------------------


def test_a_well_formed_response_becomes_a_contract():
    contract, rejected = build_contract(_response())
    assert rejected == []
    assert contract.device is Device.SHELF_SNAPSHOT
    assert [z.zone_id for z in contract.zones] == ["product", "caption", "price-label"]
    assert contract.zones[2].role is ZoneRole.PRICE
    assert "product" in contract.neighbours("price-label")
    assert contract.is_confident


def test_the_schema_offers_only_the_closed_vocabularies():
    """
    The model is constrained at the request, not only corrected afterwards.
    Both matter: the schema stops most bad answers, validation catches the
    rest, and neither alone is enough.
    """
    props = COMPOSITION_CONTRACT_SCHEMA["properties"]
    assert set(props["device"]["enum"]) == {str(d) for d in Device}
    assert set(props["zones"]["items"]["properties"]["role"]["enum"]) == {
        str(r) for r in ZoneRole
    }
    assert set(props["relations"]["items"]["properties"]["relation"]["enum"]) == {
        str(r) for r in Relation
    }


# --------------------------------------------------------------------------
# Responses that cannot be trusted
# --------------------------------------------------------------------------


def test_a_relation_naming_an_undeclared_zone_is_dropped():
    """
    The Package C defect, which a model will make far more often than an
    annotator did: an edge that reads as structure and resolves to nothing.
    """
    contract, rejected = build_contract(_response(relations=[
        {"subject": "price-label", "relation": "below", "object": "shelf"},
        {"subject": "price-label", "relation": "attached-to", "object": "product"},
    ]))
    assert [e.object for e in contract.relations] == ["product"]
    assert any("shelf" in r for r in rejected)
    assert contract.unresolved_relations() == []


def test_a_self_relation_is_dropped():
    contract, rejected = build_contract(_response(relations=[
        {"subject": "product", "relation": "contains", "object": "product"},
    ]))
    assert contract.relations == []
    assert any("itself" in r for r in rejected)


def test_a_zone_with_impossible_bounds_is_dropped_not_clamped():
    """
    Clamping invents a zone the model never described and places it
    somewhere plausible-looking. Dropping it is honest; the contract is
    simply smaller.
    """
    zones = _response()["zones"] + [
        {"id": "broken", "role": "text",
         "x_min": 0.8, "y_min": 0.1, "x_max": 0.2, "y_max": 0.4},
    ]
    contract, rejected = build_contract(_response(zones=zones))
    assert "broken" not in [z.zone_id for z in contract.zones]
    assert any("broken" in r for r in rejected)


def test_out_of_range_bounds_are_dropped():
    contract, _ = build_contract(_response(zones=[
        {"id": "off", "role": "text",
         "x_min": -0.1, "y_min": 0.1, "x_max": 1.4, "y_max": 0.4},
    ]))
    assert contract.zones == []


def test_duplicate_zone_ids_are_dropped():
    zones = _response()["zones"] + [
        {"id": "product", "role": "text",
         "x_min": 0.1, "y_min": 0.1, "x_max": 0.2, "y_max": 0.2},
    ]
    contract, rejected = build_contract(_response(zones=zones))
    assert len([z for z in contract.zones if z.zone_id == "product"]) == 1
    assert any("duplicate" in r for r in rejected)


def test_emphasis_is_restricted_to_declared_zones():
    contract, rejected = build_contract(_response(emphasis=["caption", "aisle", "product"]))
    assert contract.emphasis == ["caption", "product"]
    assert any("aisle" in r for r in rejected)


def test_an_unrecognised_device_becomes_unknown_rather_than_a_guess():
    contract, rejected = build_contract(_response(device="poster"))
    assert contract.device is Device.UNKNOWN
    assert any("poster" in r for r in rejected)


def test_a_mostly_rejected_response_is_downgraded_to_unknown():
    """
    Salvaging two zones out of six and presenting a confident device is how
    a misread image becomes an authoritative-looking contract. Below the
    survival floor the device is withdrawn and downstream degrades to
    wording-only ownership, which is worse but not wrong.
    """
    zones = [
        {"id": "ok", "role": "text", "x_min": 0.1, "y_min": 0.1, "x_max": 0.4, "y_max": 0.2},
    ] + [
        {"id": f"bad{i}", "role": "text",
         "x_min": 0.9, "y_min": 0.1, "x_max": 0.2, "y_max": 0.4}
        for i in range(4)
    ]
    contract, rejected = build_contract(_response(zones=zones, device_confidence=0.95))
    assert len(contract.zones) / len(zones) < MINIMUM_ZONE_SURVIVAL
    assert contract.device is Device.UNKNOWN
    assert contract.device_confidence == 0.0
    assert not contract.is_confident
    assert any("survived validation" in r for r in rejected)


def test_a_low_confidence_answer_stays_low_confidence():
    """An admitted unknown must not be quietly promoted."""
    contract, _ = build_contract(_response(device="unknown", device_confidence=0.2))
    assert contract.device is Device.UNKNOWN
    assert not contract.is_confident


def test_a_non_numeric_confidence_does_not_crash_the_stage():
    contract, rejected = build_contract(_response(device_confidence="very"))
    assert contract.device_confidence == 0.0
    assert any("not a number" in r for r in rejected)


def test_an_empty_response_produces_an_honest_empty_contract():
    contract, rejected = build_contract({})
    assert contract.device is Device.UNKNOWN
    assert contract.zones == [] and contract.relations == []
    assert rejected, "an unusable response must say so rather than look simple"


# --------------------------------------------------------------------------
# The fixtures are the specification: inference must be able to express them
# --------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_every_hand_annotated_contract_survives_the_stage_validator(case):
    """
    Round-trips each gold-standard annotation through the same validation a
    provider response gets. If a human annotation cannot survive it, the
    validator is rejecting valid contracts and no model could ever pass.
    """
    expected = load_contract(case)
    document = load_ground_truth(case)["composition_contract"]
    response = {
        "device": document["device"],
        "device_confidence": 1.0,
        "zones": [
            {"id": z["id"], "role": z["role"],
             "x_min": z["bounds"][0], "y_min": z["bounds"][1],
             "x_max": z["bounds"][2], "y_max": z["bounds"][3]}
            for z in document["zones"]
        ],
        "relations": [
            {"subject": s, "relation": r, "object": o} for s, r, o in document["relations"]
        ],
        "emphasis": document["emphasis"],
    }
    contract, rejected = build_contract(response)
    assert rejected == [], f"{case.name}: {rejected}"
    assert contract.device is expected.device
    assert [z.zone_id for z in contract.zones] == [z.zone_id for z in expected.zones]
    assert len(contract.relations) == len(expected.relations)
    assert contract.emphasis == expected.emphasis


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


@pytest.fixture
def slideshow_with_slide(db_session, tmp_path):
    from PIL import Image

    image_path = tmp_path / "slide.png"
    Image.new("RGB", (64, 64), (240, 240, 240)).save(image_path)

    show = Slideshow()
    db_session.add(show)
    db_session.flush()
    slide = Slide(slideshow_id=show.id, slide_index=0, stored_file_path=str(image_path),
                  original_filename="slide.png", source_type="upload",
                  source_locator="slide.png")
    db_session.add(slide)
    db_session.flush()
    db_session.refresh(show)
    return show, slide


class _FakeVision:
    provider = "fake"
    model = "fake-vision"

    def __init__(self, response):
        self.response = response
        self.calls = 0

    def analyze_creative(self, *, image_bytes, prompt_spec, response_schema, usage_sink):
        self.calls += 1
        usage_sink.update({"prompt_tokens": 10, "completion_tokens": 20})
        return self.response


def _run_with(monkeypatch, db_session, slideshow, response):
    fake = _FakeVision(response)
    monkeypatch.setattr(
        "app.slideshow_stages.composition_contract_stage.default_registry.vision",
        lambda: fake,
    )
    result = SlideCompositionContractStage().run(db_session, slideshow)
    return result, fake


def test_the_stage_persists_a_contract_per_slide(monkeypatch, db_session, slideshow_with_slide):
    show, slide = slideshow_with_slide
    result, fake = _run_with(monkeypatch, db_session, show, _response())

    assert result.succeeded, result.error
    assert fake.calls == 1

    artifact = get_current_contract(db_session, slide.id)
    assert artifact is not None
    assert artifact.device == "shelf-snapshot"
    contract = contract_of(artifact)
    assert [z.zone_id for z in contract.zones] == ["product", "caption", "price-label"]


def test_the_run_is_recorded_with_its_prompt_identity(
    monkeypatch, db_session, slideshow_with_slide
):
    """
    Package E must not reintroduce an untraceable paid call. Prompt identity
    lives on ProviderCall, not AnalysisRun - a run is stage-scoped and can
    cover several calls, so a prompt recorded there would be ambiguous (WP-2).
    """
    show, _ = slideshow_with_slide
    _run_with(monkeypatch, db_session, show, _response())

    run = db_session.query(AnalysisRun).filter(
        AnalysisRun.analysis_type == ANALYSIS_TYPE_COMPOSITION_CONTRACT
    ).one()
    assert run.status == "succeeded"
    assert run.provider == "fake"

    call = db_session.query(ProviderCall).filter(
        ProviderCall.analysis_run_id == run.id
    ).one()
    assert call.prompt_id == "analysis.composition_contract"
    assert call.prompt_version == "1.0"
    assert call.prompt_content_hash
    assert call.prompt_tokens == 10 and call.completion_tokens == 20


def test_a_provider_failure_fails_the_stage_without_writing_a_contract(
    monkeypatch, db_session, slideshow_with_slide
):
    show, slide = slideshow_with_slide

    class _Broken(_FakeVision):
        def analyze_creative(self, **kwargs):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        "app.slideshow_stages.composition_contract_stage.default_registry.vision",
        lambda: _Broken(None),
    )
    result = SlideCompositionContractStage().run(db_session, show)
    assert not result.succeeded
    assert get_current_contract(db_session, slide.id) is None


def test_re_running_supersedes_rather_than_duplicates(
    monkeypatch, db_session, slideshow_with_slide
):
    show, slide = slideshow_with_slide
    _run_with(monkeypatch, db_session, show, _response())
    first = get_current_contract(db_session, slide.id)

    _run_with(monkeypatch, db_session, show, _response(device="product-hero"))
    second = get_current_contract(db_session, slide.id)

    assert second.id != first.id
    assert second.device == "product-hero"
    db_session.refresh(first)
    assert not first.is_current
