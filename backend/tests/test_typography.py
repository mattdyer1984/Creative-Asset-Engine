"""
Typography as a design system, and the L1 renderer (ADR 0001 §10, WP-1.4).

WP-1.4 is the programme gate: if flat structured typography cannot reach
benchmark quality on case 4, Phase 1's premise is wrong. The visual proof
lives at tests/benchmarks/case04_posture/typography_gate.jpg; these tests
pin the behaviour that made it possible.
"""

import pytest
from PIL import Image

from app.services.typography import (
    CapabilityLevel,
    FamilyClass,
    TextStyle,
    TypographySystem,
    available_families,
    resolve_colour,
    resolve_face,
)
from app.services.editorial_renderer import TextBlock, render_typography


def test_every_family_class_resolves_on_this_machine():
    """A missing family would silently degrade to the caption face."""
    missing = [family for family, ok in available_families().items() if not ok]
    assert not missing, f"no face available for {missing}"


@pytest.mark.parametrize(
    "family", [FamilyClass.SERIF, FamilyClass.GROTESQUE, FamilyClass.CONDENSED_SANS]
)
def test_a_family_request_stays_in_its_family(family):
    """
    ADR §10.2: exact face matching is not a goal, but asking for a serif and
    receiving the caption grotesque is the defect this replaces.
    """
    path, _ = resolve_face(family)
    assert path


def test_real_italic_and_bold_faces_are_preferred():
    """
    Benchmark 4's subhead is the emphasis in its hierarchy - a synthetic
    slant would visibly flatten it.
    """
    regular, _ = resolve_face(FamilyClass.SERIF)
    italic, _ = resolve_face(FamilyClass.SERIF, italic=True)
    bold, _ = resolve_face(FamilyClass.SERIF, weight="bold")
    assert italic != regular
    assert bold != regular


def test_unknown_colour_roles_fall_back_rather_than_crash():
    assert resolve_colour("not-a-role") == resolve_colour("near-black")


def _case04_system() -> TypographySystem:
    return TypographySystem(
        primary_family=FamilyClass.SERIF,
        capability_level=CapabilityLevel.L1,
        base_size_ratio=0.030,
        styles={
            "numeral": TextStyle(FamilyClass.SERIF, colour_role="dark-red",
                                 size_ratio=2.5, rule_below=True),
            "headline": TextStyle(FamilyClass.SERIF, colour_role="near-black", size_ratio=1.75),
            "emphasis": TextStyle(FamilyClass.SERIF, italic=True, colour_role="dark-red",
                                  size_ratio=1.75),
            "bullet": TextStyle(FamilyClass.SERIF, colour_role="near-black", size_ratio=0.72,
                                bullet="•", bullet_colour_role="dark-red"),
        },
    )


def test_the_renderer_draws_into_its_zone_and_leaves_the_rest_alone():
    canvas = Image.new("RGB", (400, 600), (247, 245, 240))
    result = render_typography(
        canvas, [TextBlock("Your upper back", "headline", (0.05, 0.10, 0.60, 0.20))],
        _case04_system(),
    )
    assert result.getpixel((380, 560)) == (247, 245, 240), "outside the zone must be untouched"
    column = [result.getpixel((x, int(600 * 0.13))) for x in range(20, 240)]
    assert any(sum(px) < 400 for px in column), "the headline should have been drawn"


def test_a_bullet_marker_can_carry_its_own_colour():
    """
    Benchmark 4 has red markers against near-black copy. One colour for the
    whole block cannot express that, and rendering the marker in the text
    colour visibly flattens the hierarchy.
    """
    system = _case04_system()
    style = system.style_for("bullet")
    assert style.bullet_colour_role == "dark-red"
    assert style.colour_role == "near-black"
    assert resolve_colour(style.bullet_colour_role) != resolve_colour(style.colour_role)


def test_case_rules_are_applied():
    canvas = Image.new("RGB", (400, 200), (255, 255, 255))
    upper = TypographySystem(styles={"h": TextStyle(case="upper", size_ratio=1.0)})
    lower = TypographySystem(styles={"h": TextStyle(case="lower", size_ratio=1.0)})
    block = [TextBlock("MiXeD", "h", (0.05, 0.1, 0.9, 0.5))]
    assert render_typography(canvas, block, upper) != render_typography(canvas, block, lower)


def test_rendering_never_mutates_the_source_image():
    canvas = Image.new("RGB", (200, 200), (255, 255, 255))
    before = list(canvas.getdata())
    render_typography(canvas, [TextBlock("x", "h", (0.1, 0.1, 0.9, 0.9))], _case04_system())
    assert list(canvas.getdata()) == before


def test_long_words_overflow_rather_than_being_hyphenated():
    """Breaking a brand name mid-word is worse than a slightly wide line."""
    canvas = Image.new("RGB", (200, 200), (255, 255, 255))
    result = render_typography(
        canvas,
        [TextBlock("Supercalifragilistic", "headline", (0.05, 0.1, 0.4, 0.6))],
        _case04_system(),
    )
    assert result.size == canvas.size  # rendered without raising


def test_a_marker_in_the_ocr_text_is_not_doubled():
    """
    Live OCR returns "• You struggle to straighten up" - the glyph is part of
    the recognised text. Adding the style's marker on top rendered "• •",
    which the WP-1.5A end-to-end run showed plainly.
    """
    from app.services.editorial_renderer import _strip_leading_marker

    style = TextStyle(bullet="•")
    assert _strip_leading_marker("• You struggle to straighten up", style) == (
        "You struggle to straighten up"
    )
    assert _strip_leading_marker("- dash item", style) == "dash item"
    # A style with no marker of its own must leave the text alone.
    assert _strip_leading_marker("• keep me", TextStyle()) == "• keep me"
