"""
Rendering Engine — Phase 10.8 of AI Creative Engine vNext (see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §15). Composites a
background image (an accepted `GeneratedImage` candidate) with the
`TextAsset`s Text Intelligence (app.services.text_intelligence)
produced into one final, upload-ready output.

**Real, live-verified feasibility spike, done before any of this was
built, per §15's own explicit "should get its own feasibility spike
before implementation" instruction**: composited synthetic marketing
text onto a real, busy generated marketing photo (not a plain
background) using Pillow. Result: clean, legible, professional-reading
text over a genuinely busy real photograph - confirmed directly, not
assumed. See this phase's report in MIGRATION_PLAN.md for the actual
spike images.

**Style redesign, real-world-diagnosed and user-directed** (see
MIGRATION_PLAN.md): the spike's original per-hierarchy design - a
solid, semi-transparent scrim rectangle behind `headline`/`subhead`
text, a solid rounded badge behind `cta` text - read as inconsistent
and visually heavy once seen on a real generated image. The user asked
for one consistent treatment instead, matching how the original
creator's own on-screen caption actually looked: centered, a real bold
typeface, a thin outline/stroke for legibility, and no background box
of any kind. Every TextAsset now renders exactly the same way,
regardless of `hierarchy` (which still only drives font *size* - see
app.services.text_intelligence's own `_HIERARCHY_STYLE`).

**Real-world-diagnosed correction to the spike's original font choice**
(see `_load_default_typeface`'s own comment, and MIGRATION_PLAN.md):
the spike used `PIL.ImageFont.load_default(size=...)` (Pillow's own
bundled font - no external files, no download, portable to any machine
running Pillow) and deliberately rejected macOS-only system-font paths
for that portability. A real generation later showed every "£" in a
rendered overlay as a blank tofu box - `load_default()`'s bundled font
turns out to have no glyph for £ (or presumably other non-ASCII
marketing characters) at all, and it has no real bold face either (the
style redesign above needs one). Since bundling a downloaded font file
isn't an option here, this now tries a short list of real system fonts
(their actual Bold face, not a synthetic one) confirmed to have full
Latin-1/currency coverage first, falling back to `load_default()` (so
it still degrades gracefully, not a crash, on a machine with none of
them) - a narrow, forced reversal of the spike's original choice, not a
silent one.

Deliberately NOT literal typographic reproduction (matching an
arbitrary original font/color exactly) - see
app.services.text_intelligence's own docstring for why that's out of
scope. White fill + black stroke is chosen specifically because it
guarantees legibility regardless of what's underneath, without needing
to know or match the background's own color at all - a real,
deliberate design choice given this codebase has no reliable way to
sample "the right" text color from an arbitrary generated photo.

Pure-ish: takes image bytes and a list of TextAsset dicts in, returns
composited image bytes out - no DB, no provider calls. The caller
(app.services.generate_with_retry, once a winner is accepted) owns
persisting the result as a `FinalOutput` row.
"""

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# hierarchy size_class -> point size, as a fraction of the image's
# shorter dimension - scales sensibly across different generated
# aspect ratios rather than a fixed pixel size.
_SIZE_CLASS_FRACTION = {"large": 0.06, "medium": 0.04, "small": 0.028}

_TEXT_FILL = (255, 255, 255, 255)
_STROKE_FILL = (0, 0, 0, 255)
_STROKE_WIDTH_FRACTION = 0.006  # "a little bit of stroke" - a thin legibility outline, not a heavy comic-style one
_PADDING_FRACTION = 0.02
# Centered, near-full-width - the user's own direction ("always centered,
# never left justified"), not confined to wherever the original slide's
# OCR happened to find this text's narrow bounding box.
_HORIZONTAL_MARGIN_FRACTION = 0.06

# Real-world-diagnosed fix (see MIGRATION_PLAN.md): a real generation's
# rendered overlay showed every "£" as a blank tofu box - confirmed via
# a direct render test that Pillow's bundled `ImageFont.load_default()`
# font has no glyph for £ (U+00A3) at all, not a wrapping/encoding bug -
# and it has no real bold face either, needed for the style redesign
# above. The feasibility spike that chose `load_default()` (see this
# module's own docstring) rejected macOS-only system-font paths for
# portability, but that decision predates hitting a real, confirmed
# missing-glyph case - and this codebase can't bundle a downloaded font
# file (no downloading files from untrusted sources). A short, ordered
# list of real system fonts confirmed via a direct render test to have
# full Latin-1/currency coverage, each paired with its actual Bold face
# index (confirmed via direct introspection - `ImageFont.truetype`'s
# `index` parameter selects a specific face out of a .ttc collection),
# tried in order, with `load_default()` kept as the final fallback so
# this still degrades gracefully (not a crash) on a machine with none
# of them - a deliberate, narrow reversal of the earlier decision, not
# a silent one.
_SYSTEM_FONT_CANDIDATES = [
    ("/System/Library/Fonts/Helvetica.ttc", 1),  # index 1 = Bold
    ("/System/Library/Fonts/HelveticaNeue.ttc", 1),  # index 1 = Bold
    ("/Library/Fonts/Arial Unicode.ttf", 0),  # single face, no bold - last resort
]


