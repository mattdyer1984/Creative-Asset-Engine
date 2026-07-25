"""
Validation prompts (Phase 1 remediation, WP-3).

Two-stage validation plus the photorealism floor. Stage 1 checks
product IDENTITY and short-circuits on failure; stage 2 checks
creative fidelity field by field. They share most of their
instruction wording and had drifted into near-duplicates - keeping
them adjacent here makes that visible.

Text moved here verbatim as part of WP-3; the snapshots under
tests/snapshots/prompts/ were captured before the move and pass
unchanged after it. Versions start at "1.0" because this migration
changed no wording.
"""

from app.prompts.core import register

# The identity field list is prompt CONTENT, not configuration - it is
# used for nothing else, and the model reads it verbatim. Building the
# template from it here means editing the list moves the content hash,
# which would not happen if the rendered text were pasted in as a
# literal. That link is the whole point of the hash.
IDENTITY_FIELDS = [
    "silhouette",
    "aspect_ratio",
    "cap_geometry",
    "corners_edges",
    "brand_placement",
    "typography_placement",
    "color",
    "materials",
    "packaging",
]

_IDENTITY_FIELD_LINES = "\n".join(f'- "{name}"' for name in IDENTITY_FIELDS)

IDENTITY = register(
    id="validation.identity",
    version="1.0",
    description=(
        "Stage 1 - does the generated image show the SAME product? Short-circuits the rest."
    ),
    template=(
"""\
The first image is a newly generated marketing creative. Every image after it is an official reference photo of the real product this creative is meant to depict. For EACH of the fields listed below, judge whether the generated image faithfully preserves the real product's visual identity as shown in the reference photos - return exactly one field_checks entry per field below. field_name in your response must be ONLY the short field_name given in quotes below (e.g. "silhouette"), never a longer description. Set preserved=true or preserved=false and give a short reason explaining your judgment - this is strictly about whether the product's own physical identity was preserved, not about scene, lighting, or composition.

Fields to check:
"""
        + _IDENTITY_FIELD_LINES
    ),
)

CREATIVE_FIDELITY = register(
    id="validation.creative_fidelity",
    version="1.0",
    description=(
        "Stage 2 - field-by-field check against the product's immutable profile."
    ),
    variables=('field_lines',),
    template=
"""\
This image was generated to recreate a marketing creative for a specific product while preserving the product's immutable physical characteristics. For EACH of the fields listed below, judge whether the generated image preserves that field's exact expected value - return exactly one field_checks entry per field below. field_name in your response must be ONLY the short field_name given in quotes below (e.g. "brand"), never the expected value or the two combined. Set preserved=true or preserved=false and give a short reason explaining your judgment. Then give one overall_explanation summarizing the assessment across every field.

Fields to check:
{field_lines}""",
)

PHOTOREALISM = register(
    id="validation.photorealism",
    version="1.0",
    description=(
        "Stage 3 - does the image read as a real photograph rather than a render?"
    ),
    template=
"""\
This is an AI-generated marketing creative. Judge its photorealism - does it look like a real photograph, not an AI generation? Assess: is the lighting realistic, are shadows believable, do materials look physically accurate, are reflections correct, how would you rate texture quality and overall image sharpness, is the perspective/geometry correct, are objects structurally intact (no warping/melting/impossible geometry), are there any visible AI-generation artefacts (extra limbs, garbled text, impossible reflections, etc.), and if any human is depicted, is their anatomy correct (use "not_applicable" if no human appears in the image at all). Give short reasons for your overall judgment.""",
)
