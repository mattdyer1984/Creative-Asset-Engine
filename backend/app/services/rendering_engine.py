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
badge behind badge-style text (`cta`), both using
`PIL.ImageFont.load_default(size=...)` (Pillow's own bundled font - no
external font files, no download, portable to any machine running
Pillow, unlike the macOS-only system-font paths this spike also tried
and deliberately rejected for that reason). Result: clean, legible,
professional-reading text over a genuinely busy real photograph -
confirmed directly, not assumed. See this phase's report in
MIGRATION_PLAN.md for the actual spike images.

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


def _font_for(text_asset: dict, image_height: int) -> ImageFont.FreeTypeFont:
    fraction = _SIZE_CLASS_FRACTION.get(text_asset["styling"]["size_class"], _SIZE_CLASS_FRACTION["medium"])
    size = max(int(image_height * fraction), 14)
    return ImageFont.load_default(size=size)


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


def _render_scrim_text(draw: ImageDraw.ImageDraw, text_asset: dict, image_size: tuple[int, int]) -> None:
    width, height = image_size
    font = _font_for(text_asset, height)
    x = text_asset["positioning"]["x"] * width
    y = text_asset["positioning"]["y"] * height
    max_width = max(text_asset["positioning"]["width"] * width, font.size * 4)

    wrapped = _wrap_text(draw, text_asset["wording"], font, max_width)
    bbox = draw.multiline_textbbox((x, y), wrapped, font=font)
    padding = height * _PADDING_FRACTION
    draw.rectangle(
        [bbox[0] - padding, bbox[1] - padding, bbox[2] + padding, bbox[3] + padding], fill=_SCRIM_FILL
    )
    bold = text_asset["styling"]["weight"] == "bold"
    _draw_faux_bold(draw, (x, y), wrapped, font, _SCRIM_TEXT_COLOR, bold)


def _render_badge_text(draw: ImageDraw.ImageDraw, text_asset: dict, image_size: tuple[int, int]) -> None:
    width, height = image_size
    font = _font_for(text_asset, height)
    x = text_asset["positioning"]["x"] * width
    y = text_asset["positioning"]["y"] * height

    bbox = draw.textbbox((0, 0), text_asset["wording"], font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    padding = height * _PADDING_FRACTION * 1.5
    badge = [x, y, x + text_w + padding * 2, y + text_h + padding * 2]
    draw.rounded_rectangle(badge, radius=(badge[3] - badge[1]) / 2, fill=_BADGE_FILL)
    draw.text((x + padding - bbox[0], y + padding - bbox[1]), text_asset["wording"], font=font, fill=_BADGE_TEXT_COLOR)


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

    for text_asset in text_assets:
        if text_asset["styling"]["render_style"] == "badge":
            _render_badge_text(draw, text_asset, image.size)
        else:
            _render_scrim_text(draw, text_asset, image.size)

    output = BytesIO()
    image.convert("RGB").save(output, format="PNG")
    return output.getvalue()
