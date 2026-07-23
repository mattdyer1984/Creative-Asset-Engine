"""
FinalOutput — Phase 10.8 of AI Creative Engine vNext (see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §15). The
composited, upload-ready artifact the Rendering Engine produces from
one accepted `GeneratedImage` candidate plus whatever `TextAsset`s Text
Intelligence chose - a distinct entity from `GeneratedImage`
deliberately, per the ADR's own reasoning: the raw model output and
the composited final artifact are different things with different
lifecycles (a `GeneratedImage` never changes once generated; a
`FinalOutput` could in principle be re-rendered from the same
`GeneratedImage` with a different `text_strategy` later, without
touching the underlying candidate at all).

`text_assets_json` is the actual list of TextAsset dicts that got
rendered (app.services.text_intelligence's own output, persisted
verbatim) - not a foreign key to a separate TextAsset table, since a
TextAsset has no identity or lifecycle apart from the one FinalOutput
it was rendered into (see that module's own docstring). Empty list is
a real, valid value (text_strategy="no_text", or nothing was eligible
to reuse) - file_path in that case is a byte-identical copy of the
source GeneratedImage's own file, not a special-cased null.
"""

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import new_uuid, utcnow


class FinalOutput(Base):
    __tablename__ = "final_outputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    generation_attempt_id: Mapped[str] = mapped_column(ForeignKey("generation_attempts.id"), nullable=False)
    generated_image_id: Mapped[str] = mapped_column(ForeignKey("generated_images.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    text_assets_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
