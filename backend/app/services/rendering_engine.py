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

import emoji
from PIL import Image, ImageDraw, ImageFont

# hierarchy size_class -> point size, as a fraction of the image's
# shorter dimension - scales sensibly across different generated
# aspect ratios rather than a fixed pixel size.
_SIZE_CLASS_FRACTION = {"large": 0.06, "medium": 0.04, "small": 0.028}

_TEXT_FILL = (255, 255, 255, 255)
_STROKE_FILL = (0, 0, 0, 255)
_STROKE_WIDTH_FRACTION = 0.006  # "a little bit of stroke" - a thin legibility outline, not a heavy comic-style one
_PADDING_FRACTION = 0.02

# Real-world-diagnosed fix (see MIGRATION_PLAN.md): once actually posted
# to TikTok, the app's own UI sits on top of the final image - a column
# of like/comment/share icons on the right, and a caption/username/
# comment-bar strip along the bottom. Text rendered near either edge (as
# a real generated caption was, right up against the right/bottom margin)
# would be covered. Centered, and now confined to the central two-thirds
# of the width and never the bottom 15-20% - the user's own explicit
# direction, not just "always centered, never left justified" (the
# original, narrower reasoning for centering at all).
_SAFE_HORIZONTAL_MARGIN_FRACTION = 1 / 6  # (1 - 2/3) / 2 each side - central two-thirds of the width
_BOTTOM_SAFE_ZONE_FRACTION = 0.20  # text must never extend into the bottom 20% of the image

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


# Real-world-diagnosed fix (see MIGRATION_PLAN.md): "Yeah, we need to be
# able to use emojis. They're quite important on TikTok" - the regular
# Helvetica typeface above has no emoji glyphs at all, so any emoji in a
# caption rendered as a blank tofu box. Apple Color Emoji renders real,
# full-color glyphs (confirmed via a direct render + pixel-color test),
# but it's a fixed-size bitmap ("sbix") font, not a scalable one -
# `ImageFont.truetype` only accepts a handful of exact "strike" sizes
# (confirmed via direct testing on this machine; anything else raises
# `OSError: invalid pixel size`), and Pillow's own `multiline_text`/
# `multiline_textbbox` only accept one font per call, so this text and
# emoji can never be a single Pillow call. `_layout_line` splits each
# wrapped line into (text, is_emoji) runs and measures/positions each
# with its own font; `_draw_emoji_run` renders the color glyph to a
# small RGBA cell at its native strike size and resizes it to match the
# surrounding text before compositing it in place. No downloading a
# font file - Apple Color Emoji already ships with macOS.
_EMOJI_FONT_PATH = "/System/Library/Fonts/Apple Color Emoji.ttc"
_EMOJI_FONT_STRIKE_SIZES = [20, 32, 40, 48, 64, 96, 160]
_LINE_SPACING = 4  # Pillow's own multiline_text/multiline_textbbox default - kept identical so this module's own custom line layout (needed for mixed-font rendering) doesn't visibly change plain-text line spacing.


def _nearest_emoji_strike_size(target_size: int) -> int:
    return min(_EMOJI_FONT_STRIKE_SIZES, key=lambda size: abs(size - target_size))


def _load_emoji_font(target_size: int) -> ImageFont.FreeTypeFont | None:
    if not Path(_EMOJI_FONT_PATH).exists():
        return None
    return ImageFont.truetype(_EMOJI_FONT_PATH, size=_nearest_emoji_strike_size(target_size))


def _emoji_font_and_scale(target_size: int) -> tuple[ImageFont.FreeTypeFont | None, float]:
    """
    `target_size` is the surrounding text font's own point size - emoji
    should read at roughly the same visual size as the text beside
    them. `None` (no Apple Color Emoji font on this machine) degrades
    gracefully to a tofu box via the regular text font, matching this
    app's pre-emoji behavior - not a crash.
    """
    emoji_font = _load_emoji_font(target_size)
    if emoji_font is None:
        return None, 1.0
    return emoji_font, target_size / emoji_font.size


