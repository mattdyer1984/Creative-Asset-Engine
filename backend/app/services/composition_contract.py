"""Composition Contract persistence (ADR 0001 §9, Package B)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.composition_contract import CompositionContractArtifact
from app.services.validation_status import validate_composition_contract
from app.services.composition_schema import CompositionContract, Device


def get_current_contract(db: Session, slide_id: str) -> CompositionContractArtifact | None:
    return db.scalars(
        select(CompositionContractArtifact).where(
            CompositionContractArtifact.slide_id == slide_id,
            CompositionContractArtifact.is_current.is_(True),
        )
    ).first()


def record_contract(
    db: Session, *, slide_id: str, analysis_run_id: str, contract: CompositionContract,
    rejected: list[str] | None = None,
) -> CompositionContractArtifact:
    """Supersede the previous contract; history stays inspectable."""
    validation = validate_composition_contract(contract, rejected)

    previous = get_current_contract(db, slide_id)
    if previous is not None:
        previous.is_current = False

    artifact = CompositionContractArtifact(
        slide_id=slide_id,
        analysis_run_id=analysis_run_id,
        schema_version=contract.schema_version,
        device=str(contract.device),
        device_confidence=contract.device_confidence,
        contract_json=contract.model_dump(mode="json"),
        validation_status=str(validation.status),
        validation_json=validation.model_dump(mode="json"),
    )
    db.add(artifact)
    db.flush()
    return artifact


def contract_of(artifact: CompositionContractArtifact | None) -> CompositionContract | None:
    """
    Rehydrate, or None. Callers must handle absence rather than receive an
    empty contract that reads like a finding of "no structure".
    """
    if artifact is None or not artifact.contract_json:
        return None
    return CompositionContract.model_validate(artifact.contract_json)


def unknown_contract() -> CompositionContract:
    """An honest empty result - device unknown, zero confidence."""
    return CompositionContract(device=Device.UNKNOWN, device_confidence=0.0)
