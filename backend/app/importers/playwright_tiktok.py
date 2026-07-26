"""
PlaywrightTikTokImporter — the native TikTok Import Provider (Phase 10.6
of AI Creative Engine vNext, see MIGRATION_PLAN.md's "ADR: AI Creative
Engine vNext" §5a). Recommended over DownieImporter per that section:
one synchronous operation (load the page, parse one embedded JSON blob
for metadata + signed media URLs, fetch each media URL, assemble one
EvidencePackage) - no folder-polling completion heuristic to build.

source_config shape: {"url": "https://www.tiktok.com/@handle/video/123"}
(a "/photo/..." URL also works - see _normalize_post_url).

**Scope boundary, real and load-bearing, not a limitation to route
around**: this codebase's entire Slide-analysis pipeline (OCR, Product
Isolation, Creative Fingerprint, ...) calls `PIL.Image.open()` directly
on a Slide's stored bytes (app/slideshow_stages/product_isolation_stage.py)
- it has no video-handling capability anywhere. A TikTok "slideshow" post
frequently resolves to a pre-baked video export, not a true photo-mode
`imagePost` (confirmed directly, again, in this phase's own live
verification - see below), and importing one as a Slide would corrupt
the very first downstream stage that opens it. `import_source` therefore
only ever returns real, static images (`itemStruct["imagePost"]`) and
raises `TikTokImportUnsupportedContentError` for a video-only post,
rather than silently shipping bytes nothing here can read.

Real, live findings from this phase's verification (2026-07-23), beyond
what the ADR's own earlier investigation established:

- TikTok's "/photo/{id}" URL alias for a photo-mode post does NOT
  reliably carry the item's data server-side - confirmed directly: an
  unblocked, real fetch of a real "/photo/" URL rendered with no
  `webapp.video-detail` scope at all, while the same post's "/video/{id}"
  alias reliably carried it, for both true photo-mode AND ordinary video
  posts. This importer always rewrites a given URL to its "/video/{id}"
  form before navigating - the only form confirmed to work, not a
  workaround for its own sake.
- The slider-puzzle anti-bot challenge is real and appeared repeatedly on
  this session's own live requests - not hypothetical, and not rare: a
  stealth launch flag (--disable-blink-features=AutomationControlled)
  measurably reduces how often it appears (a bare headless launch hit it
  immediately) but does not eliminate it, and this session directly
  observed the block rate climbing across a handful of requests to the
  same URL in a short window - a real, live-confirmed instance of the
  "scale/sustained-use risk" the ADR flagged as untested, not assumed.
  This importer retries a bounded number of times on a fresh page, then
  fails cleanly with TikTokImportBlockedError rather than silently
  returning an empty package or hanging - the caller (the import
  endpoint) surfaces that as a real, honest failure, matching the
  "no hang, no false success" discipline Downie's own fallback design
  already commits to.
- The real, confirmed `imagePost` shape for a true photo-mode post:
  `itemStruct["imagePost"] = {"images": [{"imageURL": {"urlList": [...]},
  "imageWidth": int, "imageHeight": int}, ...], "cover": {...},
  "shareCover": {...}, "title": str}` - the first URL in each image's
  `urlList` is what actually gets fetched.
- Media (both video `playAddr`, kept only to detect and reject it, and
  photo-mode `imageURL.urlList[0]`) must be fetched through the SAME
  browser context that loaded the page
  (`page.context.request.get(..., headers={"Referer": ...})`) - a bare
  standalone HTTP client (tried directly, this session) gets a real 403;
  the signed URL is session/cookie-bound, not just Referer-bound.
- No product-tag structure was found in the one real TikTok-Shop-tagged
  post this session could reach before the block rate rose (only a
  CapCut-attribution `anchors` entry, unrelated to product tagging) -
  `product_references` stays empty rather than guessed. A genuinely new
  extraction path (§6) is still real future work; this is an honest
  "not found yet," not a claim that it doesn't exist.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO

from PIL import Image, UnidentifiedImageError
from playwright.sync_api import Browser, sync_playwright

from app.domain import CreatorInfo, EvidencePackage, MarketingCreative
from app.services.safe_fetch import UnsafeURLError, validate_tiktok_url

STEALTH_ARGS = ["--disable-blink-features=AutomationControlled"]
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REFERER = "https://www.tiktok.com/"
MAX_ATTEMPTS = 3
NAV_TIMEOUT_MS = 25_000

_POST_URL_RE = re.compile(r"tiktok\.com/@([^/?]+)/(?:video|photo)/(\d+)")
_WEBDRIVER_OVERRIDE_SCRIPT = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"


class TikTokImportError(Exception):
    """Base for every real failure this importer can raise - never a silent empty EvidencePackage."""


class TikTokImportBlockedError(TikTokImportError):
    """TikTok's anti-bot challenge (the slider puzzle) blocked every attempt."""


