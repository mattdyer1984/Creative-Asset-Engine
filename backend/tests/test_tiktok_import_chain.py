"""
Tests for the TikTok import orchestrator (Critical TikTok Slideshow
Import Fix, see MIGRATION_PLAN.md) - app.services.tiktok_import_chain.
Fakes detect_tiktok_content and get_importer entirely (both already
have their own real, live-verified coverage in
test_playwright_tiktok_importer.py/test_downie_importer.py) - these
tests exercise this module's own orchestration logic: provider order,
fallback triggers, the integrity gate wiring, enrichment, and error
mapping, deterministically.
"""

from datetime import datetime, timezone

import pytest

from app.domain import EvidencePackage, MarketingCreative
from app.importers.downie import DownieImportUnavailableError
from app.importers.playwright_tiktok import TikTokContentInfo, TikTokImportUnsupportedContentError
from app.services import tiktok_import_chain as chain_module
from app.services.tiktok_import_chain import ImportIncompleteError, import_tiktok_url


def _asset(index: int) -> MarketingCreative:
    return MarketingCreative(
        image_bytes=f"bytes-{index}".encode(),
        original_filename=f"slide_{index}.jpg",
        source_type="tiktok",
        source_locator=f"https://cdn.example/{index}.jpg",
        imported_at=datetime.now(timezone.utc),
        raw_metadata={"index": index},
    )


def _complete_package(source_platform: str, count: int, **overrides) -> EvidencePackage:
    defaults = dict(
        source_platform=source_platform,
        media_assets=[_asset(i) for i in range(count)],
        downloaded_count=count,
        failed_assets=[],
    )
    defaults.update(overrides)
    return EvidencePackage(**defaults)


def _incomplete_package(source_platform: str, count: int) -> EvidencePackage:
    return EvidencePackage(
        source_platform=source_platform,
        media_assets=[_asset(i) for i in range(count)],
        downloaded_count=count,
        failed_assets=[{"index": count, "reason": "did not download"}],
    )


class _FakeImporter:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error
        self.calls: list[dict] = []

    def import_source(self, source_config: dict) -> EvidencePackage:
        self.calls.append(source_config)
        if self._error is not None:
            raise self._error
        return self._result


def _install(monkeypatch, content_info, importers: dict):
    monkeypatch.setattr(chain_module, "detect_tiktok_content", lambda url: content_info)
    monkeypatch.setattr(chain_module, "get_importer", lambda name: importers[name])


_SLIDESHOW_ITEM = {
    "id": "1",
    "desc": "real caption",
    "author": {"uniqueId": "someone", "nickname": "Someone"},
    "challenges": [{"title": "deal"}],
}


def _content_info(count: int) -> TikTokContentInfo:
    return TikTokContentInfo(content_type="slideshow", expected_slide_count=count, item=_SLIDESHOW_ITEM)


def test_auto_mode_succeeds_via_downie_without_calling_tiktok(monkeypatch, db_session):
    downie = _FakeImporter(result=_complete_package("downie", 4))
    tiktok = _FakeImporter(result=_complete_package("tiktok", 4))
    _install(monkeypatch, _content_info(4), {"downie": downie, "tiktok": tiktok})

    slideshows = import_tiktok_url(db_session, "https://www.tiktok.com/@x/video/1", None, provider="auto")

    assert len(slideshows) == 1
    assert len(slideshows[0].slides) == 4
    assert tiktok.calls == []  # never invoked - Downie already succeeded


def test_downie_win_is_enriched_with_the_detected_items_real_metadata(monkeypatch, db_session):
    downie = _FakeImporter(result=_complete_package("downie", 2))
    _install(monkeypatch, _content_info(2), {"downie": downie, "tiktok": _FakeImporter()})

    slideshows = import_tiktok_url(db_session, "https://www.tiktok.com/@x/video/1", None, provider="auto")

    from app.models.evidence_source import EvidenceSource

    evidence_source = db_session.get(EvidenceSource, slideshows[0].evidence_source_id)
    assert evidence_source.caption == "real caption"
    assert evidence_source.creator_json["handle"] == "@someone"


