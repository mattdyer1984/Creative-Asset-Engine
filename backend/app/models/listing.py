"""
Listing — Phase 5.8 of the catalogue layer (see MIGRATION_PLAN.md's
frozen catalogue ADR). Represents one marketplace's specific sellable
page: a TikTok Shop/Amazon/Shopify URL, the commercial facts that only
ever make sense at that level (price, seller, rating, units sold,
shipping), and a resolution pointer to what it actually represents.

Deliberately NOT built on AnalysisArtifactMixin - same reasoning as
ProductSourceImport: a URL fetch isn't an AI analysis run.

Exactly one of resolved_product_id/resolved_bundle_id is set once a
Listing has been resolved; both are null while it's pending. Per the ADR:
resolution is never automatic except when a human has already chosen the
target before supplying the URL - everything else (in particular, any
inference from parsed page content, e.g. bundle member hints) requires
explicit human confirmation. Two different Listings are free to resolve
to the same Product/ProductBundle (the same physical item sold on
multiple marketplaces) - that's the whole point of Listing existing
separately from Product at all.

Commercial fields (price/seller/rating/units_sold/shipping) are plain,
nullable columns - deliberately NOT run through
CANONICAL_FIELD_VOCABULARY/ProductAttributeValue. That machinery exists
specifically to make physical product facts machine-comparable for a
future Generation/Validation Engine; nobody validates a generated image
against "units sold." Keeping these as ordinary columns here is what
guarantees they can never leak into the Product vocabulary for lack of
anywhere else to put them (see the ADR's marketplace-independence
section).

source_url uniqueness: re-fetching the same URL updates the same
Listing (get-or-create by normalized source_url, Phase 5.10's job), not
a new row - Listing is a stable identity, ProductSourceImport is the
per-fetch history underneath it.
"""

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._shared import new_uuid, utcnow


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    # Plain string, not a hardcoded enum - same reasoning as
    # ProductSourceImport.source_type. Values in use as of Phase 5.8:
    # "generic_url", "tiktok_shop".
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)

    resolved_product_id: Mapped[str | None] = mapped_column(
        ForeignKey("products.id"), nullable=True
    )
    resolved_bundle_id: Mapped[str | None] = mapped_column(
        ForeignKey("product_bundles.id"), nullable=True
    )

    price_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    seller_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    units_sold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shipping_info: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
