"""
SSRF protection for server-side fetches of user-supplied URLs
(Phase 0 remediation, WP-0C).

Before this module, four call sites each fetched user-controlled URLs
with their own ad-hoc httpx client, no scheme check, no address
validation, and `follow_redirects=True` with httpx's default of 20 hops
- so a public URL could 302 to `169.254.169.254` (cloud metadata) or an
RFC1918 host and the response would be returned to the caller. This is
the single shared implementation those sites now use.

Two tiers, because the two use cases have genuinely different threat
models:

- `validate_tiktok_url` - a strict, evidence-based hostname allowlist
  for the TikTok importers, which only ever legitimately talk to TikTok.
- `validate_public_url` / `fetch_public` - for generic product-page
  imports, which must be able to reach *any* public HTTPS site, so the
  defence is "reject everything that isn't publicly routable" rather
  than an allowlist.

Design decisions worth knowing:

**Certificate verification is never disabled**, and hostnames are never
swapped for their IPs before connecting. Substituting the IP would break
TLS hostname verification (or force disabling it), trading an SSRF hole
for a MITM hole. Instead: resolve, validate *every* returned address,
then connect normally by hostname with verification fully intact.

**Known, accepted residual risk - DNS rebinding.** Because we validate
the resolved addresses and then let httpx resolve again when it
connects, a hostile DNS server that returns a public address on the
first lookup and a private one on the second could slip past. Closing
this completely requires pinning the connection to the validated IP
while still presenting the original SNI/Host for certificate
verification, which httpx does not expose cleanly. The window is narrow
(two lookups, milliseconds apart, and the attacker must control
authoritative DNS for the name), and every redirect hop is re-validated,
so this is documented and accepted rather than silently ignored. It is
the one thing to revisit if this app ever becomes multi-tenant or
internet-facing.

**Redirects are followed manually**, one hop at a time, so each new
destination is re-validated. `follow_redirects=True` would let httpx
chase a redirect chain internally with no opportunity to check where it
is going.

**Loopback is blocked by default but has an explicit dev opt-in.**
Verified against the real dev database: local product-page fixtures were
imported from `http://127.0.0.1:8123/...` while Bundle Composition was
being built. Blocking loopback outright would silently break that
workflow. `SAFE_FETCH_ALLOW_LOOPBACK=1` re-enables it, off by default,
never set in normal operation, and it logs a warning every time it
applies so it cannot be on by accident without leaving evidence.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_REDIRECTS = 5

# Evidence-based allowlist. Every entry below was observed in a real,
# successful import in the development database (slides.source_locator,
# listings.source_url, product_source_imports.source_url) - nothing here
# is speculative, per WP-0C's "do not guess the CDN allowlist".
#
# Exact hostnames:
TIKTOK_ALLOWED_HOSTS = frozenset(
    {
        "www.tiktok.com",  # observed: slides, listings, product_source_imports
        "tiktok.com",      # bare-domain form of the above
        "shop.tiktok.com",  # observed: product_source_imports (product pages)
    }
)
# Domain suffixes. TikTok serves slide images from numbered CDN hosts
# (p16-common-sign..., p19-common-sign... were both observed) and the
# number rotates, so pinning the two exact hosts seen so far would break
# real imports. This is deliberately the registrable domain and no
# broader - it is not a wildcard added "to make imports work".
#
# Note: only the EU CDN domain is evidenced. `tiktokcdn.com` (non-EU) is
# deliberately NOT listed - it has never been observed here, and per the
# agreed discipline an unevidenced host fails closed and gets reported
# rather than pre-emptively allowed.
TIKTOK_ALLOWED_DOMAIN_SUFFIXES = ("tiktokcdn-eu.com",)


class UnsafeURLError(ValueError):
    """Raised when a URL is rejected before any connection is attempted."""


@dataclass(frozen=True)
class FetchResult:
    content: bytes
    content_type: str
    final_url: str


def _allow_loopback() -> bool:
    return os.environ.get("SAFE_FETCH_ALLOW_LOOPBACK") == "1"


def _parse(url: str) -> tuple[str, str | None]:
    """
    Returns (scheme, hostname). Deliberately does NOT raise on a missing
    hostname: callers check the scheme first, so a `file:///etc/passwd`
    URL is rejected for the accurate reason (disallowed scheme) rather
    than the incidental one (no hostname).
    """
    try:
        parsed = urlparse(url)
    except Exception as exc:  # pragma: no cover - urlparse is very tolerant
        raise UnsafeURLError(f"Could not parse URL: {url}") from exc

    return (parsed.scheme or "").lower(), parsed.hostname


def _require_hostname(hostname: str | None, url: str) -> str:
    if not hostname:
        raise UnsafeURLError(f"URL has no hostname: {url}")
    return hostname


def _assert_address_is_public(address: str, *, url: str) -> None:
    ip = ipaddress.ip_address(address)

    if ip.is_loopback:
        if _allow_loopback():
            logger.warning(
                "SAFE_FETCH_ALLOW_LOOPBACK=1 - permitting loopback fetch of %s. "
                "This is a local-development escape hatch and must never be set "
                "in a deployed or shared environment.",
                url,
            )
            return
        raise UnsafeURLError(
            f"Refusing to fetch {url}: resolves to loopback address {address}. "
            "Set SAFE_FETCH_ALLOW_LOOPBACK=1 only for local fixture servers."
        )

    # Order matters for the error message, not for safety: Python treats
    # 169.254.0.0/16 as BOTH link-local and private, so the more specific
    # label is checked first. That range holds the cloud metadata endpoint
    # 169.254.169.254 - the single most valuable SSRF target - and naming
    # it "link-local" makes the rejection far easier to diagnose than the
    # generic "private".
    for predicate, description in (
        (ip.is_link_local, "link-local"),
        (ip.is_private, "private"),
        (ip.is_multicast, "multicast"),
        (ip.is_reserved, "reserved"),
        (ip.is_unspecified, "unspecified"),
    ):
        if predicate:
            raise UnsafeURLError(
                f"Refusing to fetch {url}: resolves to {description} address {address}."
            )


def validate_public_url(url: str, *, resolve: bool = True) -> str:
    """
    Validates a URL destined for the open internet. Returns the hostname.

    `resolve=False` performs scheme/shape checks only and skips DNS -
    used when the caller has injected a mock transport, where no real
    socket is opened and there is therefore no SSRF risk to defend
    against (this is what keeps the test suite network-free).
    """
    scheme, raw_hostname = _parse(url)

    # Scheme is checked before hostname so file:// / gopher:// are
    # rejected for the real reason rather than "no hostname".
    if scheme != "https":
        # http is permitted only alongside the loopback dev opt-in, since
        # a local fixture server has no certificate.
        if not (scheme == "http" and _allow_loopback()):
            raise UnsafeURLError(
                f"Refusing to fetch {url}: only https:// is allowed (got {scheme or 'no scheme'}://)."
            )

    hostname = _require_hostname(raw_hostname, url)

    if not resolve:
        return hostname

    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Could not resolve host for {url}: {exc}") from exc

    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise UnsafeURLError(f"Host for {url} resolved to no addresses.")

    # EVERY address must be public - a name resolving to both a public and
    # a private address must not be reachable via the public one.
    for address in sorted(addresses):
        _assert_address_is_public(address, url=url)

    return hostname


def validate_tiktok_url(url: str) -> str:
    """
    Strict allowlist for the TikTok importers. Returns the hostname.

    Deliberately does not fall through to `validate_public_url`'s
    "anything public" policy: these importers have no legitimate reason
    to contact any other host, so the tighter rule is the correct one.
    """
    scheme, raw_hostname = _parse(url)
    if scheme != "https":
        raise UnsafeURLError(f"Refusing to fetch {url}: only https:// is allowed for TikTok URLs.")

    hostname = _require_hostname(raw_hostname, url)
    host = hostname.lower().rstrip(".")
    if host in TIKTOK_ALLOWED_HOSTS:
        return hostname
    for suffix in TIKTOK_ALLOWED_DOMAIN_SUFFIXES:
        # Suffix match must be on a label boundary: "eviltiktokcdn-eu.com"
        # must not satisfy a "tiktokcdn-eu.com" rule.
        if host == suffix or host.endswith("." + suffix):
            return hostname

    raise UnsafeURLError(
        f"Refusing to fetch {url}: host {hostname!r} is not in the TikTok allowlist. "
        "If this is a legitimate TikTok host, add it with evidence of a real "
        "successful import rather than widening the rule speculatively."
    )


def fetch_public(
    url: str,
    *,
    max_bytes: int,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    headers: dict[str, str] | None = None,
    transport: httpx.BaseTransport | None = None,
) -> FetchResult:
    """
    Fetches a user-supplied public URL with SSRF protection, a byte cap,
    and manual per-hop redirect validation.

    `transport` is for tests: when injected, DNS/address validation is
    skipped (no real socket is opened) while scheme validation still
    applies, so the suite stays network-free.
    """
    resolve = transport is None
    current_url = url

    with httpx.Client(
        transport=transport,
        timeout=timeout,
        follow_redirects=False,  # each hop is validated explicitly below
    ) as client:
        for _hop in range(MAX_REDIRECTS + 1):
            validate_public_url(current_url, resolve=resolve)

            with client.stream("GET", current_url, headers=headers or {}) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise UnsafeURLError(
                            f"Redirect from {current_url} had no Location header."
                        )
                    # Resolve relative redirects against the current URL,
                    # then re-validate on the next loop iteration - this
                    # is the check that stops public -> private hops.
                    current_url = str(httpx.URL(current_url).join(location))
                    continue

                response.raise_for_status()

                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError(
                            f"Response from {current_url} exceeded {max_bytes} bytes"
                        )
                    chunks.append(chunk)

                return FetchResult(
                    content=b"".join(chunks),
                    content_type=response.headers.get("content-type", ""),
                    final_url=current_url,
                )

    raise UnsafeURLError(f"Too many redirects (>{MAX_REDIRECTS}) starting from {url}.")


def looks_like_image(content: bytes, content_type: str) -> bool:
    """
    Content-sniffing image check - WP-0C requires verifying that a
    download is actually an image before saving it, and a
    `Content-Type` header alone is attacker-controlled.
    """
    if content.startswith(b"\xff\xd8\xff"):
        return True  # JPEG
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return True  # PNG
    if content.startswith(b"GIF87a") or content.startswith(b"GIF89a"):
        return True  # GIF
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return True  # WebP
    if content[4:12] in (b"ftypavif", b"ftypavis"):
        return True  # AVIF
    return False