def _load_default_typeface(size: int) -> ImageFont.FreeTypeFont:
    for path, index in _SYSTEM_FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size, index=index)
    return ImageFont.load_default(size=size)


def _font_for(text_asset: dict, image_height: int) -> ImageFont.FreeTypeFont:
    fraction = _SIZE_CLASS_FRACTION.get(text_asset["styling"]["size_class"], _SIZE_CLASS_FRACTION["medium"])
    size = max(int(image_height * fraction), 14)
    return _load_default_typeface(size)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: float) -> str:
    """
    `ImageDraw.textlength` has no `stroke_width` parameter (unlike
    `text`/`textbbox`/`multiline_text`) - wrapping doesn't need to be
    stroke-exact, a stroke only adds a few pixels per side regardless
    of line length, well within this function's own word-boundary
    granularity.
    """
    words = text.split()
    if not words:
        return text
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return "\n".join(lines)


def _render_text_asset(draw: ImageDraw.ImageDraw, text_asset: dict, image_size: tuple[int, int], y: float) -> float:
    """
    Draws at the given (already collision-resolved) y, horizontally
    centered on the full image width - one unconditional style for
    every TextAsset (see this module's own docstring). Returns the
    pixel y of the drawn text's bottom edge, so the caller can stack
    the next asset below it.
    """
    width, height = image_size
    font = _font_for(text_asset, height)
    stroke_width = max(int(height * _STROKE_WIDTH_FRACTION), 1)
    margin = width * _HORIZONTAL_MARGIN_FRACTION
    max_width = width - 2 * margin

    wrapped = _wrap_text(draw, text_asset["wording"], font, max_width)
    bbox = draw.multiline_textbbox(
        (0, y), wrapped, font=font, align="center", stroke_width=stroke_width
    )
    block_width = bbox[2] - bbox[0]
    x = (width - block_width) / 2 - bbox[0]

    draw.multiline_text(
        (x, y),
        wrapped,
        font=font,
        fill=_TEXT_FILL,
        stroke_width=stroke_width,
        stroke_fill=_STROKE_FILL,
        align="center",
    )
    return bbox[3] + height * _PADDING_FRACTION


def _resolve_y(y: float, x_start: float, x_end: float, placed: list[tuple[float, float, float]], margin: float) -> float:
    """
    Pure collision-resolution step, split out from `render_final_output`
    so it's directly unit-testable without needing real font rendering
    or pixel inspection. `placed` is every already-drawn box's own
    `(x_start, x_end, bottom)` in pixels. Deliberately 2D, not just
    vertical - a real bug found live-verifying an earlier version of
    this fix: several boxes meant to sit side-by-side (different x,
    near-identical y) were all being cascaded downward by an x-blind
    version of this function, because it only ever compared y values.
    Only a box whose *x range actually overlaps* this one's can push it
    down; boxes that are genuinely side-by-side must be left alone.
    Now that every TextAsset renders centered across nearly the full
    image width (see `_render_text_asset`), every asset's x-range
    overlaps every other's by construction - this still matters, but
    only ever resolves to straightforward top-to-bottom stacking now,
    which is exactly correct for centered captions (they can never
    legitimately sit side-by-side).
    """
    required_y = y
    for placed_x_start, placed_x_end, placed_bottom in placed:
        if x_start < placed_x_end and placed_x_start < x_end and y < placed_bottom + margin:
            required_y = max(required_y, placed_bottom + margin)
    return required_y


def render_final_output(image_bytes: bytes, text_assets: list[dict]) -> bytes:
    """
    text_assets=[] (the no_text strategy, or a slide with nothing
    eligible to reuse) is a straight pass-through of the original
    bytes - §9's own explicit instruction, not a degenerate case to
    special-case away.
    """
    if not text_assets:
        return image_bytes

    image = Image.open(BytesIO(image_bytes)).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size

    # Real-world-diagnosed fix (see MIGRATION_PLAN.md): each TextAsset's
    # positioning.y comes from the ORIGINAL slide's own OCR layout, with
    # no awareness of any other asset's actually-rendered height once
    # wrapped at this module's own deterministic font size - a headline
    # that wraps to 2 lines can grow tall enough to visually collide
    # with whatever sits below it. Resolved with a top-to-bottom
    # stacking pass: process assets in vertical order, and push any box
    # whose original top would land inside an already-placed box's
    # claimed space down just past it, before drawing anything. Every
    # asset still renders (nothing dropped), just never on top of
    # another.
    ordered = sorted(text_assets, key=lambda asset: asset["positioning"]["y"])
    margin = height * _PADDING_FRACTION
    placed: list[tuple[float, float, float]] = []
    # Every asset now renders centered across the same near-full-width
    # band (see _render_text_asset) - x bounds for collision purposes
    # are that fixed band, not the original OCR position/width, which
    # no longer determines where the text is actually drawn.
    horizontal_margin = width * _HORIZONTAL_MARGIN_FRACTION
    x_start, x_end = horizontal_margin, width - horizontal_margin

    for text_asset in ordered:
        y = _resolve_y(text_asset["positioning"]["y"] * height, x_start, x_end, placed, margin)
        bottom = _render_text_asset(draw, text_asset, (width, height), y)
        placed.append((x_start, x_end, bottom))

    output = BytesIO()
    image.convert("RGB").save(output, format="PNG")
    return output.getvalue()
