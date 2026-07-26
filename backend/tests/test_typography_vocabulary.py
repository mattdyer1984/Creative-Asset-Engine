"""
Typography vocabulary normalisation (O2).

Phase F measured typography as the largest quality gap. Categorising the
failures first - as instructed, before touching any prompt - found the cause
was neither the provider nor the benchmark. **Our own prompt told the model
to answer with a vocabulary our own validator rejected**, and every role that
complied was silently dropped: three of four designed cases produced a
typography system with ZERO text roles.

The renderer genuinely has only regular and bold faces, so the domain
vocabulary was right and the boundary was wrong.
"""

import pytest

from app.services.profile_schema import TextRole


@pytest.mark.parametrize("given,expected", [
    ("bold", "bold"), ("black", "bold"), ("heavy", "bold"),
    ("semibold", "bold"), ("extrabold", "bold"),
    ("regular", "regular"), ("normal", "regular"), ("book", "regular"),
    ("light", "regular"), ("medium", "regular"), ("thin", "regular"),
    ("BLACK", "bold"), ("  Bold  ", "bold"),
])
def test_weights_map_onto_the_two_faces_the_renderer_has(given, expected):
    assert TextRole(colour_role="b", weight=given).weight == expected


@pytest.mark.parametrize("given", ["center", "centre", "middle", "CENTER"])
def test_american_and_british_spellings_both_resolve(given):
    """
    The single highest-impact character in this file. The prompt says
    `center`, the validator demanded `centre`, and the mismatch discarded
    every role in three of four cases.
    """
    assert TextRole(colour_role="b", alignment=given).alignment == "centre"


@pytest.mark.parametrize("given,expected", [
    ("upper", "upper"), ("uppercase", "upper"), ("all-caps", "upper"),
    ("lower", "lower"), ("lowercase", "lower"),
    ("as-written", "as-written"), ("title", "as-written"),
    ("sentence", "as-written"), ("none", "as-written"),
])
def test_casing_normalises(given, expected):
    assert TextRole(colour_role="b", case=given).case == expected


def test_title_case_does_not_recase_the_copy():
    """
    ADR §5: copy policy is preserve_verbatim. Re-casing would change the
    words on the page, so `title` is honoured as as-written rather than
    implemented as a transformation.
    """
    assert TextRole(colour_role="b", case="title").case == "as-written"


@pytest.mark.parametrize("field,value", [
    ("weight", "wobbly"), ("alignment", "diagonal"), ("case", "sarcastic"),
])
def test_genuine_nonsense_is_still_rejected(field, value):
    """
    Normalising is not accepting anything. A value with no defensible
    mapping must still fail, or the vocabulary stops meaning anything.
    """
    with pytest.raises(ValueError):
        TextRole(colour_role="b", **{field: value})


def test_the_prompts_own_vocabulary_is_accepted_in_full():
    """
    The regression that matters: every value `analysis.typography_system`
    tells the model it may use must survive validation. If this fails, the
    prompt and the schema have drifted apart again.
    """
    from app.prompts import analysis

    text = analysis.TYPOGRAPHY_SYSTEM.render()
    assert "light/regular/medium/bold/black" in text
    assert "as-written/upper/lower/title" in text
    assert "left/center/right" in text

    for weight in ("light", "regular", "medium", "bold", "black"):
        for case in ("as-written", "upper", "lower", "title"):
            for alignment in ("left", "center", "right"):
                TextRole(
                    colour_role="b", weight=weight, case=case, alignment=alignment
                )
