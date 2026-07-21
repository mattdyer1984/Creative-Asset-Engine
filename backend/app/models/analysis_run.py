"""
AnalysisRun — the traceability backbone (plan §6.5, §7).

Records HOW an Analysis Artifact was produced (provider, model, status).
The artifact itself (OCRResult, etc.) records WHAT was produced and holds
its own analysis_run_id pointing back here — the relating direction is
artifact -> run, not run -> artifact, since some stages (Product
Isolation) produce more than one artifact row per run.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import new_uuid, utcnow

# One value per Stage in STAGE_PIPELINE (plan §6). Adding a future stage
# (Brand Analysis, Compliance Analysis, ...) means adding a new value here.
ANALYSIS_TYPE_OCR = "ocr"
ANALYSIS_TYPE_PRODUCT_ISOLATION = "product_isolation"
ANALYSIS_TYPE_PRODUCT_LOCK_PROFILE = "product_lock_profile"
ANALYSIS_TYPE_CREATIVE_FINGERPRINT = "creative_fingerprint"
ANALYSIS_TYPE_MARKETING_ANALYSIS = "marketing_analysis"
ANALYSIS_TYPE_RECREATION_PROMPT = "recreation_prompt"

STATUS_PENDING = "pending"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    creative_id: Mapped[str] = mapped_column(ForeignKey("creatives.id"), nullable=False)
    analysis_type: Mapped[str] = mapped_column(String(32), nullable=False)

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_template_version: Mapped[str] = mapped_column(String(16), default="1.0")

    status: Mapped[str] = mapped_column(String(16), default=STATUS_PENDING)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
