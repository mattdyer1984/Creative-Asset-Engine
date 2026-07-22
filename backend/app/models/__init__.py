"""
ORM models package.

Slideshow, Slide, and ProductAppearance are the live, authoritative
entities as of the Slideshow/Slide migration - Project, Product,
AnalysisRun, OCRResult, ProductReferenceImage, ProductLockProfile,
CreativeFingerprint, MarketingAnalysis, and RecreationPrompt round out
the data model. Every Analysis Artifact follows the same
AnalysisArtifactMixin pattern (plan §6.5).

Creative and CreativeBlueprint are legacy: the old pipeline that wrote
to them was removed in Phase 2.7, but the models (and their tables)
remain until Phase 2.8 explicitly drops them - app.services.
slideshow_backfill still reads Creative to backfill historical data, and
several artifact tables still carry (now-nullable) legacy creative_id/
source_creative_id columns pending that same phase.
"""

from app.models.analysis_run import AnalysisRun
from app.models.creative import Creative
from app.models.creative_blueprint import CreativeBlueprint
from app.models.creative_fingerprint import CreativeFingerprint
from app.models.marketing_analysis import MarketingAnalysis
from app.models.ocr_result import OCRResult
from app.models.product import Product
from app.models.product_appearance import ProductAppearance
from app.models.product_lock_profile import ProductLockProfile
from app.models.product_reference_image import ProductReferenceImage
from app.models.project import Project
from app.models.recreation_prompt import RecreationPrompt
from app.models.slide import Slide
from app.models.slideshow import Slideshow

__all__ = [
    "Project",
    "Creative",
    "CreativeBlueprint",
    "AnalysisRun",
    "OCRResult",
    "Product",
    "ProductReferenceImage",
    "ProductLockProfile",
    "CreativeFingerprint",
    "MarketingAnalysis",
    "RecreationPrompt",
    "Slideshow",
    "Slide",
    "ProductAppearance",
]
