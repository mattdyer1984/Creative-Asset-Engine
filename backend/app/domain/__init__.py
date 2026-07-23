"""
Domain objects: plain Python types shared across the application that are
not tied to the database (see app.models) or the API (see app.schemas).

MarketingCreative is the first and most important of these — it's the
per-image handoff object between Import Providers (app.importers) and
everything downstream. Nothing downstream of import ever sees a file
path, a URL, or a provider name directly; it only ever sees this type.

EvidencePackage (Phase 10.5 of AI Creative Engine vNext, see
MIGRATION_PLAN.md's ADR §4a) is what an ImportProvider actually returns
as of that phase - MarketingCreative nested inside it (media_assets),
plus the package-level facts (creator/caption/hashtags/
product_references/raw) that had nowhere to live before.
"""

from app.domain.evidence_package import CreatorInfo, EvidencePackage, ProductReferenceHint
from app.domain.marketing_creative import MarketingCreative

__all__ = ["MarketingCreative", "EvidencePackage", "CreatorInfo", "ProductReferenceHint"]
