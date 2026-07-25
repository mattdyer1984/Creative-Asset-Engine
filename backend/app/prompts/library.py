"""
Canonical Reference Library prompts (Phase 1 remediation, WP-3).

Both were inline string literals buried in `prompt_spec` dict arguments
inside `reference_scoring_stage.py` - no constant, no builder, no name.
They were the least discoverable prompts in the codebase: nothing turned
them up by grepping for a prompt-shaped identifier, and neither had any
version or hash. They are also real paid calls.

Text moved here verbatim; byte-identity against the original literals is
asserted by the snapshot tests.
"""

from app.prompts.core import register

REFERENCE_SCORING = register(
    id="library.reference_scoring",
    version="1.0",
    description=(
        "Tier-2 scoring of a candidate reference image: which view it shows and "
        "whether it is usable for conditioning generation."
    ),
    template=(
        "This is a candidate reference image for a product's Canonical "
        "Reference Library - a curated set of images used to condition "
        "AI image generation so the product's real appearance is "
        "preserved. Classify which view/role this image shows, and "
        "judge its usability as a reference: is the product's front "
        "clearly visible, is it occluded by anything, is any brand "
        "text/logo readable, is packaging visible, and how would you "
        "rate the overall composition. Give short reasons for your "
        "judgments."
    ),
)

SUPERSEDE_CHECK = register(
    id="library.supersede_check",
    version="1.0",
    description=(
        "Is a new candidate a near-duplicate of an already-included reference "
        "image in the same role, or a genuinely different view?"
    ),
    template=(
        "The first image is a new candidate reference image for a "
        "product's Canonical Reference Library. The second image "
        "is an already-included reference image showing the same "
        "role/view. Judge whether the new candidate is a "
        "near-duplicate of the existing image - the same shot, "
        "same angle, carrying no meaningfully different "
        "information - rather than a genuinely different, useful "
        "view of the product."
    ),
)
