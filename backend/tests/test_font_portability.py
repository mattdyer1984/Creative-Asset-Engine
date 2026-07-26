"""
Font portability (P2).

Rendering must not depend on which machine drew it. A benchmark scored
against whatever faces a host happens to have is not a benchmark, and every
host candidate in `FONT_TOKENS` is macOS-only.

These tests cover the MECHANISM. They pass whether or not the redistributable
faces are installed, because the mechanism is what this codebase owns - the
faces are an asset-acquisition step (`scripts/fetch_fonts.py`).
"""

import pathlib

import pytest

from app.services.typography import (
    FONT_TOKENS,
    VENDORED_FACES,
    UnavailableFontToken,
    assert_fonts_are_portable,
    font_root,
    font_source,
    resolve_token,
)


def test_every_token_has_a_vendored_face_mapped():
    """
    A token with no bundled mapping can never become portable, so the gap
    must be visible here rather than at deployment.
    """
    unmapped = sorted(set(FONT_TOKENS) - set(VENDORED_FACES))
    assert unmapped == [], f"no redistributable face is mapped for {unmapped}"


def test_vendored_faces_are_filenames_not_absolute_paths():
    """The directory is configurable; baking a path in would defeat that."""
    for token, name in VENDORED_FACES.items():
        assert not pathlib.Path(name).is_absolute(), f"{token} maps to an absolute path"


def test_a_bundled_face_wins_over_a_host_face(tmp_path, monkeypatch):
    """
    Order is deliberate. Host fonts are a development convenience; if they
    won, a developer's machine would silently produce different output from
    production - the portability problem restated, not solved.
    """
    face = tmp_path / VENDORED_FACES["serif_editorial_regular"]
    face.write_bytes(b"not a real font, but it exists")
    monkeypatch.setattr("app.config.settings.font_root", tmp_path)

    path, index = resolve_token("serif_editorial_regular")
    assert path == str(face)
    assert index == 0
    assert font_source("serif_editorial_regular") == "vendored"


def test_a_missing_face_names_what_it_looked_for(tmp_path, monkeypatch):
    """
    The error has to be actionable: which token, which filename, which
    directory, and what to run.
    """
    monkeypatch.setattr("app.config.settings.font_root", tmp_path)
    monkeypatch.setattr("app.services.typography.FONT_TOKENS",
                        {"serif_editorial_regular": [("/nonexistent.ttf", 0)]})

    with pytest.raises(UnavailableFontToken) as exc:
        resolve_token("serif_editorial_regular")
    message = str(exc.value)
    assert VENDORED_FACES["serif_editorial_regular"] in message
    assert str(tmp_path) in message
    assert "fetch_fonts" in message


def test_the_portability_gate_refuses_host_only_fonts(tmp_path, monkeypatch):
    """
    The production check. Host faces are fine on a Mac and not fine in
    production, and the difference must be enforced rather than remembered.
    """
    monkeypatch.setattr("app.config.settings.font_root", tmp_path)
    with pytest.raises(UnavailableFontToken, match="only a HOST face|no face at all"):
        assert_fonts_are_portable()


def test_the_gate_passes_when_every_face_is_bundled(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.font_root", tmp_path)
    for name in VENDORED_FACES.values():
        (tmp_path / name).write_bytes(b"face")
    assert_fonts_are_portable()


def test_font_root_is_configurable(tmp_path, monkeypatch):
    """So a deployment can supply licensed brand faces without a code change."""
    monkeypatch.setattr("app.config.settings.font_root", tmp_path)
    assert font_root() == tmp_path


def test_no_font_is_committed_without_a_pinned_checksum():
    """
    An unverified binary must not reach the renderer. A face present in the
    repository with a blank pin would be exactly that.
    """
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))
    from fetch_fonts import FONTS, FONT_DIR

    for name, (_, expected) in FONTS.items():
        if (FONT_DIR / name).exists():
            assert expected, (
                f"{name} is committed but has no SHA-256 pin in fetch_fonts.py"
            )
