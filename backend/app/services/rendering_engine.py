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
background) using Pillow - a solid, semi-transparent scrim rectangle
behind scrim-style text (`headline`/`subhead`), and a solid rounded
badge behind badge-style text (`cta`). Result: clean, legible,
professional-reading text over a genuinely busy real photograph -
confirmed directly, not assumed. See this phase's report in
MIGRATION_PLAN.md for the actual spike images.

**Real-world-diagnosed correction to the spike's original font choice**
(see `_load_default_typeface`'s own comment, and MIGRATION_PLAN.md):
the spike used `PIL.ImageFont.load_default(size=...)` (Pillow's own
bundled font - no external files, no download, portable to any machine
running Pillow) and deliberately rejected macOS-only system-font paths
for that portability. A real generation later showed every "£" in a
rendered overlay as a blank tofu box - `load_default()`'s bundled font
turns out to have no glyph for £ (or presumably other non-ASCII
marketing characters) at all. Since bundling a downloaded font file
isn't an option here, this now tries a short list of real system fonts
confirmed to have full Latin-1/currency coverage first, falling back to
`load_default()` (so it still degrades gracefully, not a crash, on a
machine with none of them) - a narrow, forced reversal of the spike's
original choice, not a silent one.

Deliberately NOT literal typographic reproduction (matching an
arbitrary original font/color exactly) - see
app.services.text_intelligence's own docstring for why that's out of
scope. The scrim/badge techniques used here are chosen specifically
because they guarantee legibility regardless of what's underneath,
without needing to know or match the background's own color at all -
a real, deliberate design choice given this codebase has no reliable
way to sample "the right" text color from an arbitrary generated
photo.

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

_SCRIM_FILL = (10, 10, 10, 150)
_SCRIM_TEXT_COLOR = (255, 255, 255, 255)
_BADGE_FILL = (230, 180, 90, 255)
_BADGE_TEXT_COLOR = (20, 20, 20, 255)
_PADDING_FRACTION = 0.02

# Real-world-diagnosed fix (see MIGRATION_PLAN.md): a real generation's
# rendered overlay showed every "£" as a blank tofu box - confirmed via
# a direct render test that Pillow's bundled `ImageFont.load_default()`
# font has no glyph for £ (U+00A3) at all, not a wrapping/encoding bug.
# The feasibility spike that chose `load_default()` (see this module's
# own docstring) rejected macOS-only system-font paths for portability,
# but that decision predates hitting a real, confirmed missing-glyph
# case - and this codebase can't bundle a downloaded font file (no
# downloading files from untrusted sources). A short, ordered list of
# real system fonts confirmed via a direct render test to have full
# Latin-1/currency coverage, tried in order, with `load_default()` kept
# as the final fallback so this still degrades gracefully (not a crash)
# on a machine with none of them - a deliberate, narrow reversal of the
# earlier decision, not a silent one.
_SYSTEM_FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]


def _load_default_typeface(size: int) -> ImageFont.FreeTypeFont:
    for candidate in _SYSTEM_FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default(size=size)


def _font_for(text_asset: dict, image_height: int) -> ImageFont.FreeTypeFont:
    fraction = _SIZE_CLASS_FRACTION.get(text_asset["styling"]["size_class"], _SIZE_CLASS_FRACTION["medium"])
    size = max(int(image_height * fraction), 14)
    return _load_default_typeface(size)


def _draw_faux_bold(draw: ImageDraw.ImageDraw, xy: tuple, text: str, font, fill, bold: bool) -> None:
    """
    Pillow's bundled default font has a single weight - faux-bold via a
    tiny double-draw offset (a well-known technique for single-weight
    fonts) rather than claiming a real bold variant that doesn't exist.
    """
    if bold:
        offset = max(font.size // 40, 1)
        draw.text((xy[0] + offset, xy[1]), text, font=font, fill=fill)
    draw.text(xy, text, font=font, fill=fill)


def _render_scrim_text(draw: ImageDraw.ImageDraw, text_asset: dict, image_size: tuple[int, int], y: float) -> float:
    """Draws at the given (already collision-resolved) y; returns the pixel y of the drawn box's bottom edge."""
    width, height = image_size
    font = _font_for(text_asset, height)
    x = text_asset["positioning"]["x"] * width
    max_width = max(text_asset["positioning"]["width"] * width, font.size * 4)

    wrapped = _wrap_text(draw, text_asset["wording"], font, max_width)
    bbox = draw.multiline_textbbox((x, y), wrapped, font=font)
    padding = height * _PADDING_FRACTION
    draw.rectangle(
        [bbox[0] - padding, bbox[1] - padding, bbox[2] + padding, bbox[3] + padding], fill=_SCRIM_FILL
    )
    bold = text_asset["styling"]["weight"] == "bold"
    _draw_faux_bold(draw, (x, y), wrapped, font, _SCRIM_TEXT_COLOR, bold)
    return bbox[3] + padding


def _render_badge_text(draw: ImageDraw.ImageDraw, text_asset: dict, image_size: tuple[int, int], y: float) -> float:
    """Draws at the given (already collision-resolved) y; returns the pixel y of the drawn box's bottom edge."""
    width, height = image_size
    font = _font_for(text_asset, height)
    x = text_asset["positioning"]["x"] * width

    bbox = draw.textbbox((0, 0), text_asset["wording"], font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    padding = height * _PADDING_FRACTION * 1.5
    badge = [x, y, x + text_w + padding * 2, y + text_h + padding * 2]
    draw.rounded_rectangle(badge, radius=(badge[3] - badge[1]) / 2, fill=_BADGE_FILL)
    draw.text((x + padding - bbox[0], y + padding - bbox[1]), text_asset["wording"], font=font, fill=_BADGE_TEXT_COLOR)
    return badge[3]


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: float) -> str:
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


def _resolve_y(y: float, x_start: float, x_end: float, placed: list[tuple[float, float, float]], margin: float) -> float:
    """
    Pure collision-resolution step, split out from `render_final_output`
    so it's directly unit-testable without needing real font rendering
    or pixel inspection. `placed` is every already-drawn box's own
    `(x_start, x_end, bottom)` in pixels. Deliberately 2D, not just
    vertical - a real bug found live-verifying this fix: four shelf
    price tags meant to sit side-by-side (different x, near-identical
    y) were all being cascaded downward by an earlier, x-blind version
    of this function, because it only ever compared y values. Only a
    box whose *x range actually overlaps* this one's can push it down;
    boxes that are genuinely side-by-side must be left alone.
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
    # claimed space - one whose x-range actually overlaps this one's -
    # down just past it, before drawing anything. Every asset still
    # renders (nothing dropped), just never on top of another.
    ordered = sorted(text_assets, key=lambda asset: asset["positioning"]["y"])
    margin = height * _PADDING_FRACTION
    placed: list[tuple[float, float, float]] = []

    for text_asset in ordered:
        x_start = text_asset["positioning"]["x"] * width
        x_end = x_start + text_asset["positioning"]["width"] * width
        y = _resolve_y(text_asset["positioning"]["y"] * height, x_start, x_end, placed, margin)

        if text_asset["styling"]["render_style"] == "badge":
            bottom = _render_badge_text(draw, text_asset, (width, height), y)
        else:
            bottom = _render_scrim_text(draw, text_asset, (width, height), y)
        placed.append((x_start, x_end, bottom))

    output = BytesIO()
    image.convert("RGB").save(output, format="PNG")
    return output.getvalue()
