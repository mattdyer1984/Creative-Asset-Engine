"""
SSRF protection tests (Phase 0 remediation, WP-0C).

Fully offline: DNS is stubbed via monkeypatching `socket.getaddrinfo`,
and HTTP via `httpx.MockTransport`. No test here opens a real socket.

Covers the eight negative cases WP-0C requires, plus positive cases
proving legitimate imports still work - a security control that blocks
everything is not a fix.
"""

import httpx
import pytest

from app.services import safe_fetch
from app.services.safe_fetch import (
    UnsafeURLError,
    fetch_public,
    looks_like_image,
    validate_public_url,
    validate_tiktok_url,
)


def _stub_dns(monkeypatch, mapping: dict[str, list[str]]):
    """Deterministic name -> address resolution, no network."""

    def fake_getaddrinfo(host, *args, **kwargs):
        if host not in mapping:
            raise OSError(f"unstubbed host in test: {host}")
        return [(None, None, None, "", (addr, 0)) for addr in mapping[host]]

    monkeypatch.setattr(safe_fetch.socket, "getaddrinfo", fake_getaddrinfo)


# --- The eight required negative cases -------------------------------


@pytest.mark.parametrize(
    "url, resolved, expect",
    [
        ("https://evil.test/", ["127.0.0.1"], "loopback"),
        ("https://localhost.test/", ["127.0.0.1"], "loopback"),
        ("https://internal.test/", ["10.0.0.5"], "private"),
        ("https://internal.test/", ["192.168.1.1"], "private"),
        ("https://internal.test/", ["172.16.0.1"], "private"),
        ("https://metadata.test/", ["169.254.169.254"], "link-local"),
        ("https://v6.test/", ["::1"], "loopback"),
        ("https://v6private.test/", ["fd00::1"], "private"),
    ],
)
def test_rejects_non_public_addresses(monkeypatch, url, resolved, expect):
    _stub_dns(monkeypatch, {httpx.URL(url).host: resolved})
    with pytest.raises(UnsafeURLError) as exc:
        validate_public_url(url)
    assert expect in str(exc.value)


def test_rejects_non_https_schemes(monkeypatch):
    for url in ("http://example.test/", "file:///etc/passwd", "ftp://example.test/", "gopher://x.test/"):
        with pytest.raises(UnsafeURLError) as exc:
            validate_public_url(url)
        assert "only https" in str(exc.value)


def test_rejects_a_public_url_that_redirects_to_a_private_address(monkeypatch):
    """The headline case: validating only the first URL is not enough."""
    _stub_dns(monkeypatch, {"public.test": ["93.184.216.34"], "internal.test": ["169.254.169.254"]})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "public.test":
            return httpx.Response(302, headers={"location": "https://internal.test/secrets"})
        return httpx.Response(200, content=b"SHOULD NEVER BE REACHED")

    # transport is injected, but redirect hops must still be validated -
    # so DNS validation is forced on for this test via resolve-capable URLs.
    monkeypatch.setattr(safe_fetch, "MAX_REDIRECTS", 5)
    with pytest.raises(UnsafeURLError) as exc:
        _fetch_with_forced_resolution(
            "https://public.test/", transport=httpx.MockTransport(handler)
        )
    assert "link-local" in str(exc.value)


def _fetch_with_forced_resolution(url, *, transport):
    """
    fetch_public skips DNS when a transport is injected (tests are
    network-free). This helper re-enables validation so redirect-hop
    checking can be exercised with a mock transport.
    """
    original = safe_fetch.validate_public_url

    def always_resolve(u, *, resolve=True):
        return original(u, resolve=True)

    safe_fetch.validate_public_url = always_resolve
    try:
        return fetch_public(url, max_bytes=1024, transport=transport)
    finally:
        safe_fetch.validate_public_url = original


def test_rejects_invalid_image_content():
    assert looks_like_image(b"\xff\xd8\xff\xe0rest", "image/jpeg") is True
    assert looks_like_image(b"\x89PNG\r\n\x1a\nrest", "image/png") is True
    # A lying Content-Type must not be enough on its own.
    assert looks_like_image(b"<!DOCTYPE html><html>", "image/png") is False
    assert looks_like_image(b"#!/bin/sh\nrm -rf /", "image/jpeg") is False


# --- Positive cases: legitimate traffic must still work --------------


