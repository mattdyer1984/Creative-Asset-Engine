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

COMPOSITION_CONTRACT = register(
    id="analysis.composition_contract",
    version="1.0",
    description=(
        "Infers the slide's layout device, zones and spatial relations "
        "(ADR 0001 §9). The vocabularies are closed; the model chooses from "
        "them and may answer `unknown`."
    ),
    template=
"""\
Describe the LAYOUT of this marketing creative - how it is arranged, not what it depicts.

First name the compositional device, choosing exactly one of: split-comparison (one image divided into contrasting halves), grid-collage (four or more panels in a grid), side-by-side-comparison (two separate subjects placed next to each other), product-hero (one product dominating the frame), scene-with-caption (a photographed scene with text laid over it), shelf-snapshot (a product photographed in a retail setting), diagram-with-callout (an illustration annotated with a pointer or highlight), screen-in-scene (a display or monitor within a wider scene), or unknown. Answer `unknown` with a low confidence rather than guessing - a wrong device is worse than an admitted one. Give device_confidence between 0.0 and 1.0.

Then list the ZONES. Each zone gets a short lowercase id unique within this image and descriptive of what it is (`caption`, `price-label`, `left-stack`, `numeral-rule`), one role, and a normalized bounding box (x_min/y_min/x_max/y_max, 0.0-1.0). The roles are:
- text: copy the design has placed deliberately, as part of the creative
- caption: platform caption furniture laid over the top, of the kind a poster adds
- subject: a person, animal or scene that is the focus
- product: the item being sold, including its packaging
- callout: an annotation pointing into the subject, such as a highlighted body part
- price: a shelf edge label or price tag
- screen: a phone, monitor or television display within the scene
- graphic: a rule, divider, underline or design mark carrying NO text
- negative-space: deliberately empty area

Include `graphic` zones even though they contain no words - a rule under a heading or a divider splitting a comparison is part of the design and must be listed. Include a zone for the caption if there is one.

Then list the RELATIONS between zones. Each relation is a subject zone id, one of above / below / left-of / right-of / attached-to / points-to / splits / flanks / contains, and an object zone id. BOTH ids must be zones you listed above - do not name anything else. Prefer relations that carry meaning a reader would lose if they were missing: which product a price belongs to, what a callout points at, what a divider splits.

Finally give `emphasis`: the zone ids in the order the eye reaches them, most prominent first. Every id must be one you listed.""",
)

TYPOGRAPHY_SYSTEM = register(
    id="analysis.typography_system",
    version="1.0",
    description=(
        "Reads a designed creative's type system as a design system - roles, "
        "not a font name (ADR 0001 §10). Only called for projects whose text "
        "mode is designed typography."
    ),
    template=
"""\
Read the TYPE SYSTEM of this designed creative. Describe it as a design system - the rules a designer would hand to someone rebuilding it - not as a description of what the words say.

Name the primary family CLASS and, if a second is genuinely used, the secondary: serif, grotesque, geometric-sans, condensed-sans, slab, script or display. A class, never a specific font name - the exact face is not recoverable from an image and guessing one produces false confidence.

Give `colour_roles` as a map of role name to a plain colour name, e.g. {"accent": "dark-red", "body": "near-black"}. Use the roles the design actually distinguishes, not a fixed list.

Give `text_roles` as a map of role name (headline, subhead, body, label, numeral, bullet...) to its setting: family_class, weight (light/regular/medium/bold/black), italic (true/false), case (as-written/upper/lower/title), colour_role naming one of the colour roles above, alignment (left/center/right), size_ratio relative to the body text (body is 1.0), tracking, and line_height.

Give `size_scale` as named ratios between roles, e.g. {"headline_to_body": 2.9}.

Give `capability_level`: L1 if every text element is flat type placed in clear space and could be reproduced by drawing text onto the image; L2 if it needs effects a renderer must apply (outlines, shadows, containers, or text following a shape); L3 if the type is integrated INTO the image - occluded by a subject, wrapped around an object, or treated as part of the artwork. Judge honestly: claiming L1 for integrated typography produces a flat, wrong recreation.

If the creative has a rule, divider or underline as part of its type system, include it in `rule_roles` or `divider_roles` with its colour_role and thickness relative to the body text size. These carry no words but are part of the system.""",
)
