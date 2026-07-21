"""
Creative import orchestration.

This is the one place that knows both "how to get a MarketingCreative"
(via the Import Provider registry) and "how to persist one" (Creative +
CreativeBlueprint rows, file on disk). The API router calls this and
nothing else - it never talks to an importer or the storage module
directly.

From M2 onward, this is also where a newly-created CreativeBlueprint
gets handed to the Analysis Orchestrator to move it from "imported" to
"analyzing". That hand-off doesn't exist yet.
"""

import json

from sqlalchemy.orm import Session

from app.domain import MarketingCreative
from app.importers import get_importer
from app.models.creative import Creative
from app.models.creative_blueprint import CreativeBlueprint
from app.storage import save_creative_original


def import_creatives(
    db: Session,
    source_type: str,
    source_config: dict,
    project_id: str | None,
) -> list[Creative]:
    """
    Resolve the requested Import Provider, run it, and persist every
    MarketingCreative it returns as its own independent Creative +
    CreativeBlueprint (batch = independent items, per the plan's import
    flow, §10).
    """
    importer = get_importer(source_type)
    marketing_creatives = importer.import_source(source_config)

    return [
        _persist_marketing_creative(db, mc, project_id)
        for mc in marketing_creatives
    ]


def _persist_marketing_creative(
    db: Session,
    marketing_creative: MarketingCreative,
    project_id: str | None,
) -> Creative:
    creative = Creative(
        project_id=project_id,
        original_filename=marketing_creative.original_filename,
        source_type=marketing_creative.source_type,
        source_locator=marketing_creative.source_locator,
        raw_metadata_json=json.dumps(marketing_creative.raw_metadata),
        imported_at=marketing_creative.imported_at,
        # placeholder; replaced below once we have the generated id
        stored_file_path="",
    )
    db.add(creative)
    db.flush()  # assigns creative.id without committing yet

    stored_path = save_creative_original(
        creative.id, marketing_creative.original_filename, marketing_creative.image_bytes
    )
    creative.stored_file_path = str(stored_path)

    blueprint = CreativeBlueprint(
        creative_id=creative.id,
        source_references_json=json.dumps(
            {
                "source_type": marketing_creative.source_type,
                "source_locator": marketing_creative.source_locator,
                "raw_metadata": marketing_creative.raw_metadata,
            }
        ),
    )
    db.add(blueprint)

    db.commit()
    db.refresh(creative)
    return creative