def _split_into_runs(line: str) -> list[tuple[str, bool]]:
    """
    Splits one already-wrapped line into (text, is_emoji) runs, using
    the `emoji` package's own grapheme-cluster-aware detection
    (`emoji.emoji_list`) rather than iterating codepoints - a single
    visible emoji can span several codepoints (skin-tone modifiers, ZWJ
    sequences) that must stay together as one drawable unit.
    """
    matches = emoji.emoji_list(line)
    if not matches:
        return [(line, False)]
    runs: list[tuple[str, bool]] = []
    cursor = 0
    for match in matches:
        start, end = match["match_start"], match["match_end"]
        if start > cursor:
            runs.append((line[cursor:start], False))
        runs.append((line[start:end], True))
        cursor = end
    if cursor < len(line):
        runs.append((line[cursor:], False))
    return runs


def _layout_line(
    draw: ImageDraw.ImageDraw,
    line: str,
    text_font: ImageFont.FreeTypeFont,
    emoji_font: ImageFont.FreeTypeFont | None,
    emoji_scale: float,
) -> tuple[list[tuple[str, bool, float]], float]:
    """
    The shared measure/draw step behind both `_measure_text_asset`
    (needs the resulting line width before committing to a position)
    and `_draw_text_asset` (draws from the exact same layout, so what's
    measured is what's drawn) - each run's own width, plus the line's
    total width for centering.
    """
    runs = _split_into_runs(line)
    measured: list[tuple[str, bool, float]] = []
    total_width = 0.0
    for text, is_emoji in runs:
        if is_emoji and emoji_font is not None:
            width = draw.textlength(text, font=emoji_font) * emoji_scale
        else:
            width = draw.textlength(text, font=text_font)
        measured.append((text, is_emoji, width))
        total_width += width
    return measured, total_width


def _draw_emoji_run(
    image: Image.Image, emoji_text: str, emoji_font: ImageFont.FreeTypeFont, target_size: int, x: float, top: float
) -> None:
    """
    Renders one real color emoji glyph to its own small RGBA cell at
    the font's native strike size (the only sizes `ImageFont.truetype`
    accepts for Apple Color Emoji - see `_load_emoji_font`), resizes it
    to match the surrounding text, and pastes it onto `image` using its
    own alpha channel as the mask - deliberately no stroke outline
    (unlike the regular text runs): the glyph is already a distinct,
    high-contrast pictorial image, and Pillow's stroke isn't meaningful
    combined with `embedded_color`.
    """
    native_size = emoji_font.size
    cell = Image.new("RGBA", (native_size, native_size), (0, 0, 0, 0))
    ImageDraw.Draw(cell).text((0, 0), emoji_text, font=emoji_font, embedded_color=True)
    if target_size != native_size:
        cell = cell.resize((max(target_size, 1), max(target_size, 1)), Image.LANCZOS)
    image.paste(cell, (int(x), int(top)), cell)


def _base_font_size_for(text_asset: dict, image_height: int) -> int:
    fraction = _SIZE_CLASS_FRACTION.get(text_asset["styling"]["size_class"], _SIZE_CLASS_FRACTION["medium"])
    return max(int(image_height * fraction), 14)


def _greedy_wrap_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: float,
    emoji_font: ImageFont.FreeTypeFont | None = None,
    emoji_scale: float = 1.0,
) -> list[str]:
    """
    Pure word-wrap at a fixed font size - the mechanical wrapping step,
    with no opinion on font size or orphan words (see
    `_choose_wrapped_lines`, which calls this at several sizes to pick
    the best result). Measures candidates via `_layout_line` (not a
    plain `draw.textlength`) so a caption containing emoji wraps
    against their *actual* drawn width - real bug caught live: a plain
    `draw.textlength` on an emoji character measures the regular text
    font's own (much narrower) tofu-box advance, which let lines that
    only fit once real emoji width is accounted for pack extra emoji
    on, overflowing `max_width` and, downstream, the safe zone. Stroke
    isn't included here - it only adds a few pixels per side regardless
    of line length, well within word-boundary granularity.
    """
    words = text.split()
    if not words:
        return [text]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        _, width = _layout_line(draw, candidate, font, emoji_font, emoji_scale)
        if width <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


# Real-world-diagnosed fix (Generate All follow-up, see MIGRATION_PLAN.md):
# a real caption wrapped onto 3 lines at the size_class's fixed font
# size, with the final line holding a single orphaned word - the user's
# own explicit direction is to fit text onto two lines wherever
# possible, and never start a new line for just one word.
_MIN_FONT_SCALE = 0.6  # never shrink a caption below 60% of its size-class's target size
_FONT_SCALE_STEP = 0.05


