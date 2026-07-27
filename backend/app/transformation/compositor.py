"""
Deterministic overlay compositor — the `composite_layer` rendering mechanism.

It rebuilds creator overlays from the Plan (exact text, reserved zone) onto a
base image. This is the app-side, deterministic step in the overlay-first flow;
it never asks the image model to draw the copy. Given a base scene it:
  - clears (blurs) the reserved zone (stand-in for regenerating that area),
  - draws a TikTok-style sticker (caption) or price block per the Plan.

No provider calls. Pure Pillow.
"""
from __future__ import annotations

import textwrap
from PIL import Image, ImageDraw, ImageFont, ImageFilter

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(size: int):
    for p in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _px(zone, w, h):
    x0, y0, x1, y1 = zone
    return int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)


def composite_overlays(base: Image.Image, items: list[dict]) -> Image.Image:
    """items: {text, zone[0..1], style: 'caption'|'price'}."""
    img = base.convert("RGB")
    W, H = img.size
    draw = ImageDraw.Draw(img)
    for it in items:
        text = (it.get("text") or "").strip()
        if not text:
            continue
        x0, y0, x1, y1 = _px(it["zone"], W, H)
        zone_w = max(x1 - x0, 40)
        # clear the reserved zone (stand-in for the regenerated area under the overlay)
        region = img.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(18))
        img.paste(region, (x0, y0))
        style = it.get("style", "caption")
        size = max(22, int(zone_w / 14))
        font = _font(size)
        # wrap to zone width
        approx_chars = max(8, int(zone_w / (size * 0.55)))
        lines = textwrap.wrap(text, width=approx_chars) or [text]
        line_h = int(size * 1.25)
        block_h = line_h * len(lines) + 24
        bx0, by0, bx1, by1 = x0, y0, x1, min(y0 + block_h, H)
        bg = (255, 255, 255) if style == "caption" else (20, 20, 24)
        fg = (0, 0, 0) if style == "caption" else (255, 255, 255)
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=18, fill=bg)
        cy = by0 + 12
        for ln in lines:
            tb = draw.textbbox((0, 0), ln, font=font)
            tw = tb[2] - tb[0]
            cx = bx0 + (bx1 - bx0 - tw) // 2
            # price: colour the discount/prices red like the source
            if style == "price" and ("%" in ln or "£" in ln):
                draw.text((cx, cy), ln, font=font, fill=(255, 90, 90))
            else:
                draw.text((cx, cy), ln, font=font, fill=fg)
            cy += line_h
    return img
