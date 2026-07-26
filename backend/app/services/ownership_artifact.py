"""
Text ownership artifact persistence (ADR 0001, Package A).

Records the ownership decisions that were actually applied to one slide, with
the effective policies that produced them. Re-analysis creates a new current
artifact; earlier ones stay inspectable.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.composition_contract import CompositionContractArtifact
from app.models.text_ownership_artifact import TextOwnershipArtifact
from app.services.text_ownership import OwnershipPlan, TextOwnership

#: Bumped when routing would produce different owners for identical input.
#: 1.1 - composition-informed spatial routing (Package C). The same blocks
#: can now legitimately route differently, so decisions made before and after
#: must be distinguishable rather than silently comparable.
OWNERSHIP_MODEL_VERSION = "1.1"


class OwnershipIntegrityError(RuntimeError):
    """The plan violates an invariant that must hold before it is persisted."""


def _validate(plan: OwnershipPlan, expected_block_ids: set[str] | None) -> None:
    seen: set[str] = set()
    for decision in plan.decisions:
        if decision.block_id in seen:
            raise OwnershipIntegrityError(f"{decision.block_id} appears more than once")
        seen.add(decision.block_id)
    if expected_block_ids is not None and seen != expected_block_ids:
        missing = sorted(expected_block_ids - seen)
        extra = sorted(seen - expected_block_ids)
        raise OwnershipIntegrityError(
            f"every recognised OCR block must be accounted for; missing={missing} extra={extra}"
        )


def _validate_spatial_provenance(
    plan: OwnershipPlan, contract_artifact: CompositionContractArtifact | None
) -> None:
    """
    A decision citing a zone must name the contract that zone came from.

    Otherwise the artifact records *what* was decided spatially with no way
    to check it against the geometry that decided it - and Package C's whole
    claim is that those decisions are reviewable.
    """
    if contract_artifact is not None:
        return
    cited = [d.block_id for d in plan.decisions if d.composition_zone_id]
    if cited:
        raise OwnershipIntegrityError(
            f"blocks {cited} cite composition zones but no contract was supplied; "
            "pass the contract artifact these decisions were made against"
        )


def get_current(db: Session, slide_id: str) -> TextOwnershipArtifact | None:
    return db.scalars(
        select(TextOwnershipArtifact).where(
            TextOwnershipArtifact.slide_id == slide_id,
            TextOwnershipArtifact.is_current.is_(True),
        )
    ).first()


def record_ownership(
    db: Session,
    *,
    slide_id: str,
    analysis_run_id: str,
    plan: OwnershipPlan,
    project_profile_id: str | None = None,
    contract_artifact: CompositionContractArtifact | None = None,
    effective_copy_policy: str | None = None,
    effective_overlay_policy: str | None = None,
    expected_block_ids: set[str] | None = None,
) -> TextOwnershipArtifact:
    """
    Persist one slide's ownership decisions as the new current artifact.

    The effective policies are stamped onto each block rather than referenced,
    because the profile they came from may change. A past run must stay
    explainable in its own terms.
    """
    _validate(plan, expected_block_ids)
    _validate_spatial_provenance(plan, contract_artifact)

    blocks = []
    for decision in plan.decisions:
        block = decision.model_dump(mode="json")
        block["effective_copy_policy"] = effective_copy_policy
        block["effective_overlay_policy"] = effective_overlay_policy
        blocks.append(block)

    previous = get_current(db, slide_id)
    if previous is not None:
        previous.is_current = False

    artifact = TextOwnershipArtifact(
        slide_id=slide_id,
        analysis_run_id=analysis_run_id,
        project_profile_id=project_profile_id,
        composition_contract_id=contract_artifact.id if contract_artifact else None,
        composition_contract_version=(
            contract_artifact.schema_version if contract_artifact else None
        ),
        ownership_model_version=OWNERSHIP_MODEL_VERSION,
        blocks_json=blocks,
    )
    db.add(artifact)
    db.flush()
    return artifact


def decisions_of(artifact: TextOwnershipArtifact) -> list[TextOwnership]:
    """Rehydrate the routing decisions, ignoring the stamped policy fields."""
    decisions = []
    for block in artifact.blocks_json or []:
        payload = {k: v for k, v in block.items()
                   if k not in ("effective_copy_policy", "effective_overlay_policy")}
        decisions.append(TextOwnership.model_validate(payload))
    return decisions