def test_auto_mode_falls_back_to_tiktok_when_downie_unavailable(monkeypatch, db_session):
    downie = _FakeImporter(error=DownieImportUnavailableError("not installed"))
    tiktok = _FakeImporter(result=_complete_package("tiktok", 3))
    _install(monkeypatch, _content_info(3), {"downie": downie, "tiktok": tiktok})

    slideshows = import_tiktok_url(db_session, "https://www.tiktok.com/@x/video/1", None, provider="auto")

    assert len(slideshows) == 1
    assert len(slideshows[0].slides) == 3
    assert len(tiktok.calls) == 1


def test_auto_mode_falls_back_to_tiktok_when_downie_is_incomplete(monkeypatch, db_session):
    downie = _FakeImporter(result=_incomplete_package("downie", 1))
    tiktok = _FakeImporter(result=_complete_package("tiktok", 4))
    _install(monkeypatch, _content_info(4), {"downie": downie, "tiktok": tiktok})

    slideshows = import_tiktok_url(db_session, "https://www.tiktok.com/@x/video/1", None, provider="auto")

    assert len(slideshows[0].slides) == 4


def test_auto_mode_raises_incomplete_when_both_providers_fail_the_gate(monkeypatch, db_session):
    downie = _FakeImporter(result=_incomplete_package("downie", 1))
    tiktok = _FakeImporter(result=_incomplete_package("tiktok", 2))
    _install(monkeypatch, _content_info(4), {"downie": downie, "tiktok": tiktok})

    with pytest.raises(ImportIncompleteError) as exc_info:
        import_tiktok_url(db_session, "https://www.tiktok.com/@x/video/1", None, provider="auto")

    assert str(exc_info.value) == "Slideshow import incomplete: expected 4 slides, downloaded 2."


def test_video_post_is_rejected_before_either_provider_is_invoked(monkeypatch, db_session):
    downie = _FakeImporter(result=_complete_package("downie", 1))
    tiktok = _FakeImporter(result=_complete_package("tiktok", 1))
    video_info = TikTokContentInfo(content_type="video", expected_slide_count=0, item={"id": "1"})
    _install(monkeypatch, video_info, {"downie": downie, "tiktok": tiktok})

    with pytest.raises(TikTokImportUnsupportedContentError):
        import_tiktok_url(db_session, "https://www.tiktok.com/@x/video/1", None, provider="auto")

    assert downie.calls == []
    assert tiktok.calls == []


def test_forced_tiktok_provider_never_tries_downie(monkeypatch, db_session):
    downie = _FakeImporter(result=_complete_package("downie", 4))
    tiktok = _FakeImporter(result=_complete_package("tiktok", 4))
    _install(monkeypatch, _content_info(4), {"downie": downie, "tiktok": tiktok})

    import_tiktok_url(db_session, "https://www.tiktok.com/@x/video/1", None, provider="tiktok")

    assert downie.calls == []
    assert len(tiktok.calls) == 1


def test_forced_tiktok_provider_raises_incomplete_with_no_fallback(monkeypatch, db_session):
    downie = _FakeImporter(result=_complete_package("downie", 4))
    tiktok = _FakeImporter(result=_incomplete_package("tiktok", 1))
    _install(monkeypatch, _content_info(4), {"downie": downie, "tiktok": tiktok})

    with pytest.raises(ImportIncompleteError) as exc_info:
        import_tiktok_url(db_session, "https://www.tiktok.com/@x/video/1", None, provider="tiktok")

    assert str(exc_info.value) == "Slideshow import incomplete: expected 4 slides, downloaded 1."
    assert downie.calls == []


def test_forced_downie_provider_never_tries_tiktok_and_propagates_its_own_errors(monkeypatch, db_session):
    downie = _FakeImporter(error=DownieImportUnavailableError("not installed"))
    tiktok = _FakeImporter(result=_complete_package("tiktok", 4))
    _install(monkeypatch, _content_info(4), {"downie": downie, "tiktok": tiktok})

    with pytest.raises(DownieImportUnavailableError):
        import_tiktok_url(db_session, "https://www.tiktok.com/@x/video/1", None, provider="downie")

    assert tiktok.calls == []


def test_downie_source_config_carries_the_detected_expected_count(monkeypatch, db_session):
    downie = _FakeImporter(result=_complete_package("downie", 4))
    _install(monkeypatch, _content_info(4), {"downie": downie, "tiktok": _FakeImporter()})

    import_tiktok_url(db_session, "https://www.tiktok.com/@x/video/1", None, provider="auto")

    assert downie.calls[0]["expected_count"] == 4
