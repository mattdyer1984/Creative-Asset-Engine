"""
Analysis-stage prompts (Phase 1 remediation, WP-3).

Text moved here verbatim from the provider adapters and slideshow stage modules as part of WP-3. The
snapshot tests under tests/snapshots/prompts/ were captured BEFORE the
move and pass unchanged after it, which is what proves nothing was
reworded in transit.

Versions all start at "1.0": this migration deliberately changes no
wording, so claiming anything else would misrepresent the history. The
first real edit to any prompt bumps its own version.
"""

from app.prompts.core import register

EXTRACT_TEXT = register(
    id="ocr.extract_text",
    version="1.0",
    description=(
        "Reads every piece of text in a slide, tagging each as printed on the product or overlaid by the editor."
    ),
    template=
"""\
Extract all visible text from this marketing image. Return the complete raw text, plus a structured breakdown of each distinct text element, its marketing role, its normalized bounding box (x_min/y_min/x_max/y_max, each 0.0-1.0, measured against the full image width/height) - as precise as you can read it from the actual rendered position of that text - and its surface: 'physical' if it's printed, molded, or displayed on a real object the camera photographed (product packaging, a shelf price tag, a sign, a screen), or 'overlay' if it was added digitally on top of the photo or video afterward by whoever created or edited it (a social-media caption, meme-style commentary, a watermark, a burned-in subtitle) and was never part of the physical scene itself. If you're unsure, prefer 'physical'.""",
)

PRODUCT_ISOLATION = register(
    id="analysis.product_isolation",
    version="1.0",
    description=(
        "Locates the featured product and returns its bounding box."
    ),
    template=
"""\
Identify the bounding box(es) of the featured product in this marketing image - the physical product being sold, not background props, people, or decorative elements. Return coordinates as fractions of the image width/height (0.0 to 1.0), a confidence score, and brief notes on what you identified. Some images are narrative/story slides with no product actually shown - a person talking to camera, a text-only caption card, a reaction shot. If no real product is visible anywhere in this image, return an empty bounding_boxes array - this is a normal, expected, and CORRECT answer for those images, not a failure to find something that must be there. Never force a box around a hand, a prop, or the background just to return a non-empty result.""",
)

PRODUCT_LOCK_PROFILE = register(
    id="analysis.product_lock_profile",
    version="1.0",
    description=(
        "Records the product's immutable physical characteristics - the basis of Product Lock."
    ),
    template=
"""\
Analyze the featured product in this marketing image and produce a detailed, structured description covering its category, type, shape and proportions, packaging, materials, surface finish, colors, branding, any visible labels or printed text, distinguishing visual features, viewing angle, perspective, lighting characteristics, and its approximate scale within the frame. For labels_and_text, only include text that is actually printed, embossed, or molded onto the product's own packaging or body - never text overlaid onto this photo afterward, such as a social-media caption, meme-style commentary, a retailer's price sticker or shelf tag, or a watermark. If you're unsure whether a piece of text is part of the product itself or was overlaid onto the photo, leave it out. In immutable_characteristics, list the visual traits that must NEVER change if this exact product is recreated in a new marketing image.""",
)

CREATIVE_FINGERPRINT = register(
    id="analysis.creative_fingerprint",
    version="1.0",
    description=(
        "Describes the slide's visual style, composition and emotional trigger."
    ),
    template=
"""\
Analyze this marketing creative and produce a structured description of its overall visual style, marketing objective, emotional appeal, target audience, color palette, typography style, layout and composition, background environment, lighting style, graphic style, product prominence, marketing angle, visual hierarchy, trust elements (e.g. certifications, guarantees, testimonials), promotional devices (e.g. discounts, urgency, social proof), object placement (how the product and key objects are physically arranged/positioned in the frame), and the specific emotional trigger this creative pulls (more granular than a general emotional-appeal tag - name the precise psychological lever, e.g. 'fear of missing a limited window' rather than just 'urgency').""",
)

SCENE_INTELLIGENCE = register(
    id="analysis.scene_intelligence",
    version="1.0",
    description=(
        "Splits the slide into regions and decides which must be preserved."
    ),
    template=
"""\
Segment this marketing creative into its distinct visual regions and classify each one. For every region, give a normalized bounding box (x_min/y_min/x_max/y_max, 0.0-1.0), a region_type (primary_subject, secondary_subject, product, human_subject, environment, background, prop, decorative_element, or negative_space), and an importance_tier rating how safe that region is to change if this creative were regenerated: essential (must never change - the product itself, a person's hands/pose directly interacting with it, its exact positioning), important (should closely match - overall pose, action, composition), context (the general setting/room type - can be replaced with a different instance of the same category), incidental (furniture, decor - free to change), or replaceable (wall art, background clutter - safe to remove or swap freely). Give a short note explaining each region's classification.""",
)

MARKETING_ANALYSIS = register(
    id="analysis.marketing_analysis",
    version="1.0",
    description=(
        "Infers audience, angle and narrative from the primary slide's fingerprint."
    ),
    variables=('fingerprint_json',),
    template=
"""\
Given the following structured analysis of a marketing creative, write a clear, readable prose summary (2-4 short paragraphs) connecting these facts into a coherent narrative: what the creative is trying to achieve, who it's targeting, what emotional appeal it uses, and why it works as marketing. Write for a marketer who wants to understand the strategy at a glance, not just a list of facts.

Structured analysis (JSON):
{fingerprint_json}""",
)

NARRATIVE_STRUCTURE = register(
    id="analysis.narrative_structure",
    version="1.0",
    description=(
        "Assigns a narrative beat to each slide across the whole slideshow."
    ),
    variables=('slides_json',),
    template=
"""\
The following is the on-screen text extracted from each slide of a marketing slideshow, in display order. Classify each slide's role in the overall persuasion narrative using exactly one of: hook (grabs attention), story (builds context/relatability), reveal (introduces the product/solution), proof (evidence/credibility - reviews, results, comparisons), cta (call to action), or other (doesn't fit the above). Then write a short 1-2 sentence summary of the overall arc.

Slides:
{slides_json}""",
)