def _has_orphaned_last_word(lines: list[str]) -> bool:
    return len(lines) > 1 and len(lines[-1].split()) == 1


def _choose_wrapped_lines(
    draw: ImageDraw.ImageDraw, text: str, base_size: int, max_width: float
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """
    Tries the size_class's own target size first, then shrinks in small
    steps down to `_MIN_FONT_SCALE`, always preferring the largest size
    that wraps the text onto 2 lines or fewer with no single-word last
    line - a size that reads a little smaller but wraps cleanly beats
    the "ideal" size wrapping badly. If no size in that range achieves
    both, falls back to whichever size produced the fewest lines, then
    (tie-break) whichever still avoids an orphaned last word, then
    (tie-break) the largest font - not every caption can be rescued
    (e.g. one genuinely long final word), so this is a best-effort
    preference, not a guarantee.
    """
    words = text.split()
    if len(words) <= 1:
        # A single word can never be "orphaned" - nothing to rebalance,
        # and shrinking it would only make it needlessly smaller.
        font = _load_default_typeface(base_size)
        emoji_font, emoji_scale = _emoji_font_and_scale(font.size)
        return font, _greedy_wrap_lines(draw, text, font, max_width, emoji_font, emoji_scale)

    best: tuple[int, bool, ImageFont.FreeTypeFont, list[str]] | None = None
    scale = 1.0
    while scale >= _MIN_FONT_SCALE - 1e-9:
        size = max(int(base_size * scale), 10)
        font = _load_default_typeface(size)
        emoji_font, emoji_scale = _emoji_font_and_scale(font.size)
        lines = _greedy_wrap_lines(draw, text, font, max_width, emoji_font, emoji_scale)
        orphaned = _has_orphaned_last_word(lines)
        if len(lines) <= 2 and not orphaned:
            return font, lines
        if best is None or (len(lines), orphaned) < (best[0], best[1]):
            best = (len(lines), orphaned, font, lines)
        scale -= _FONT_SCALE_STEP
    assert best is not None
    return best[2], best[3]


def _measure_text_asset(
    draw: ImageDraw.ImageDraw, text_asset: dict, image_size: tuple[int, int], max_width: float
) -> tuple[ImageFont.FreeTypeFont, list[str], int, tuple[float, float, float, float]]:
    """
    The wrapping/sizing half of what used to be `_render_text_asset` -
    split out so `render_final_output` can know a caption's real
    rendered height (and therefore whether it fits above the bottom
    safe zone, see that function's own docstring) before committing to
    a y position, not just after drawing it. `bbox_at_zero` mirrors
    what Pillow's own `multiline_textbbox` used to return at a y anchor
    of 0 (top/bottom offsets relative to wherever this text is
    eventually drawn) - computed by hand now via `_layout_line` rather
    than Pillow's own multi-line layout, since mixed text/emoji
    rendering (see this module's own docstring above `_split_into_runs`)
    needs its own per-line, per-run measurement Pillow can't do in one
    call.
    """
    width, height = image_size
    base_size = _base_font_size_for(text_asset, height)
    stroke_width = max(int(height * _STROKE_WIDTH_FRACTION), 1)
    font, lines = _choose_wrapped_lines(draw, text_asset["wording"], base_size, max_width)
    ascent, descent = font.getmetrics()
    line_height = ascent + descent
    block_height = len(lines) * line_height + max(len(lines) - 1, 0) * _LINE_SPACING
    emoji_font, emoji_scale = _emoji_font_and_scale(font.size)
    max_line_width = max((_layout_line(draw, line, font, emoji_font, emoji_scale)[1] for line in lines), default=0.0)
    bbox_at_zero = (
        -max_line_width / 2 - stroke_width,
        -stroke_width,
        max_line_width / 2 + stroke_width,
        block_height + stroke_width,
    )
    return font, lines, stroke_width, bbox_at_zero


def _draw_text_asset(
    draw: ImageDraw.ImageDraw,
    image: Image.Image,
    font: ImageFont.FreeTypeFont,
    lines: list[str],
    stroke_width: int,
    image_size: tuple[int, int],
    y: float,
) -> float:
    """
    Draws at the given (already collision- and safe-zone-resolved) y,
    horizontally centered on the full image width - one unconditional
    style for every TextAsset (see this module's own docstring). Draws
    line by line, run by run (rather than one `multiline_text` call)
    so a caption can mix the regular text font with real color emoji
    glyphs (see `_split_into_runs`/`_draw_emoji_run`) - centering each
    line independently against the full image width produces the same
    visual result as the old "center the block, then center each line
    within it" two-step approach. Returns the pixel y of the drawn
    text's bottom edge, so the caller can stack the next asset below it.
    """
    width, height = image_size
    ascent, descent = font.getmetrics()
    line_height = ascent + descent
    emoji_font, emoji_scale = _emoji_font_and_scale(font.size)

    line_top = y
    for line in lines:
        runs, line_width = _layout_line(draw, line, font, emoji_font, emoji_scale)
        # `draw.textlength` (what _layout_line measures text runs with)
        # doesn't include stroke - Pillow's own stroke bleeds stroke_width
        # pixels beyond the glyph's normal advance on every side. Padding
        # the centered width by stroke_width on each side (and shifting
        # the start position in by the same amount) keeps the *visible*
        # stroked line centered, matching what the old multiline_textbbox
        # -based bbox (which included stroke automatically) used to
        # guarantee - without this, a full-width caption's stroke could
        # bleed just past the safe-zone margin (real regression caught by
        # test_caption_mixing_text_and_emoji_still_stays_within_the_safe_zone).
        visual_width = line_width + 2 * stroke_width
        x = (width - visual_width) / 2 + stroke_width
        for text, is_emoji, run_width in runs:
            if is_emoji and emoji_font is not None:
                target_size = max(int(emoji_font.size * emoji_scale), 1)
                _draw_emoji_run(image, text, emoji_font, target_size, x, line_top + ascent - target_size)
            elif text:
                draw.text(
                    (x, line_top),
                    text,
                    font=font,
                    fill=_TEXT_FILL,
                    stroke_width=stroke_width,
                    stroke_fill=_STROKE_FILL,
                )
            x += run_width
        line_top += line_height + _LINE_SPACING

    block_height = len(lines) * line_height + max(len(lines) - 1, 0) * _LINE_SPACING
    return y + block_height + stroke_width + height * _PADDING_FRACTION


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
    Now that every TextAsset renders centered across the same
    central-two-thirds band (see `_SAFE_HORIZONTAL_MARGIN_FRACTION`),
    every asset's x-range
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
    # Every asset now renders centered across the same central-two-thirds
    # band (see _SAFE_HORIZONTAL_MARGIN_FRACTION) - x bounds for
    # collision purposes are that fixed band, not the original OCR
    # position/width, which no longer determines where the text is
    # actually drawn.
    horizontal_margin = width * _SAFE_HORIZONTAL_MARGIN_FRACTION
    x_start, x_end = horizontal_margin, width - horizontal_margin
    max_width = x_end - x_start
    # Real-world-diagnosed fix (see MIGRATION_PLAN.md): a real caption
    # was placed low enough that TikTok's own UI (posted afterward)
    # would cover it - text must never extend into the bottom
    # _BOTTOM_SAFE_ZONE_FRACTION of the image, regardless of where the
    # original slide's own OCR happened to find it.
    safe_bottom = height * (1 - _BOTTOM_SAFE_ZONE_FRACTION)

    for text_asset in ordered:
        font, lines, stroke_width, bbox_at_zero = _measure_text_asset(draw, text_asset, (width, height), max_width)
        max_y = safe_bottom - bbox_at_zero[3]
        desired_y = min(max(text_asset["positioning"]["y"] * height, 0), max_y)
        y = _resolve_y(desired_y, x_start, x_end, placed, margin)
        # Re-clamped after collision-stacking: keeping every asset out of
        # the bottom safe zone takes priority over its exact stacked
        # position in the rare case a lower asset would otherwise be
        # pushed past it.
        y = max(min(y, max_y), 0)
        bottom = _draw_text_asset(draw, image, font, lines, stroke_width, (width, height), y)
        placed.append((x_start, x_end, bottom))

    output = BytesIO()
    image.convert("RGB").save(output, format="PNG")
    return output.getvalue()
