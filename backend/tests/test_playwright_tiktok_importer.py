"""
Tests for PlaywrightTikTokImporter (Phase 10.6 of AI Creative Engine
vNext, see MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §5a).

Fakes Playwright's sync API entirely - real browser behavior (the anti-
bot challenge, the real imagePost/video JSON shapes, the session-bound
signed-URL download requirement) was verified directly against live
TikTok URLs during this phase's implementation (see that phase's report
in MIGRATION_PLAN.md), not re-asserted here. These tests exercise this
module's own logic - URL normalization, retry-then-fail-cleanly on a
block, the imagePost/video branch, error mapping - deterministically.
"""

import json
from types import SimpleNamespace

import pytest

from app.domain import EvidencePackage
from app.importers.playwright_tiktok import (
    PlaywrightTikTokImporter,
    TikTokImportBlockedError,
    TikTokImportNotFoundError,
    TikTokImportUnsupportedContentError,
    _creator_from_item,
    _normalize_post_url,
)


class _FakeDownloadResponse:
    def __init__(self, status: int, content: bytes):
        self.status = status
        self.ok = 200 <= status < 300
        self._content = content

    def body(self) -> bytes:
        return self._content


class _FakePage:
    def __init__(self, body_text: str, rehydration_data: dict | None, downloads: dict[str, bytes]):
        self._body_text = body_text
        self._rehydration_data = rehydration_data
        self.context = SimpleNamespace(request=SimpleNamespace(get=self._get))
        self._downloads = downloads

    def add_init_script(self, script: str) -> None:
        pass

    def goto(self, url: str, wait_until: str | None = None, timeout: int | None = None) -> None:
        pass

    def inner_text(self, selector: str) -> str:
        return self._body_text

    def eval_on_selector(self, selector: str, script: str) -> str | None:
        if self._rehydration_data is None:
            return None
        return json.dumps(self._rehydration_data)

    def close(self) -> None:
        pass

    def _get(self, url: str, headers: dict | None = None) -> _FakeDownloadResponse:
        if url not in self._downloads:
            return _FakeDownloadResponse(404, b"")
        return _FakeDownloadResponse(200, self._downloads[url])


class _FakeBrowser:
    def __init__(self, pages: list[_FakePage]):
        self._pages = list(pages)

    def new_page(self, user_agent: str | None = None) -> _FakePage:
        return self._pages.pop(0)

    def close(self) -> None:
        pass


def _install_fake_playwright(monkeypatch, browser: _FakeBrowser) -> None:
    class _FakePlaywrightContext:
        def __enter__(self):
            return SimpleNamespace(chromium=SimpleNamespace(launch=lambda headless, args: browser))

        def __exit__(self, *exc_info):
            return False

    monkeypatch.setattr(
        "app.importers.playwright_tiktok.sync_playwright", lambda: _FakePlaywrightContext()
    )


def _rehydration(item: dict) -> dict:
    return {"__DEFAULT_SCOPE__": {"webapp.video-detail": {"itemInfo": {"itemStruct": item}}}}


def _image_post_item(**overrides) -> dict:
    item = {
        "id": "7000000000000000001",
        "desc": "check this out #widgets #deal",
        "author": {"uniqueId": "someone", "nickname": "Someone"},
        "challenges": [{"title": "widgets"}, {"title": "deal"}],
        "imagePost": {
            "images": [
                {"imageURL": {"urlList": ["https://cdn.example/img0.jpeg"]}},
                {"imageURL": {"urlList": ["https://cdn.example/img1.jpeg"]}},
            ]
        },
    }
    item.update(overrides)
    return item


def test_normalize_post_url_rewrites_photo_to_video():
    assert (
        _normalize_post_url("https://www.tiktok.com/@someone/photo/123")
        == "https://www.tiktok.com/@someone/video/123"
    )


def test_normalize_post_url_leaves_video_url_equivalent():
    assert (
        _normalize_post_url("https://www.tiktok.com/@someone/video/123")
        == "https://www.tiktok.com/@someone/video/123"
    )


def test_normalize_post_url_rejects_unrecognizable_url():
    with pytest.raises(TikTokImportNotFoundError):
        _normalize_post_url("https://www.tiktok.com/discover/some-tag")


def test_creator_from_item_builds_handle_and_profile_url():
    creator = _creator_from_item({"author": {"uniqueId": "someone", "nickname": "Someone"}})
    assert creator.handle == "@someone"
    assert creator.display_name == "Someone"
    assert creator.profile_url == "https://www.tiktok.com/@someone"


def test_creator_from_item_returns_none_with_no_author():
    assert _creator_from_item({}) is None


