"""
API request/response schemas (Pydantic), kept separate from ORM models
so the two can evolve independently — the API's shape is a contract with
the frontend, the ORM's shape is a contract with the database.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProjectCreate(BaseModel):
    name: str
    notes: str | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    notes: str | None
    created_at: datetime


class ProductCreate(BaseModel):
    display_name: str
    project_id: str | None = None


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    display_name: str
    created_at: datetime


class CreativeBlueprintRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    current_ocr_result_id: str | None
    current_product_lock_profile_id: str | None
    current_creative_fingerprint_id: str | None
    current_marketing_analysis_id: str | None
    current_recreation_prompt_id: str | None
    created_at: datetime
    updated_at: datetime


class CreativeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    product_id: str | None
    product: ProductRead | None
    original_filename: str
    source_type: str
    source_locator: str
    imported_at: datetime
    blueprint: CreativeBlueprintRead


class AssignProductRequest(BaseModel):
    product_id: str | None  # null unassigns


class ProductReferenceImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_creative_id: str
    isolation_method: str
    is_current: bool
    created_at: datetime


class ProductLockProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    schema_version: str
    is_current: bool
    structured: dict
    reference_image_ids: list[str]
    created_at: datetime


class CreativeFingerprintRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    schema_version: str
    is_current: bool
    structured: dict
    created_at: datetime


class MarketingAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    is_current: bool
    narrative_text: str
    created_at: datetime


class RecreationPromptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    schema_version: str
    is_current: bool
    product_lock_profile_id: str
    creative_fingerprint_id: str
    structured: dict
    created_at: datetime


class OCRResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    schema_version: str
    is_current: bool
    raw_text: str
    structured_blocks: list[dict]
    created_at: datetime


class AnalysisRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    analysis_type: str
    provider: str
    model_name: str
    status: str
    error: str | None
    created_at: datetime


class AssembledCreativeBlueprint(BaseModel):
    """
    The single, canonical, user-facing view of a Creative (plan §1
    principle 7, §11 M7): everything the six Analysis Artifacts contain,
    assembled into one response so the frontend never has to make six
    separate calls (or think about "stages") to show what the
    application understands about a creative.
    """

    id: str  # Creative id
    status: str
    original_filename: str
    source_type: str
    source_locator: str
    imported_at: datetime
    project_id: str | None
    product_id: str | None
    product: ProductRead | None
    source_references: dict

    ocr_result: OCRResultRead | None = None
    product_reference_images: list[ProductReferenceImageRead] = []
    product_lock_profile: ProductLockProfileRead | None = None
    creative_fingerprint: CreativeFingerprintRead | None = None
    marketing_analysis: MarketingAnalysisRead | None = None
    recreation_prompt: RecreationPromptRead | None = None

    # If the Blueprint's overall status is "failed", names which stage
    # most recently failed and why - the pipeline is an implementation
    # detail the user shouldn't need to reason about, but "what broke and
    # why" still needs a clear answer when something does.
    failed_stage: str | None = None
    failed_stage_error: str | None = None
