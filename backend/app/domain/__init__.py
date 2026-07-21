"""
Domain objects: plain Python types shared across the application that are
not tied to the database (see app.models) or the API (see app.schemas).

MarketingCreative is the first and most important of these — it's the
sole handoff object between Import Providers (app.importers) and
everything downstream. Nothing downstream of import ever sees a file
path, a URL, or a provider name directly; it only ever sees this type.
"""

from app.domain.marketing_creative import MarketingCreative

__all__ = ["MarketingCreative"]
