"""
The Slideshow-scoped Stage pipeline (Phase 2.4 of the Slideshow/Slide
migration, now complete as of 2.4e). Originally a parallel equivalent of
app.stages.pipeline.STAGE_PIPELINE, the six-stage old pipeline this
package replaced - that module no longer exists (deleted in the Phase 2
engineering review once this package had no remaining callers), so this
package is now the only pipeline, not a parallel one.

Narrative Structure (Phase 7.2 of the Narrative pass, see
MIGRATION_PLAN.md) added after Marketing Analysis - no ordering
dependency between the two either way (both slideshow-scoped and
narrative-adjacent; Narrative Structure depends on OCR, Marketing
Analysis depends on Creative Fingerprint), grouped here for pipeline
readability.

Composition Contract (ADR 0001 §9, Package E) added after Scene
Intelligence and before Creative Specification. It depends on nothing but
the slide's raw image, but it must precede any stage that reasons about
spatial ownership - which is the point of it existing.

Scene Intelligence (Phase 10.4 of AI Creative Engine vNext, see
MIGRATION_PLAN.md's ADR §8) added after Creative Fingerprint - no
ordering dependency either way (it only reads the slide's raw image,
same as OCR/Product Isolation), grouped there for the same
creative/visual-analysis-adjacency reasoning as Narrative Structure's
own placement above.
"""

from app.slideshow_stages.base import SlideshowAnalysisStage
from app.slideshow_stages.creative_fingerprint_stage import SlideCreativeFingerprintStage
from app.slideshow_stages.creative_profile_stage import SlideshowCreativeProfileStage
from app.slideshow_stages.composition_contract_stage import SlideCompositionContractStage
from app.slideshow_stages.creative_specification_stage import SlideCreativeSpecificationStage
from app.slideshow_stages.marketing_analysis_stage import SlideshowMarketingAnalysisStage
from app.slideshow_stages.narrative_structure_stage import SlideshowNarrativeStructureStage
from app.slideshow_stages.ocr_stage import SlideOCRStage
from app.slideshow_stages.product_isolation_stage import SlideProductIsolationStage
from app.slideshow_stages.product_lock_profile_stage import SlideProductLockProfileStage
from app.slideshow_stages.scene_intelligence_stage import SceneIntelligenceStage

SLIDESHOW_STAGE_PIPELINE: list[SlideshowAnalysisStage] = [
    SlideOCRStage(),
    SlideProductIsolationStage(),
    SlideProductLockProfileStage(),
    SlideCreativeFingerprintStage(),
    SceneIntelligenceStage(),
    SlideCompositionContractStage(),
    SlideshowCreativeProfileStage(),
    SlideshowMarketingAnalysisStage(),
    SlideshowNarrativeStructureStage(),
    SlideCreativeSpecificationStage(),
]