def test_allows_a_normal_public_https_site(monkeypatch):
    _stub_dns(monkeypatch, {"shop.example.test": ["93.184.216.34"]})
    assert validate_public_url("https://shop.example.test/product/1") == "shop.example.test"


def test_allows_evidenced_tiktok_hosts():
    # Every host below was observed in a real successful import.
    assert validate_tiktok_url("https://www.tiktok.com/@u/photo/123") == "www.tiktok.com"
    assert validate_tiktok_url("https://shop.tiktok.com/gb/pdp/456") == "shop.tiktok.com"
    assert (
        validate_tiktok_url("https://p16-common-sign.tiktokcdn-eu.com/x.jpeg")
        == "p16-common-sign.tiktokcdn-eu.com"
    )
    assert (
        validate_tiktok_url("https://p19-common-sign.tiktokcdn-eu.com/y.jpeg")
        == "p19-common-sign.tiktokcdn-eu.com"
    )


def test_tiktok_allowlist_rejects_lookalike_domains():
    """Suffix matching must respect label boundaries."""
    for url in (
        "https://eviltiktokcdn-eu.com/x.jpg",
        "https://tiktokcdn-eu.com.evil.test/x.jpg",
        "https://www.tiktok.com.evil.test/x",
        "https://evil.test/?u=www.tiktok.com",
    ):
        with pytest.raises(UnsafeURLError):
            validate_tiktok_url(url)


def test_tiktok_allowlist_rejects_unevidenced_tiktok_cdn():
    """
    Non-EU tiktokcdn.com is deliberately absent until a real import
    evidences it - fails closed and reports, per the agreed discipline.
    """
    with pytest.raises(UnsafeURLError) as exc:
        validate_tiktok_url("https://p16-sign.tiktokcdn.com/x.jpeg")
    assert "not in the TikTok allowlist" in str(exc.value)


def test_successful_fetch_returns_content(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>ok</html>", headers={"content-type": "text/html"})

    result = fetch_public(
        "https://shop.example.test/p", max_bytes=1024, transport=httpx.MockTransport(handler)
    )
    assert result.content == b"<html>ok</html>"
    assert "text/html" in result.content_type


def test_size_cap_is_enforced():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 5000)

    with pytest.raises(ValueError, match="exceeded"):
        fetch_public(
            "https://shop.example.test/p", max_bytes=1000, transport=httpx.MockTransport(handler)
        )


def test_redirect_limit_is_enforced():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://shop.example.test/next"})

    with pytest.raises(UnsafeURLError, match="Too many redirects"):
        fetch_public(
            "https://shop.example.test/p", max_bytes=1024, transport=httpx.MockTransport(handler)
        )


# --- The documented local-development escape hatch -------------------


def test_loopback_is_blocked_by_default(monkeypatch):
    _stub_dns(monkeypatch, {"fixtures.test": ["127.0.0.1"]})
    monkeypatch.delenv("SAFE_FETCH_ALLOW_LOOPBACK", raising=False)
    with pytest.raises(UnsafeURLError, match="loopback"):
        validate_public_url("https://fixtures.test/bundle.html")


def test_loopback_opt_in_permits_local_fixture_servers(monkeypatch):
    """
    Verified against the real dev DB: local fixtures were imported from
    http://127.0.0.1:8123 while building Bundle Composition. The opt-in
    keeps that workflow working without weakening the default.
    """
    _stub_dns(monkeypatch, {"127.0.0.1": ["127.0.0.1"]})
    monkeypatch.setenv("SAFE_FETCH_ALLOW_LOOPBACK", "1")
    assert validate_public_url("http://127.0.0.1:8123/bundle.html") == "127.0.0.1"


def test_loopback_opt_in_does_not_permit_other_private_ranges(monkeypatch):
    """The escape hatch is loopback-only - it must not open RFC1918."""
    _stub_dns(monkeypatch, {"internal.test": ["10.1.2.3"]})
    monkeypatch.setenv("SAFE_FETCH_ALLOW_LOOPBACK", "1")
    with pytest.raises(UnsafeURLError, match="private"):
        validate_public_url("https://internal.test/")


def test_mixed_public_and_private_resolution_is_rejected(monkeypatch):
    """A name resolving to both must not be reachable via the public one."""
    _stub_dns(monkeypatch, {"sneaky.test": ["93.184.216.34", "10.0.0.1"]})
    with pytest.raises(UnsafeURLError, match="private"):
        validate_public_url("https://sneaky.test/")