class TikTokImportNotFoundError(TikTokImportError):
    """The URL didn't resolve to a real, parseable TikTok post."""


class TikTokImportUnsupportedContentError(TikTokImportError):
    """A real post was found, but it's a video, not a photo-mode slideshow - see module docstring."""


def _normalize_post_url(url: str) -> str:
    """
    SSRF hardening (Phase 0, WP-0C): the rebuild below was already the
    codebase's only effective allowlist - whatever came in, what goes out
    is always a literal https://www.tiktok.com/... URL. But `_POST_URL_RE`
    is unanchored, so `https://evil.test/?x=tiktok.com/@a/video/1` also
    matched; harmless for the rebuilt URL itself, but it meant a hostile
    string could reach this path at all. The explicit validation makes
    the guarantee checkable rather than incidental.
    """
    match = _POST_URL_RE.search(url)
    if match is None:
        raise TikTokImportNotFoundError(f"Not a recognizable TikTok post URL: {url}")
    handle, post_id = match.groups()
    normalized = f"https://www.tiktok.com/@{handle}/video/{post_id}"
    validate_tiktok_url(normalized)
    return normalized


#: The share form. `https://vm.tiktok.com/<token>/` is what the TikTok app's
#: own "Copy link" button produces, so it is what people actually paste - and
#: it carries no handle or post id, so `_POST_URL_RE` can never match it.
#: Rejecting it read as "the app won't accept my link".
_SHORT_URL_RE = re.compile(r"^https://vm\.tiktok\.com/[A-Za-z0-9_-]+/?$")


def is_short_post_url(url: str) -> bool:
    return _SHORT_URL_RE.match(url.strip()) is not None


def _resolve_short_url(browser: Browser, url: str) -> str:
    """
    Follow a share link to the canonical post URL.

    Resolved by navigating in the browser we already have, rather than by
    adding another HTTP path: TikTok answers short links with a redirect
    plus its own bot checks, and this browser is already configured to get
    through them.

    **The security guarantee is unchanged.** The input host is validated
    against the strict TikTok allowlist before navigating, and whatever the
    redirect lands on is handed straight to `_normalize_post_url`, which
    rebuilds a literal `https://www.tiktok.com/@handle/video/id` from a
    regex match. A redirect to somewhere unexpected therefore cannot become
    a fetched URL - it fails the rebuild.
    """
    validate_tiktok_url(url)

    page = browser.new_page(user_agent=USER_AGENT)
    page.add_init_script(_WEBDRIVER_OVERRIDE_SCRIPT)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        resolved = page.url
    finally:
        page.close()

    if _POST_URL_RE.search(resolved) is None:
        raise TikTokImportNotFoundError(
            f"{url} did not resolve to a TikTok post - it went to {resolved}. "
            "Share links for products or profiles are not post URLs; open the "
            "slideshow itself and copy its link."
        )
    return resolved


def _canonical_post_url(browser: Browser, url: str) -> str:
    """Accept either a canonical post URL or a share link."""
    url = url.strip()
    if is_short_post_url(url):
        return _normalize_post_url(_resolve_short_url(browser, url))
    return _normalize_post_url(url)


