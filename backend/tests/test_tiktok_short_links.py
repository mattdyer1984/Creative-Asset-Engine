"""
Share links must import.

`https://vm.tiktok.com/<token>/` is what the TikTok app's own "Copy link"
button produces, so it is what a user actually pastes. It carries no handle
and no post id, so `_POST_URL_RE` could never match it and the importer
answered "Not a recognizable TikTok post URL" - which reads as the app
refusing a perfectly good link.

The security boundary is unchanged and is asserted here: whatever a redirect
lands on still has to survive `_normalize_post_url`'s rebuild, so a share
link cannot be used to reach an arbitrary host.
"""

from __future__ import annotations

import pytest

from app.importers.playwright_tiktok import (
    TikTokImportNotFoundError,
    _canonical_post_url,
    is_short_post_url,
)
from app.services.safe_fetch import UnsafeURLError, validate_tiktok_url

CANONICAL = "https://www.tiktok.com/@someone/photo/7412345678901234567"
SHORT = "https://vm.tiktok.com/ZN8JpA6wa/"


class _Page:
    def __init__(self, lands_on):
        self.url = lands_on
        self.closed = False

    def add_init_script(self, _script):
        pass

    def goto(self, _url, **_kwargs):
        pass

    def close(self):
        self.closed = True


class _Browser:
    """Records whether a page was opened, so pass-through is provable."""

    def __init__(self, lands_on=CANONICAL):
        self.lands_on = lands_on
        self.pages = []

    def new_page(self, **_kwargs):
        page = _Page(self.lands_on)
        self.pages.append(page)
        return page


# --- recognising the share form ------------------------------------------

@pytest.mark.parametrize("url", [
    "https://vm.tiktok.com/ZN8JpA6wa/",
    "https://vm.tiktok.com/ZN8JpA6wa",
    "https://vm.tiktok.com/ZN9rGctQ97Tgk-pImZm/",
])
def test_share_links_are_recognised(url):
    assert is_short_post_url(url)


@pytest.mark.parametrize("url", [
    CANONICAL,
    "https://www.tiktok.com/@a/video/123",
    "https://vt.tiktok.com/ZN8JpA6wa/",          # sibling domain, not evidenced
    "https://evil.test/vm.tiktok.com/ZN8JpA6wa/",  # not the host, just in the path
    "https://vm.tiktok.com.evil.test/ZN8JpA6wa/",  # suffix-confusion attempt
])
def test_non_share_forms_are_not_treated_as_share_links(url):
    assert not is_short_post_url(url)


# --- resolution -----------------------------------------------------------

def test_a_share_link_resolves_to_the_canonical_post():
    browser = _Browser(lands_on=CANONICAL)
    assert _canonical_post_url(browser, SHORT) == (
        "https://www.tiktok.com/@someone/video/7412345678901234567"
    )
    assert len(browser.pages) == 1, "should have navigated exactly once"
    assert browser.pages[0].closed, "the resolution page must be closed"


def test_a_canonical_url_does_not_open_a_page_at_all():
    """No share link, no navigation - resolution must not cost a page load."""
    browser = _Browser()
    assert _canonical_post_url(browser, CANONICAL) == (
        "https://www.tiktok.com/@someone/video/7412345678901234567"
    )
    assert browser.pages == []


def test_surrounding_whitespace_is_tolerated():
    """Pasted links routinely carry a trailing space or newline."""
    browser = _Browser(lands_on=CANONICAL)
    assert _canonical_post_url(browser, f"  {SHORT}\n").endswith("7412345678901234567")


# --- the security boundary ------------------------------------------------

def test_a_redirect_to_another_host_is_refused():
    """
    The whole point of resolving in a browser is that we do not control
    where it lands. Landing anywhere that is not a post must fail.
    """
    browser = _Browser(lands_on="https://evil.test/whatever")
    with pytest.raises(TikTokImportNotFoundError) as excinfo:
        _canonical_post_url(browser, SHORT)
    assert "did not resolve to a TikTok post" in str(excinfo.value)


def test_a_share_link_landing_on_a_shop_page_is_refused_with_advice():
    """A product share link is not a post link - say so usefully."""
    browser = _Browser(lands_on="https://www.tiktok.com/shop/gb/pdp/1729839262236121327")
    with pytest.raises(TikTokImportNotFoundError) as excinfo:
        _canonical_post_url(browser, SHORT)
    assert "copy its link" in str(excinfo.value)


# --- the allowlist --------------------------------------------------------

def test_the_share_host_is_allowed():
    assert validate_tiktok_url("https://vm.tiktok.com/ZN8JpA6wa/") == "vm.tiktok.com"


def test_the_unevidenced_sibling_domain_still_fails_closed():
    """vt.tiktok.com is real but unobserved here - it must not be pre-allowed."""
    with pytest.raises(UnsafeURLError):
        validate_tiktok_url("https://vt.tiktok.com/ZN8JpA6wa/")


def test_a_lookalike_host_is_refused():
    with pytest.raises(UnsafeURLError):
        validate_tiktok_url("https://vm.tiktok.com.evil.test/ZN8JpA6wa/")


# ---------------------------------------------------------------------------
# A pasted URL with no scheme.
#
# `tiktok.com/@someone/photo/123` is exactly what a browser address bar
# gives you. The Downie importer validated the raw string it was handed, so
# the missing scheme reached validate_tiktok_url, was refused, and surfaced
# as an unexplained HTTP 500.
# ---------------------------------------------------------------------------

from app.services.safe_fetch import normalise_pasted_url  # noqa: E402


@pytest.mark.parametrize("pasted,expected", [
    ("tiktok.com/@a/photo/1", "https://tiktok.com/@a/photo/1"),
    ("www.tiktok.com/@a/photo/1", "https://www.tiktok.com/@a/photo/1"),
    ("vm.tiktok.com/ZN8JpA6wa/", "https://vm.tiktok.com/ZN8JpA6wa/"),
    ("  tiktok.com/@a/photo/1  ", "https://tiktok.com/@a/photo/1"),
    ("tiktok.com/@a/photo/1\n", "https://tiktok.com/@a/photo/1"),
])
def test_a_missing_scheme_becomes_https(pasted, expected):
    assert normalise_pasted_url(pasted) == expected


def test_an_existing_scheme_is_left_alone():
    assert normalise_pasted_url("https://x.test/a") == "https://x.test/a"


def test_http_is_not_silently_upgraded():
    """
    Upgrading http:// here would hide it from the validators, which are
    what actually refuse plaintext. This function makes a URL parseable;
    it must never make an unsafe one acceptable.
    """
    assert normalise_pasted_url("http://x.test/a") == "http://x.test/a"
    with pytest.raises(UnsafeURLError):
        validate_tiktok_url(normalise_pasted_url("http://www.tiktok.com/@a/photo/1"))


def test_normalising_does_not_widen_the_allowlist():
    """A scheme-less hostile host must still be refused after normalising."""
    with pytest.raises(UnsafeURLError):
        validate_tiktok_url(normalise_pasted_url("evil.test/@a/photo/1"))


def test_an_empty_string_stays_empty():
    assert normalise_pasted_url("   ") == ""


def test_the_exact_url_from_the_live_failure_now_validates():
    """The paste that produced 'Request failed (500)'."""
    url = normalise_pasted_url("tiktok.com/@tokkkyshoppydeals/photo/7666826660213263638")
    assert validate_tiktok_url(url) == "tiktok.com"
