"""
The Stage pipeline (plan §6.2). Complete as of M6 - all 6 stages from
the plan are now present, in the exact order specified. Any future stage
(Brand Analysis, Compliance Analysis, Image Generation) is added the
same way: implement AnalysisStage, add one line here.
"""

from app.stages.base import AnalysisStage
from app.stages.creative_fingerprint_stage import CreativeFingerprintStage
from app.stages.marketing_analysis_stage import MarketingAnalysisStage
from app.stages.ocr_stage import OCRStage
from app.stages.product_isolation_stage import ProductIsolationStage
from app.stages.product_lock_profile_stage import ProductLockProfileStage
from app.stages.recreation_prompt_stage import RecreationPromptStage

STAGE_PIPELINE: list[AnalysisStage] = [
    OCRStage(),
    ProductIsolationStage(),
    ProductLockProfileStage(),
    CreativeFingerprintStage(),
    MarketingAnalysisStage(),
    RecreationPromptStage(),
]
