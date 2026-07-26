"""
Style-aware typographic rendering (ADR 0001 WP-1.4, capability level L1).

**This is the programme gate.** If flat structured typography cannot reach
benchmark quality on case 4, Phase 1's premise is wrong.

The existing `rendering_engine` draws every block the same way: bold
Helvetica, white fill, black stroke, centred. That is correct for a TikTok
caption and wrong for designed editorial typography. Case 4 needs a red
numeral above a short rule, a black serif headline, a red italic subhead,
and a red-bulleted list, all left-aligned in the left third. Drawn in the
caption style it looks nothing like the source, which is the single largest
visible quality gap.

This renderer is deliberately narrow. It draws a `TypographySystem` into
declared zones and does nothing else - no captions, no compositing policy,
no decisions about what text belongs in the image. Those live elsewhere.
L2 effects (stroke, shadow) are honoured where a style asks for them;
L3 expressive lettering is out of scope by design.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from app.services.typography import TextStyle, TypographySystem, resolve_colour, resolve_face


@dataclass(frozen=True)
class TextBlock:
    """One block to set, with the role that selects its style."""

    text: str
    role: str                      # headline | subhead | body | numeral | label …
    # Normalised [x_min, y_min, x_max, y_max]. The block is laid out inside
    # this box; height is advisory, width is binding for wrapping.
    bounds: tuple[float, float, float, float]


#: Marker glyphs OCR commonly includes in the block text itself.
_LEADING_MARKERS = "•‣▪◦·-–—*"


def _strip_leading_marker(text: str, style: TextStyle) -> str:
    """
    Drop a marker the OCR text already carries when the style supplies one.

    Live OCR returns "• You struggle to straighten up" - the glyph is part of
    the recognised text. Adding the style's marker on top rendered "• •",
    which the end-to-end run showed plainly. The style owns the marker, so
    the text must not also carry it.
    """
    if not style.bullet:
        return text
    stripped = text.lstrip()
    while stripped and stripped[0] in _LEADING_MARKERS:
        stripped = stripped[1:].lstrip()
    return stripped or text


def _apply_case(text: str, style: TextStyle) -> str:
    if style.case == "upper":
        return text.upper()
    if style.case == "lower":
        return text.lower()
    return text


def _font(style: TextStyle, size: int) -> ImageFont.FreeTypeFont:
    path, index = resolve_face(style.family, style.weight, style.italic)
    return ImageFont.truetype(path, size=size, index=index)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """
    Greedy wrap. Long words are left to overflow rather than hyphenated -
    breaking a brand name mid-word would be worse than a slightly wide line.
    """
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_tracked(
    draw: ImageDraw.ImageDraw, xy, text: str, font, fill, tracking_px: float
) -> float:
    """Draw with letter spacing, returning the advance width."""
    if not tracking_px:
        draw.text(xy, text, font=font, fill=fill)
        return draw.textlength(text, font=font)
    x, y = xy
    for character in text:
        draw.text((x, y), character, font=font, fill=fill)
        x += draw.textlength(character, font=font) + tracking_px
    return x - xy[0]


def render_typography(
    image: Image.Image, blocks: list[TextBlock], system: TypographySystem
) -> Image.Image:
    """
    Draw `blocks` onto a copy of `image` using `system`.

    Each block is laid out from the top of its zone. Alignment, colour role,
    case, tracking, leading, bullets and rules all come from the style for
    that block's role - which is the whole point: the renderer holds no
    opinion of its own about how text should look.
    """
    canvas = image.convert("RGB").copy()
    draw = ImageDraw.Draw(canvas)
    width, height = canvas.size
    base_size = max(int(height * system.base_size_ratio), 8)

    for block in blocks:
        style = system.style_for(block.role)
        text = _apply_case(_strip_leading_marker(block.text, style), style)
        if not text.strip():
            continue

        x_min, y_min, x_max, _ = block.bounds
        left, top = int(x_min * width), int(y_min * height)
        box_width = max(int((x_max - x_min) * width), 1)

        size = max(int(base_size * style.size_ratio), 8)
        font = _font(style, size)
        tracking_px = style.tracking * size

        bullet_indent = 0
        if style.bullet:
            bullet_indent = int(draw.textlength(f"{style.bullet} ", font=font))

        lines = _wrap(draw, text, font, box_width - bullet_indent)
        fill = resolve_colour(style.colour_role)
        line_height = int(size * style.line_spacing)

        y = top
        for index, line in enumerate(lines):
            line_width = draw.textlength(line, font=font) + tracking_px * max(len(line) - 1, 0)
            if style.alignment == "centre":
                x = left + (box_width - line_width) / 2
            elif style.alignment == "right":
                x = left + box_width - line_width
            else:
                x = left + (bullet_indent if index else 0)

            if style.bullet and index == 0:
                marker_fill = (
                    resolve_colour(style.bullet_colour_role)
                    if style.bullet_colour_role
                    else fill
                )
                _draw_tracked(draw, (left, y), style.bullet, font, marker_fill, 0)
                x = left + bullet_indent

            if style.shadow:  # L2
                _draw_tracked(
                    draw, (x + size * 0.04, y + size * 0.04), line, font, (0, 0, 0), tracking_px
                )
            if style.stroke:  # L2
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    offset = max(int(size * 0.03), 1)
                    _draw_tracked(
                        draw, (x + dx * offset, y + dy * offset), line, font, (0, 0, 0), tracking_px
                    )

            _draw_tracked(draw, (x, y), line, font, fill, tracking_px)
            y += line_height

        if style.rule_below:
            rule_y = y + int(size * 0.10)
            rule_width = int(box_width * 0.42)
            thickness = max(int(size * 0.045), 2)
            draw.rectangle(
                [left, rule_y, left + rule_width, rule_y + thickness], fill=fill
            )

    return canvas
