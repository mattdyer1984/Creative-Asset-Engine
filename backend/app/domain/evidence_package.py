"""
EvidencePackage — Phase 10.5 of AI Creative Engine vNext (see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §4a). The real
output of every `ImportProvider`, reworked from a bare
`list[MarketingCreative]` - a small, real, if additive-in-spirit,
breaking change to already-shipped code (`ImportProvider`,
`LocalFileImporter`), per that ADR's own explicit §4a/§17 flagging.

`MarketingCreative` itself is unchanged - it stays the per-image type,
nested inside this package's `media_assets` rather than replaced.

Every other field carries a piece of provenance that had nowhere to
live before this: who made the import (`creator`), what they said
about it (`caption`/`hashtags`), what the platform itself already
knows about products in it (`product_references`), and the
untranslated raw response (`raw`) for audit/debugging - the same "one
fetch, keep the raw payload" precedent
`app.product_sources.base.ProductSourceExtraction` already established
for URL-based product evidence, applied to the other half of evidence
intake.

`expected_count`/`downloaded_count`/`failed_assets` (the Critical
TikTok Slideshow Import Fix, see MIGRATION_PLAN.md) exist for exactly
one reason: `import_source`'s return value is the *only* channel an
`ImportProvider`'s internal per-asset accounting can cross a module
boundary through, and the import integrity gate
(app.services.import_integrity) needs that accounting to catch a
partial, silently-incomplete import instead of trusting
`len(media_assets)` as ground truth. All three default to their
"nothing to report" value (`None`/`0`/`[]`) so `LocalFileImporter`'s
existing construction call needs zero changes - a manual upload has no
independent "expected count" to compare against (every file the user
selected trivially is the expected set), the correct, expected value
for that source, not a gap to work around.
"""

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.marketing_creative import MarketingCreative


@dataclass
class CreatorInfo:
    handle: str | None = None
    display_name: str | None = None
    profile_url: str | None = None


@dataclass
class ProductReferenceHint:
    """
    A platform-native product tag an importer's source page already
    exposes (e.g. a TikTok post tagged against TikTok Shop listings) -
    evidence *about* products discovered incidentally during creative
    import, distinct in kind from `ProductSourceImport`'s explicit "the
    user gave us this product URL." No real importer populates this yet
    (`LocalFileImporter` never has any product tags to expose) - the
    shape exists so a future platform-native importer doesn't need a
    schema change to start using it.
    """

    label: str
    external_id: str | None = None
    url: str | None = None


@dataclass
class EvidencePackage:
    source_platform: str
    media_assets: list[MarketingCreative]
    original_url: str | None = None
    creator: CreatorInfo | None = None
    caption: str | None = None
    hashtags: list[str] = field(default_factory=list)
    product_references: list[ProductReferenceHint] = field(default_factory=list)
    platform_metadata: dict = field(default_factory=dict)
    imported_at: datetime | None = None
    raw: dict = field(default_factory=dict)
    # Ground truth from source metadata (e.g. TikTok's own reported image
    # count), independent of how many actually made it into media_assets -
    # None for a source with no such independent count (LocalFileImporter).
    expected_count: int | None = None
    # Raw count of files/bytes actually fetched, before validation - can
    # legitimately differ from len(media_assets) (e.g. a file that
    # downloaded but failed to open as a real image).
    downloaded_count: int = 0
    # Every asset that didn't make it into media_assets, with why -
    # {"index": int | None, "reason": str}. Never silently dropped.
    failed_assets: list[dict] = field(default_factory=list)