def _is_blocked(body_text: str) -> bool:
    return "puzzle" in body_text.lower()


def _creator_from_item(item: dict) -> CreatorInfo | None:
    author = item.get("author")
    if not author:
        return None
    handle = author.get("uniqueId")
    return CreatorInfo(
        handle=f"@{handle}" if handle else None,
        display_name=author.get("nickname"),
        profile_url=f"https://www.tiktok.com/@{handle}" if handle else None,
    )


@dataclass
class TikTokContentInfo:
    """
    The independent, provider-agnostic ground truth for "what is this
    post and how many slides should it have" - the Critical TikTok
    Slideshow Import Fix (see MIGRATION_PLAN.md). Known *before* either
    Import Provider downloads a single pixel, since DownieImporter's own
    automation surface has no way to learn an expected count on its own
    (see its module docstring).
    """

    content_type: str  # "slideshow" | "video"
    expected_slide_count: int  # 0 for a video post
    item: dict  # the raw item struct - reused by callers to avoid a second scrape


def detect_tiktok_content(url: str) -> TikTokContentInfo:
    """
    Fetches+parses the item struct only - no image downloads - to learn
    the content type and expected slide count ahead of picking an Import
    Provider. Reuses the exact same `_fetch_item_struct` mechanism
    `import_source` itself uses, so this is real, live-verified TikTok
    scraping, not a lighter-weight approximation of it.
    """
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=STEALTH_ARGS)
        try:
            # Inside the browser context: a share link can only be resolved
            # by following it, and the browser is what gets past TikTok's
            # bot checks.
            item = _fetch_item_struct(browser, _canonical_post_url(browser, url))
        finally:
            browser.close()

    image_post = item.get("imagePost")
    if not image_post:
        return TikTokContentInfo(content_type="video", expected_slide_count=0, item=item)
    images = image_post.get("images", [])
    return TikTokContentInfo(content_type="slideshow", expected_slide_count=len(images), item=item)


def _fetch_item_struct(browser: Browser, url: str) -> dict:
    for _attempt in range(MAX_ATTEMPTS):
        page = browser.new_page(user_agent=USER_AGENT)
        page.add_init_script(_WEBDRIVER_OVERRIDE_SCRIPT)
        try:
            page.goto(url, wait_until="networkidle", timeout=NAV_TIMEOUT_MS)
            if _is_blocked(page.inner_text("body")):
                continue

            raw = page.eval_on_selector(
                "script#__UNIVERSAL_DATA_FOR_REHYDRATION__",
                "el => el ? el.textContent : null",
            )
            if raw is None:
                raise TikTokImportNotFoundError(f"No TikTok data found for {url}")

            data = json.loads(raw)
            video_detail = data.get("__DEFAULT_SCOPE__", {}).get("webapp.video-detail")
            if video_detail is None:
                raise TikTokImportNotFoundError(
                    f"TikTok returned a page for {url} with no post data - "
                    "removed, private, or region-restricted"
                )
            item = video_detail.get("itemInfo", {}).get("itemStruct")
            if not item:
                raise TikTokImportNotFoundError(f"No item data found for {url}")
            return item
        finally:
            page.close()

    raise TikTokImportBlockedError(
        f"TikTok's anti-bot challenge blocked every attempt ({MAX_ATTEMPTS}) for {url}"
    )


