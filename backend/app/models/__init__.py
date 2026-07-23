"""
ORM models package.

Slideshow, Slide, and ProductAppearance are the live, authoritative
entities as of the Slideshow/Slide migration - Project, Product,
AnalysisRun, OCRResult, ProductReferenceImage, ProductLockProfile,
CreativeFingerprint, MarketingAnalysis, and CreativeSpecification (renamed
from RecreationPrompt in Phase 8.1, see MIGRATION_PLAN.md) round out the
data model. Every Analysis Artifact follows the same AnalysisArtifactMixin
pattern (plan §6.5).

ProductSourceImport (Phase 5.1 of Product Intelligence, see
MIGRATION_PLAN.md) is the one artifact-like model that deliberately does
NOT use AnalysisArtifactMixin - it records a Product Source URL fetch,
not an AI analysis run, so it has no AnalysisRun to point at. See its own
docstring, and ProductReferenceImage's, for how this affected that
table's normally-mixin-enforced analysis_run_id.

GenerationReferenceSet and GenerationReferenceSetImage (Phase 9.1,
Product Lock v2 - see MIGRATION_PLAN.md's "ADR: Canonical Product
Reference") record which Library images (ProductReferenceImage rows
with library_status="included") a specific generation call actually
selected. The Canonical Reference Library itself is not a new table -
it's a query over ProductReferenceImage's four new nullable columns
(quality_score/quality_reasons_json/role/library_status), the same
compute-on-read pattern used throughout this codebase.

Listing, ProductBundle, and ProductBundleMember (Phase 5.8, catalogue
layer - see MIGRATION_PLAN.md's frozen catalogue ADR) sit above Product
Intelligence rather than inside it: Listing owns marketplace/commercial
facts and resolves to either a Product or a ProductBundle; ProductBundle
is a pure composition of Products, never a Product subtype or a new
Product Profile vocabulary. See the ADR for the full reasoning.

GenerationAttempt and QualityAssessment (Phase 10.2, AI Creative Engine
vNext - see MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext")
group N candidate GeneratedImage rows produced by one Decision Engine
plan, and record the Quality Engine's per-candidate accept/reject
verdict. QualityAssessment references ImageValidationResult for the
Product Fidelity dimension rather than duplicating it - see that
model's own docstring for why.

SceneAnalysis (Phase 10.4, AI Creative Engine vNext - see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §8) holds one
slide's detected regions (bounding box, region_type, importance_tier) -
the input Creative Intelligence uses to decide what's safe to
transform. Part of SLIDESHOW_STAGE_PIPELINE, unlike the Generation/
Quality Engine models above.

EvidenceSource and ProjectProduct (Phase 10.5, AI Creative Engine vNext
- see MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §3/§4b) are
the Project-role-reversal + Evidence Engine pieces: EvidenceSource is a
Project-scoped event-log row recording one ImportProvider call's
package-level facts (Slideshow.evidence_source_id points back to it,
many-to-one); ProjectProduct is a pure membership join (mirroring
ProductBundleMember's shape) recording which Products a Project's work
involves, without Product moving into Project's ownership.

BundleComposition and BundleCompositionMember (Phase 10.7, AI Creative
Engine vNext - see MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext"
§12's "Bundle Composition" addendum) let one generation attempt compose
several distinct, independently-selected products into a single scene
without relaxing Product Lock's own one-product-at-a-time reasoning
anywhere else - see that model's own docstring for the full design.

Creative and CreativeBlueprint are legacy: the old pipeline that wrote
to them was removed in Phase 2.7, but the models (and their tables)
remain until Phase 2.8 explicitly drops them - app.services.
slideshow_backfill still reads Creative to backfill historical data, and
several artifact tables still carry (now-nullable) legacy creative_id/
source_creative_id columns pending that same phase.
"""

from app.models.analysis_run import AnalysisRun
from app.models.bundle_composition import BundleComposition, BundleCompositionMember
from app.models.creative import Creative
from app.models.creative_blueprint import CreativeBlueprint
from app.models.creative_fingerprint import CreativeFingerprint
from app.models.creative_specification import CreativeSpecification
from app.models.evidence_source import EvidenceSource
from app.models.generated_image import GeneratedImage
from app.models.generation_attempt import GenerationAttempt
from app.models.generation_reference_set import GenerationReferenceSet
from app.models.generation_reference_set_image import GenerationReferenceSetImage
from app.models.image_validation_result import ImageValidationResult
from app.models.listing import Listing
from app.models.marketing_analysis import MarketingAnalysis
from app.models.narrative_structure import NarrativeStructure
from app.models.ocr_result import OCRResult
from app.models.product import Product
from app.models.product_appearance import ProductAppearance
from app.models.product_bundle import ProductBundle
from app.models.product_bundle_member import ProductBundleMember
from app.models.product_lock_profile import ProductLockProfile
from app.models.product_reference_image import ProductReferenceImage
from app.models.product_source_import import ProductSourceImport
from app.models.project import Project
from app.models.project_product import ProjectProduct
from app.models.quality_assessment import QualityAssessment
from app.models.scene_analysis import SceneAnalysis
from app.models.slide import Slide
from app.models.slideshow import Slideshow

__all__ = [
    "Project",
    "ProjectProduct",
    "EvidenceSource",
    "Creative",
    "CreativeBlueprint",
    "AnalysisRun",
    "OCRResult",
    "Product",
    "ProductReferenceImage",
    "ProductLockProfile",
    "ProductSourceImport",
    "Listing",
    "ProductBundle",
    "ProductBundleMember",
    "CreativeFingerprint",
    "MarketingAnalysis",
    "NarrativeStructure",
    "CreativeSpecification",
    "GeneratedImage",
    "GenerationReferenceSet",
    "GenerationReferenceSetImage",
    "ImageValidationResult",
    "GenerationAttempt",
    "QualityAssessment",
    "SceneAnalysis",
    "BundleComposition",
    "BundleCompositionMember",
    "Slideshow",
    "Slide",
    "ProductAppearance",
]
