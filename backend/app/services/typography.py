"""
Typography as a design system (ADR 0001 §10).

**Not a text-rendering concern.** The Rendering Engine has one hardcoded
style - bold Helvetica, white fill, black stroke, centred - which is correct
for a TikTok caption and wrong for everything else. Benchmark 4 needs a
red numeral over a short rule, a black serif headline, a red italic subhead
and red-bulleted lists. Rendering it in the caption style is what produced
output far below the source, and it is why typography is modelled here as a
system alongside colour palette and illustration style rather than as a
font argument.

**Family CLASS, never a specific face.** We cannot licence arbitrary fonts,
and exact matching is explicitly not a goal (ADR §10.2): benchmark 4 in any
competent serif beats benchmark 4 in bold Helvetica, and benchmarks 6 and 7
changed typeface family outright while keeping their hierarchy. Effort
belongs in hierarchy, spacing, emphasis and alignment.

**Capability levels** (ADR §10.1) keep one expressive title treatment from
blocking a renderer that already solves three benchmarks:

  L1  flat structured type - family, weight, case, size, alignment,
      leading, tracking, colour, bullets, rules. Covers cases 4, 6, 7.
  L2  stroke, shadow, gradient, containers, glow.
  L3  bevelled and expressive lettering, type integrated into artwork.
      May remain model-generated indefinitely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class FamilyClass(StrEnum):
    SERIF = "serif"
    GROTESQUE = "grotesque"
    GEOMETRIC_SANS = "geometric-sans"
    CONDENSED_SANS = "condensed-sans"
    SLAB = "slab"
    SCRIPT = "script"
    DISPLAY = "display"


class CapabilityLevel(StrEnum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


# Curated faces, mapped by family class. Every entry is a system face present
# on macOS; licensing is checked per face before anything is added here.
# `index` selects a face out of a .ttc collection.
_FACES: dict[FamilyClass, list[tuple[str, int]]] = {
    FamilyClass.SERIF: [
        ("/System/Library/Fonts/Supplemental/Georgia.ttf", 0),
        ("/System/Library/Fonts/Palatino.ttc", 0),
        ("/System/Library/Fonts/Times.ttc", 0),
    ],
    FamilyClass.GROTESQUE: [
        ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
        ("/System/Library/Fonts/Helvetica.ttc", 0),
    ],
    FamilyClass.GEOMETRIC_SANS: [
        ("/System/Library/Fonts/Avenir Next.ttc", 0),
        ("/System/Library/Fonts/Avenir.ttc", 0),
    ],
    FamilyClass.CONDENSED_SANS: [
        ("/System/Library/Fonts/Avenir Next Condensed.ttc", 0),
        ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
    ],
    FamilyClass.SLAB: [
        ("/System/Library/Fonts/Supplemental/Georgia.ttf", 0),
        ("/System/Library/Fonts/Palatino.ttc", 0),
    ],
    FamilyClass.SCRIPT: [
        ("/System/Library/Fonts/Supplemental/SnellRoundhand.ttc", 0),
        ("/System/Library/Fonts/Supplemental/Georgia.ttf", 0),
    ],
    FamilyClass.DISPLAY: [
        ("/System/Library/Fonts/Supplemental/Impact.ttf", 0),
        ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
    ],
}

# Bold and italic variants, where the system provides a real face rather than
# a synthetic slant. A real italic matters for benchmark 4, whose subhead is
# the emphasis in the hierarchy.
_VARIANTS: dict[tuple[FamilyClass, str], list[tuple[str, int]]] = {
    (FamilyClass.SERIF, "italic"): [
        ("/System/Library/Fonts/Supplemental/Georgia Italic.ttf", 0),
        ("/System/Library/Fonts/Times.ttc", 1),
    ],
    (FamilyClass.SERIF, "bold"): [
        ("/System/Library/Fonts/Supplemental/Georgia Bold.ttf", 0),
        ("/System/Library/Fonts/Times.ttc", 2),
    ],
    (FamilyClass.GROTESQUE, "bold"): [("/System/Library/Fonts/HelveticaNeue.ttc", 1)],
    (FamilyClass.GEOMETRIC_SANS, "bold"): [("/System/Library/Fonts/Avenir Next.ttc", 1)],
    (FamilyClass.CONDENSED_SANS, "bold"): [
        ("/System/Library/Fonts/Avenir Next Condensed.ttc", 1)
    ],
}

# Named colour roles resolved to RGB. The extractor reports role names rather
# than hex values because a role survives a palette change and a hex does not.
_COLOUR_ROLES: dict[str, tuple[int, int, int]] = {
    "near-black": (26, 26, 26),
    "dark-red": (155, 22, 34),
    "red": (200, 30, 40),
    "green": (22, 110, 55),
    "white": (255, 255, 255),
    "warm-white": (247, 245, 240),
    "grey": (110, 110, 110),
}


@dataclass(frozen=True)
class TextStyle:
    """How one block is set."""

    family: FamilyClass = FamilyClass.GROTESQUE
    weight: str = "regular"          # regular | bold
    italic: bool = False
    case: str = "as-written"         # as-written | upper | lower
    colour_role: str = "near-black"
    alignment: str = "left"          # left | centre | right
    size_ratio: float = 1.0          # relative to the system's base size
    tracking: float = 0.0            # em
    line_spacing: float = 1.18
    bullet: str | None = None        # marker glyph, if this block is a list
    # The marker often carries the accent colour while the text stays neutral -
    # benchmark 4 has red markers against near-black copy. One colour for the
    # whole block cannot express that, and rendering the marker in the text
    # colour visibly flattens the hierarchy.
    bullet_colour_role: str | None = None
    rule_below: bool = False
    stroke: bool = False             # L2
    shadow: bool = False             # L2


@dataclass(frozen=True)
class TypographySystem:
    """ADR 0001 §10. `styles` is keyed by role: headline, subhead, body …"""

    primary_family: FamilyClass = FamilyClass.GROTESQUE
    secondary_family: FamilyClass | None = None
    styles: dict[str, TextStyle] = field(default_factory=dict)
    colour_roles: dict[str, str] = field(default_factory=dict)
    capability_level: CapabilityLevel = CapabilityLevel.L1
    base_size_ratio: float = 0.045   # of image height

    def style_for(self, role: str) -> TextStyle:
        return self.styles.get(role, TextStyle(family=self.primary_family))


def resolve_colour(role: str) -> tuple[int, int, int]:
    """A role name to RGB, falling back to near-black rather than guessing."""
    return _COLOUR_ROLES.get(role, _COLOUR_ROLES["near-black"])


def resolve_face(family: FamilyClass, weight: str = "regular", italic: bool = False):
    """
    The nearest available face for a family class.

    Returns `(path, index)`. Never silently falls back to the caption face:
    if a family has no entry the request degrades within the same broad
    category, and only an entirely unknown family reaches the grotesque
    default. Callers can therefore trust that asking for a serif yields a
    serif.
    """
    if italic:
        for path, index in _VARIANTS.get((family, "italic"), []):
            if Path(path).exists():
                return path, index
    if weight == "bold":
        for path, index in _VARIANTS.get((family, "bold"), []):
            if Path(path).exists():
                return path, index
    for path, index in _FACES.get(family, []):
        if Path(path).exists():
            return path, index
    for path, index in _FACES[FamilyClass.GROTESQUE]:
        if Path(path).exists():
            return path, index
    raise RuntimeError("no usable system typeface found")


def available_families() -> dict[FamilyClass, bool]:
    """Which family classes actually resolve on this machine - for diagnostics."""
    result = {}
    for family in FamilyClass:
        result[family] = any(Path(path).exists() for path, _ in _FACES.get(family, []))
    return result