def _download_images(
    browser: Browser, item: dict, now: datetime
) -> tuple[list[MarketingCreative], int, list[dict]]:
    """
    Returns (media_assets, downloaded_count, failed_assets) - never
    raises on an individual image's failure (the Critical TikTok
    Slideshow Import Fix, see MIGRATION_PLAN.md: silently `continue`-ing
    past a bad image is exactly how a 4-image post used to become a
    clean 1-image success). Every dropped index is recorded with why, so
    the caller's integrity gate can tell "this import is genuinely
    incomplete" from "everything downloaded fine." Only a total,
    zero-survivors failure still raises directly - a real, distinct
    condition (see below), not the same thing as a partial miss.
    """
    image_post = item.get("imagePost")
    if not image_post:
        raise TikTokImportUnsupportedContentError(
            f"TikTok post {item.get('id')} is a video, not a photo-mode slideshow - "
            "see PlaywrightTikTokImporter's module docstring for why this is rejected, "
            "not silently imported"
        )

    images = image_post.get("images", [])
    if not images:
        raise TikTokImportNotFoundError(f"TikTok photo post {item.get('id')} had no images")

    page = browser.new_page(user_agent=USER_AGENT)
    try:
        request = page.context.request
        media_assets: list[MarketingCreative] = []
        failed_assets: list[dict] = []
        downloaded_count = 0
        for index, image in enumerate(images):
            url_list = image.get("imageURL", {}).get("urlList", [])
            if not url_list:
                failed_assets.append({"index": index, "reason": "no downloadable URL for this slide"})
                continue
            image_url = url_list[0]
            # SSRF hardening (Phase 0, WP-0C): these URLs come from
            # TikTok's own JSON response, not from us - second-order
            # input. Validated against the evidenced CDN allowlist.
            # Deliberately fails this ONE slide rather than the whole
            # import, and names the rejected host so a genuinely new
            # TikTok CDN domain can be evidenced and added rather than
            # guessed at in advance (see safe_fetch's allowlist comment).
            try:
                validate_tiktok_url(image_url)
            except UnsafeURLError as exc:
                failed_assets.append({"index": index, "reason": f"blocked by URL policy: {exc}"})
                continue
            response = request.get(image_url, headers={"Referer": REFERER})
            if not response.ok:
                failed_assets.append({"index": index, "reason": f"HTTP {response.status}"})
                continue
            downloaded_count += 1
            body = response.body()
            # This importer used to trust any HTTP-200 body as a valid
            # image with zero verification - unlike DownieImporter, which
            # already PIL-validates. A "downloaded but not a real image"
            # slide is a genuinely different failure from "never
            # downloaded at all", and the integrity gate's
            # slides_downloaded/slides_validated distinction only means
            # anything if this importer can actually produce a case where
            # they differ.
            try:
                Image.open(BytesIO(body)).load()
            except UnidentifiedImageError:
                failed_assets.append({"index": index, "reason": "downloaded bytes are not a valid image"})
                continue
            media_assets.append(
                MarketingCreative(
                    image_bytes=body,
                    original_filename=f"tiktok_{item.get('id')}_{index}.jpeg",
                    source_type="tiktok",
                    source_locator=image_url,
                    imported_at=now,
                    raw_metadata={"index": index},
                )
            )
        if not media_assets:
            raise TikTokImportNotFoundError(
                f"TikTok photo post {item.get('id')} had no downloadable images"
            )
        return media_assets, downloaded_count, failed_assets
    finally:
        page.close()


class PlaywrightTikTokImporter:
    """source_config shape: {"url": "<a TikTok post URL>"}."""

    def import_source(self, source_config: dict) -> EvidencePackage:
        now = datetime.now(timezone.utc)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=STEALTH_ARGS)
            try:
                url = _canonical_post_url(browser, source_config["url"])
                item = _fetch_item_struct(browser, url)
                media_assets, downloaded_count, failed_assets = _download_images(browser, item, now)
            finally:
                browser.close()

        image_post = item.get("imagePost") or {}
        expected_count = len(image_post.get("images", []))

        return EvidencePackage(
            source_platform="tiktok",
            media_assets=media_assets,
            original_url=url,
            creator=_creator_from_item(item),
            caption=item.get("desc") or None,
            hashtags=[c["title"] for c in item.get("challenges", []) if c.get("title")],
            product_references=[],
            platform_metadata={"item_id": item.get("id")},
            imported_at=now,
            raw=item,
            expected_count=expected_count,
            downloaded_count=downloaded_count,
            failed_assets=failed_assets,
        )
