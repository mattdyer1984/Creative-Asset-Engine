"""
MarketingCreative — the universal output of every Import Provider.

Plan reference: architecture plan §5.1.

Every ImportProvider, regardless of source (local file, ZIP, TikTok
slideshow, Amazon product page, ...), returns a list of these. This is
the *only* thing the rest of the application ever consumes when handling
a newly-imported creative — the analysis pipeline and Creative Blueprint
assembler never see a file path, a URL, or a provider name directly.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MarketingCreative:
    # The actual image data, ready to persist. Kept as raw bytes rather
    # than a file handle/path so importers that never touch local disk
    # (a future URL-based importer, say) can produce one identically.
    image_bytes: bytes

    # Best-effort display name — not guaranteed unique, not used as an
    # identifier anywhere.
    original_filename: str

    # Which importer produced this, e.g. "local_file", "zip_archive",
    # "tiktok_slideshow", "amazon_product_page". Used only for provenance
    # (surfaced in the Creative Blueprint's source_references) — never
    # branched on by the analysis pipeline.
    source_type: str

    # Where this specific creative came from within that source: an
    # absolute file path, a URL, or an archive entry name.
    source_locator: str

    imported_at: datetime

    # Provider-specific extras (e.g. a TikTok caption, an Amazon listing
    # title, a slide index within a slideshow). Carried along purely for
    # provenance/debugging — the pipeline never requires anything here.
    raw_metadata: dict = field(default_factory=dict)
