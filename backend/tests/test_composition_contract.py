"""Composition Contract (ADR 0001 §9, Package B)."""

import pathlib

import pytest
import yaml

from app.models.analysis_run import AnalysisRun
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.services.composition_contract import (
    contract_of,
    get_current_contract,
    record_contract,
    unknown_contract,
)
from app.services.composition_schema import (
    CompositionContract,
    Device,
    Relation,
    RelationEdge,
    Zone,
    ZoneRole,
)

BENCHMARKS = pathlib.Path(__file__).parent / "benchmarks"
CASES = sorted(p for p in BENCHMARKS.iterdir() if p.is_dir())


def _contract_from_fixture(case: pathlib.Path) -> CompositionContract:
    c = yaml.safe_load((case / "ground_truth.yaml").read_text())["composition_contract"]
    return CompositionContract(
        device=Device(c["device"]),
        device_confidence=1.0,
        zones=[
            Zone(zone_id=f"{z['role']}-{i}", role=ZoneRole(z["role"]), bounds=tuple(z["bounds"]))
            for i, z in enumerate(c["zones"])
        ],
        relations=[RelationEdge(subject=r[0], relation=Relation(r[1]), object=r[2])
                   for r in c["relations"]],
        emphasis=list(c["emphasis"]),
    )


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_every_benchmark_is_expressible(case):
    """
    The schema must carry all eight cases with no free-text escape hatch. A
    general graph was rejected precisely because it would express anything -
    including things we cannot check.
    """
    contract = _contract_from_fixture(case)
    assert contract.device is not Device.UNKNOWN
    assert contract.zones and contract.relations and contract.emphasis


def test_relations_are_limited_to_the_closed_set():
    with pytest.raises(ValueError):
        RelationEdge(subject="a", relation="near", object="b")


def test_zone_bounds_must_be_normalised_and_non_empty():
    with pytest.raises(ValueError):
        Zone(zone_id="z", role=ZoneRole.TEXT, bounds=(0.5, 0.1, 0.2, 0.4))
    with pytest.raises(ValueError):
        Zone(zone_id="z", role=ZoneRole.TEXT, bounds=(0.0, 0.0, 1.4, 1.0))


def test_an_unknown_device_stays_honest():
    """Low confidence must not be dressed up as a finding."""
    contract = unknown_contract()
    assert contract.device is Device.UNKNOWN
    assert not contract.is_confident


def test_zone_lookup_finds_the_containing_region():
    """The question OCR cannot answer: which region is this text in?"""
    contract = _contract_from_fixture(BENCHMARKS / "case04_posture")
    text_zone = contract.zones_with_role(ZoneRole.TEXT)[0]
    inside = (0.08, 0.25, 0.30, 0.31)
    assert contract.zone_for(inside) is text_zone


def test_a_region_outside_every_zone_returns_none():
    contract = _contract_from_fixture(BENCHMARKS / "case04_posture")
    assert contract.zone_for((0.90, 0.02, 0.99, 0.05)) is None


def test_relations_are_queryable():
    contract = _contract_from_fixture(BENCHMARKS / "case08_fan_shelf")
    assert "product" in contract.related("price-label", Relation.BELOW)


@pytest.fixture
def slide(db_session):
    show = Slideshow()
    db_session.add(show)
    db_session.flush()
    row = Slide(slideshow_id=show.id, slide_index=0, stored_file_path="/tmp/x.jpg",
                original_filename="x.jpg", source_type="upload", source_locator="x.jpg")
    db_session.add(row)
    db_session.flush()
    return row


def test_contract_round_trips_and_supersedes(db_session, slide):
    run = AnalysisRun(analysis_type="composition_contract", provider="gemini",
                      model_name="test", status="succeeded")
    db_session.add(run)
    db_session.flush()

    original = _contract_from_fixture(BENCHMARKS / "case04_posture")
    first = record_contract(db_session, slide_id=slide.id, analysis_run_id=run.id,
                            contract=original)
    assert contract_of(first) == original

    second = record_contract(db_session, slide_id=slide.id, analysis_run_id=run.id,
                             contract=unknown_contract())
    db_session.flush()
    assert not first.is_current
    assert get_current_contract(db_session, slide.id) is second
    assert contract_of(first) == original, "history stays inspectable"


def test_absent_contract_returns_none_not_an_empty_one():
    assert contract_of(None) is None