def test_import_source_builds_evidence_package_from_a_real_image_post(monkeypatch):
    item = _image_post_item()
    downloads = {
        "https://cdn.example/img0.jpeg": b"first-image-bytes",
        "https://cdn.example/img1.jpeg": b"second-image-bytes",
    }
    fetch_page = _FakePage(body_text="ok", rehydration_data=_rehydration(item), downloads={})
    download_page = _FakePage(body_text="ok", rehydration_data=None, downloads=downloads)
    _install_fake_playwright(monkeypatch, _FakeBrowser([fetch_page, download_page]))

    package = PlaywrightTikTokImporter().import_source({"url": "https://www.tiktok.com/@someone/video/1"})

    assert isinstance(package, EvidencePackage)
    assert package.source_platform == "tiktok"
    assert package.creator.handle == "@someone"
    assert package.caption == "check this out #widgets #deal"
    assert package.hashtags == ["widgets", "deal"]
    assert package.product_references == []
    assert package.platform_metadata == {"item_id": "7000000000000000001"}
    assert [m.image_bytes for m in package.media_assets] == [b"first-image-bytes", b"second-image-bytes"]
    assert [m.source_type for m in package.media_assets] == ["tiktok", "tiktok"]


def test_import_source_normalizes_photo_url_before_fetching(monkeypatch):
    item = _image_post_item()
    downloads = {"https://cdn.example/img0.jpeg": b"a", "https://cdn.example/img1.jpeg": b"b"}
    fetch_page = _FakePage(body_text="ok", rehydration_data=_rehydration(item), downloads={})
    download_page = _FakePage(body_text="ok", rehydration_data=None, downloads=downloads)
    _install_fake_playwright(monkeypatch, _FakeBrowser([fetch_page, download_page]))

    package = PlaywrightTikTokImporter().import_source(
        {"url": "https://www.tiktok.com/@someone/photo/7000000000000000001"}
    )

    assert package.original_url == "https://www.tiktok.com/@someone/video/7000000000000000001"


def test_import_source_rejects_a_video_only_post(monkeypatch):
    item = {"id": "1", "desc": "", "author": {}, "challenges": [], "video": {"playAddr": "https://cdn/x.mp4"}}
    fetch_page = _FakePage(body_text="ok", rehydration_data=_rehydration(item), downloads={})
    _install_fake_playwright(monkeypatch, _FakeBrowser([fetch_page]))

    with pytest.raises(TikTokImportUnsupportedContentError):
        PlaywrightTikTokImporter().import_source({"url": "https://www.tiktok.com/@someone/video/1"})


def test_import_source_retries_then_raises_when_blocked_every_attempt(monkeypatch):
    blocked_pages = [
        _FakePage(body_text="Drag the slider to fit the puzzle", rehydration_data=None, downloads={})
        for _ in range(3)
    ]
    _install_fake_playwright(monkeypatch, _FakeBrowser(blocked_pages))

    with pytest.raises(TikTokImportBlockedError):
        PlaywrightTikTokImporter().import_source({"url": "https://www.tiktok.com/@someone/video/1"})


def test_import_source_succeeds_after_one_blocked_attempt(monkeypatch):
    item = _image_post_item()
    downloads = {"https://cdn.example/img0.jpeg": b"a", "https://cdn.example/img1.jpeg": b"b"}
    pages = [
        _FakePage(body_text="Drag the slider to fit the puzzle", rehydration_data=None, downloads={}),
        _FakePage(body_text="ok", rehydration_data=_rehydration(item), downloads={}),
        _FakePage(body_text="ok", rehydration_data=None, downloads=downloads),
    ]
    _install_fake_playwright(monkeypatch, _FakeBrowser(pages))

    package = PlaywrightTikTokImporter().import_source({"url": "https://www.tiktok.com/@someone/video/1"})
    assert len(package.media_assets) == 2


def test_import_source_raises_not_found_when_post_has_no_data(monkeypatch):
    no_post_data = {"__DEFAULT_SCOPE__": {"webapp.app-context": {}}}
    fetch_page = _FakePage(body_text="ok", rehydration_data=no_post_data, downloads={})
    _install_fake_playwright(monkeypatch, _FakeBrowser([fetch_page]))

    with pytest.raises(TikTokImportNotFoundError):
        PlaywrightTikTokImporter().import_source({"url": "https://www.tiktok.com/@someone/video/1"})


def test_import_source_raises_not_found_on_download_failure(monkeypatch):
    item = _image_post_item()
    fetch_page = _FakePage(body_text="ok", rehydration_data=_rehydration(item), downloads={})
    download_page = _FakePage(body_text="ok", rehydration_data=None, downloads={})  # nothing downloadable
    _install_fake_playwright(monkeypatch, _FakeBrowser([fetch_page, download_page]))

    with pytest.raises(TikTokImportNotFoundError):
        PlaywrightTikTokImporter().import_source({"url": "https://www.tiktok.com/@someone/video/1"})
