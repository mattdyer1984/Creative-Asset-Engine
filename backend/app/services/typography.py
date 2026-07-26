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


class FontResolutionError(RuntimeError):
    """Base for font problems. Never swallowed into a silent substitution."""


class UnmappedFontToken(FontResolutionError):
    """No logical token covers this style - a gap in the token table."""


class UnavailableFontToken(FontResolutionError):
    """The token is mapped but no face for it exists on this host."""



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


# --- Logical font tokens -------------------------------------------------
#
# The renderer asks for a TOKEN, never for a host font by name. "Georgia"
# existing is an accident of this machine; `serif_editorial_regular` is a
# design intent that survives a move to Linux or a container. The mapping
# below is the local development binding and is expected to be replaced by
# packaged, licence-cleared assets - see FONT_PORTABILITY.md.
#
# Every dependency here is documented, and an unavailable token raises or
# warns rather than degrading silently. Silently falling back to the caption
# face is precisely the defect this whole subsystem replaces.

FontToken = str

#: token -> ordered candidate (path, ttc index) pairs, most preferred first.
FONT_TOKENS: dict[FontToken, list[tuple[str, int]]] = {
    "serif_editorial_regular": [
        ("/System/Library/Fonts/Supplemental/Georgia.ttf", 0),
        ("/System/Library/Fonts/Palatino.ttc", 0),
        ("/System/Library/Fonts/Times.ttc", 0),
    ],
    "serif_editorial_italic": [
        ("/System/Library/Fonts/Supplemental/Georgia Italic.ttf", 0),
        ("/System/Library/Fonts/Times.ttc", 1),
    ],
    "serif_editorial_bold": [
        ("/System/Library/Fonts/Supplemental/Georgia Bold.ttf", 0),
        ("/System/Library/Fonts/Times.ttc", 2),
    ],
    "grotesque_regular": [
        ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
        ("/System/Library/Fonts/Helvetica.ttc", 0),
    ],
    "grotesque_bold": [("/System/Library/Fonts/HelveticaNeue.ttc", 1)],
    "geometric_sans_regular": [
        ("/System/Library/Fonts/Avenir Next.ttc", 0),
        ("/System/Library/Fonts/Avenir.ttc", 0),
    ],
    "geometric_sans_bold": [("/System/Library/Fonts/Avenir Next.ttc", 1)],
    "condensed_display_regular": [("/System/Library/Fonts/Avenir Next Condensed.ttc", 0)],
    "condensed_display_bold": [("/System/Library/Fonts/Avenir Next Condensed.ttc", 1)],
    "slab_regular": [
        ("/System/Library/Fonts/Supplemental/Georgia.ttf", 0),
        ("/System/Library/Fonts/Palatino.ttc", 0),
    ],
    "script_regular": [("/System/Library/Fonts/Supplemental/SnellRoundhand.ttc", 0)],
    "display_regular": [("/System/Library/Fonts/Supplemental/Impact.ttf", 0)],
}

#: (family class, weight, italic) -> token. The renderer never sees a path.
_TOKEN_FOR: dict[tuple[str, str, bool], FontToken] = {
    ("serif", "regular", False): "serif_editorial_regular",
    ("serif", "regular", True): "serif_editorial_italic",
    ("serif", "bold", False): "serif_editorial_bold",
    ("serif", "bold", True): "serif_editorial_italic",
    ("slab", "regular", False): "slab_regular",
    ("slab", "bold", False): "slab_regular",
    ("grotesque", "regular", False): "grotesque_regular",
    ("grotesque", "bold", False): "grotesque_bold",
    ("geometric-sans", "regular", False): "geometric_sans_regular",
    ("geometric-sans", "bold", False): "geometric_sans_bold",
    ("condensed-sans", "regular", False): "condensed_display_regular",
    ("condensed-sans", "bold", False): "condensed_display_bold",
    ("script", "regular", False): "script_regular",
    ("display", "regular", False): "display_regular",
    ("display", "bold", False): "display_regular",
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


def is_known_colour(name: str) -> bool:
    return name in _COLOUR_ROLES


def resolve_colour(name: str) -> tuple[int, int, int]:
    """
    A NAMED COLOUR to RGB. Not a role name - see `to_renderer_system`, which
    dereferences the project's `colour_roles` map first.

    The distinction is not pedantic. This function was being handed role
    names like `accent`, which it did not recognise and silently rendered
    near-black. Benchmark 4's dark-red accent came out black, and no test
    caught it because the schema-level assertions only checked that the
    accent role DIFFERED from the body role - which it did, right up until
    both were drawn in the same colour.

    Still falls back rather than raising, because a wrong colour is
    recoverable and a crashed render is not - but callers should check
    `is_known_colour` first and warn, so the fallback is never silent.
    """
    return _COLOUR_ROLES.get(name, _COLOUR_ROLES["near-black"])


def token_for(family: FamilyClass, weight: str = "regular", italic: bool = False) -> FontToken:
    """
    The logical token for a style. Degrades within the family (a bold serif
    with no bold face falls back to the regular serif), never across it.
    """
    for candidate in (
        (str(family), weight, italic),
        (str(family), weight, False),
        (str(family), "regular", italic),
        (str(family), "regular", False),
    ):
        token = _TOKEN_FOR.get(candidate)
        if token:
            return token
    raise UnmappedFontToken(
        f"no logical font token maps {family}/{weight}{'/italic' if italic else ''}"
    )


def resolve_token(token: FontToken) -> tuple[str, int]:
    """
    A token to a concrete face on this machine.

    Raises rather than substituting. There is no fallback to the caption
    face: a serif silently rendered in bold Helvetica is the exact defect
    this subsystem exists to remove, and a loud failure is recoverable
    where a silent one is not.
    """
    for path, index in FONT_TOKENS.get(token, []):
        if Path(path).exists():
            return path, index
    raise UnavailableFontToken(
        f"font token {token!r} has no available face on this host. "
        f"Candidates: {[p for p, _ in FONT_TOKENS.get(token, [])]}. "
        "See FONT_PORTABILITY.md - packaged assets are required for deployment."
    )


def resolve_face(family: FamilyClass, weight: str = "regular", italic: bool = False):
    """Convenience: style attributes straight through to a concrete face."""
    return resolve_token(token_for(family, weight, italic))


def font_availability() -> dict[FontToken, bool]:
    """Which tokens resolve on this host - for diagnostics and startup checks."""
    return {
        token: any(Path(path).exists() for path, _ in candidates)
        for token, candidates in FONT_TOKENS.items()
    }


def available_families() -> dict[FamilyClass, bool]:
    """Which family classes resolve on this host, via their tokens."""
    result = {}
    for family in FamilyClass:
        try:
            resolve_face(family)
            result[family] = True
        except (UnmappedFontToken, UnavailableFontToken):
            result[family] = False
    return result
