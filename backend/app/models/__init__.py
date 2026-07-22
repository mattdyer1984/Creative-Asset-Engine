"""
ORM models package.

Slideshow, Slide, and ProductAppearance are the live, authoritative
entities as of the Slideshow/Slide migration - Project, Product,
AnalysisRun, OCRResult, ProductReferenceImage, ProductLockProfile,
CreativeFingerprint, MarketingAnalysis, and RecreationPrompt round out
the data model. Every Analysis Artifact follows the same
AnalysisArtifactMixin pattern (plan §6.5).

ProductSourceImport (Phase 5.1 of Product Intelligence, see
MIGRATION_PLAN.md) is the one artifact-like model that deliberately does
NOT use AnalysisArtifactMixin - it records a Product Source URL fetch,
not an AI analysis run, so it has no AnalysisRun to point at. See its own
docstring, and ProductReferenceImage's, for how this affected that
table's normally-mixin-enforced analysis_run_id.

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
from app.models.product_source_import import ProductSourceImport
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
    "ProductSourceImport",
    "CreativeFingerprint",
    "MarketingAnalysis",
    "RecreationPrompt",
    "Slideshow",
    "Slide",
    "ProductAppearance",
]
