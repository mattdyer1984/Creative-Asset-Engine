"""
ORM models package.

Project, Creative, CreativeBlueprint, AnalysisRun, OCRResult, Product,
ProductReferenceImage, ProductLockProfile, CreativeFingerprint,
MarketingAnalysis, and RecreationPrompt exist as of M6 - the full data
model from the plan (§7) is now complete. Every Analysis Artifact
follows the same AnalysisArtifactMixin pattern (plan §6.5).
"""

from app.models.analysis_run import AnalysisRun
from app.models.creative import Creative
from app.models.creative_blueprint import CreativeBlueprint
from app.models.creative_fingerprint import CreativeFingerprint
from app.models.marketing_analysis import MarketingAnalysis
from app.models.ocr_result import OCRResult
from app.models.product import Product
from app.models.product_lock_profile import ProductLockProfile
from app.models.product_reference_image import ProductReferenceImage
from app.models.project import Project
from app.models.recreation_prompt import RecreationPrompt

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
]
