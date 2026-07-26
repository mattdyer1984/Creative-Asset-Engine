"""
One way to turn a benchmark annotation into live objects.

Three copies of this loader appeared across the ownership tests, each
synthesising zone ids differently. That is a quiet way to make tests pass:
if the loader invents `text-0` rather than reading the annotated `numeral`,
then no test can ever exercise a relation, because nothing the annotator
wrote resolves to anything the loader built.

The fixtures ARE the specification, so they are loaded verbatim.
"""

from __future__ import annotations

import pathlib

import yaml

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


def load_ground_truth(case: pathlib.Path | str) -> dict:
    case = BENCHMARKS / case if isinstance(case, str) else case
    return yaml.safe_load((case / "ground_truth.yaml").read_text())


def load_contract(case: pathlib.Path | str, *, device_confidence: float = 1.0):
    """Build the contract exactly as annotated - ids included."""
    document = load_ground_truth(case)["composition_contract"]
    return CompositionContract(
        device=Device(document["device"]),
        device_confidence=device_confidence,
        zones=[
            Zone(zone_id=z["id"], role=ZoneRole(z["role"]), bounds=tuple(z["bounds"]))
            for z in document["zones"]
        ],
        relations=[
            RelationEdge(subject=s, relation=Relation(r), object=o)
            for s, r, o in document["relations"]
        ],
        emphasis=list(document["emphasis"]),
    )


def zone(contract: CompositionContract, zone_id: str) -> Zone:
    """Fetch a zone by its annotated id, failing loudly if it is gone."""
    for candidate in contract.zones:
        if candidate.zone_id == zone_id:
            return candidate
    raise KeyError(f"{zone_id!r} is not a zone in this contract")
