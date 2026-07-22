"""
The new Slideshow-scoped Stage pipeline (Phase 2.4 of the Slideshow/
Slide migration, now complete as of 2.4e). Parallel equivalent of
app.stages.pipeline.STAGE_PIPELINE - the same six stages, in the same
order, operating on Slideshow/Slide instead of Creative/CreativeBlueprint.
"""

from app.slideshow_stages.base import SlideshowAnalysisStage
from app.slideshow_stages.creative_fingerprint_stage import SlideCreativeFingerprintStage
from app.slideshow_stages.marketing_analysis_stage import SlideshowMarketingAnalysisStage
from app.slideshow_stages.ocr_stage import SlideOCRStage
from app.slideshow_stages.product_isolation_stage import SlideProductIsolationStage
from app.slideshow_stages.product_lock_profile_stage import SlideProductLockProfileStage
from app.slideshow_stages.recreation_prompt_stage import SlideRecreationPromptStage

SLIDESHOW_STAGE_PIPELINE: list[SlideshowAnalysisStage] = [
    SlideOCRStage(),
    SlideProductIsolationStage(),
    SlideProductLockProfileStage(),
    SlideCreativeFingerprintStage(),
    SlideshowMarketingAnalysisStage(),
    SlideRecreationPromptStage(),
]
