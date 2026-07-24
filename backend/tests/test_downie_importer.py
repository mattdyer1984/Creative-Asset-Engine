"""
Tests for DownieImporter (Phase 10.6b of AI Creative Engine vNext, see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §5a).

Fakes subprocess.run entirely - the real `downie://XUOpenURL` trigger,
its `destination`/`title` parameter grammar, and the real 8-image
TikTok-slideshow download it produced were verified directly against
the real, licensed Downie 4 app during this phase's implementation (see
that phase's report in MIGRATION_PLAN.md), not re-asserted here. These
tests exercise this module's own logic - completion-detection polling
(stable size, `.downiepart` skipping, timeout), sort-by-index ordering,
the image-only content boundary, scratch-dir cleanup, and error mapping
- deterministically and fast, by having the fake `subprocess.run` write
files into the real (per-test, tmp_path-backed) scratch directory
synchronously rather than waiting on a real download.
"""

import io
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from PIL import Image

from app.domain import EvidencePackage
from app.importers import downie as downie_module
from app.importers.downie import (
    DownieImporter,
    DownieImportTimeoutError,
    DownieImportUnavailableError,
    DownieImportUnsupportedContentError,
)
from app.importers.registry import get_importer


def _real_jpeg_bytes(color=(200, 50, 50)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), color).save(buf, format="JPEG")
    return buf.getvalue()


def _destination_from_downie_url(downie_url: str) -> tuple[Path, str]:
    query = parse_qs(urlparse(downie_url).query)
    return Path(query["destination"][0]), query["title"][0]


@pytest.fixture(autouse=True)
def _fast_polling(monkeypatch):
    monkeypatch.setattr(downie_module, "POLL_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(downie_module, "MAX_WAIT_SECONDS", 0.5)


@pytest.fixture(autouse=True)
def _downie_installed(monkeypatch):
    monkeypatch.setattr(downie_module, "DOWNIE_APP_PATH", Path("/"))  # always exists


def _writes_files(files_by_suffix: dict[str, bytes]):
    """Fake subprocess.run: writes the given {name_suffix: content} files into the real destination folder."""

    def _fake_run(cmd, check):
        destination, title = _destination_from_downie_url(cmd[-1])
        for suffix, content in files_by_suffix.items():
            (destination / f"{title}{suffix}").write_bytes(content)
        return subprocess.CompletedProcess(cmd, 0)

    return _fake_run


def test_import_source_downloads_a_single_stable_image(monkeypatch):
    monkeypatch.setattr(
        downie_module.subprocess, "run", _writes_files({".jpg": _real_jpeg_bytes()})
    )

    package = DownieImporter().import_source({"url": "https://example.com/post/1"})

    assert isinstance(package, EvidencePackage)
    assert package.source_platform == "downie"
    assert len(package.media_assets) == 1
    assert package.media_assets[0].source_type == "downie"
    assert package.media_assets[0].source_locator == "https://example.com/post/1"


def test_import_source_sorts_multi_image_downloads_by_bracket_index(monkeypatch):
    monkeypatch.setattr(
        downie_module.subprocess,
        "run",
        _writes_files(
            {
                " [2 - 3].jpg": _real_jpeg_bytes((10, 10, 10)),
                " [1 - 3].jpg": _real_jpeg_bytes((20, 20, 20)),
                " [3 - 3].jpg": _real_jpeg_bytes((30, 30, 30)),
            }
        ),
    )

    package = DownieImporter().import_source({"url": "https://example.com/post/2"})

    assert [m.original_filename for m in package.media_assets] == sorted(
        m.original_filename for m in package.media_assets
    )
    assert "[1 - 3]" in package.media_assets[0].original_filename
    assert "[2 - 3]" in package.media_assets[1].original_filename
    assert "[3 - 3]" in package.media_assets[2].original_filename


def test_import_source_skips_non_image_files_among_real_ones(monkeypatch):
    monkeypatch.setattr(
        downie_module.subprocess,
        "run",
        _writes_files({".jpg": _real_jpeg_bytes(), ".mp4": b"not a real video, just garbage bytes"}),
    )

    package = DownieImporter().import_source({"url": "https://example.com/post/3"})

    assert len(package.media_assets) == 1
    assert package.media_assets[0].original_filename.endswith(".jpg")


def test_import_source_raises_unsupported_when_nothing_downloaded_is_an_image(monkeypatch):
    monkeypatch.setattr(
        downie_module.subprocess, "run", _writes_files({".mp4": b"not a real video, just garbage bytes"})
    )

    with pytest.raises(DownieImportUnsupportedContentError):
        DownieImporter().import_source({"url": "https://example.com/video-only"})


def test_import_source_raises_timeout_when_nothing_appears(monkeypatch):
    monkeypatch.setattr(downie_module.subprocess, "run", lambda cmd, check: subprocess.CompletedProcess(cmd, 0))

    with pytest.raises(DownieImportTimeoutError):
        DownieImporter().import_source({"url": "https://example.com/nothing"})


def test_import_source_raises_unavailable_when_downie_not_installed(monkeypatch):
    monkeypatch.setattr(downie_module, "DOWNIE_APP_PATH", Path("/definitely/does/not/exist/Downie 4.app"))

    def _fail_if_called(cmd, check):
        raise AssertionError("subprocess.run should never be called when Downie isn't installed")

    monkeypatch.setattr(downie_module.subprocess, "run", _fail_if_called)

    with pytest.raises(DownieImportUnavailableError):
        DownieImporter().import_source({"url": "https://example.com/post/4"})


def test_import_source_cleans_up_scratch_dir_on_success(monkeypatch):
    scratch_dirs = []
    fake_write = _writes_files({".jpg": _real_jpeg_bytes()})

    def _run_and_record(cmd, check):
        destination, _title = _destination_from_downie_url(cmd[-1])
        scratch_dirs.append(destination)
        return fake_write(cmd, check)

    monkeypatch.setattr(downie_module.subprocess, "run", _run_and_record)

    DownieImporter().import_source({"url": "https://example.com/post/5"})

    assert not scratch_dirs[0].exists()


def test_import_source_cleans_up_scratch_dir_on_failure(monkeypatch):
    scratch_dirs = []

    def _run_and_record(cmd, check):
        destination, _title = _destination_from_downie_url(cmd[-1])
        scratch_dirs.append(destination)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(downie_module.subprocess, "run", _run_and_record)

    with pytest.raises(DownieImportTimeoutError):
        DownieImporter().import_source({"url": "https://example.com/post/6"})

    assert not scratch_dirs[0].exists()


def test_import_source_evidence_package_has_no_platform_metadata_downie_cannot_provide(monkeypatch):
    monkeypatch.setattr(downie_module.subprocess, "run", _writes_files({".jpg": _real_jpeg_bytes()}))

    package = DownieImporter().import_source({"url": "https://example.com/post/7"})

    assert package.creator is None
    assert package.caption is None
    assert package.hashtags == []
    assert package.product_references == []


def test_import_source_treats_downiepart_as_in_progress_not_done(monkeypatch):
    monkeypatch.setattr(
        downie_module.subprocess, "run", _writes_files({".jpg.downiepart": _real_jpeg_bytes()})
    )

    with pytest.raises(DownieImportTimeoutError):
        DownieImporter().import_source({"url": "https://example.com/still-downloading"})


def test_downie_registered_in_importer_registry():
    assert isinstance(get_importer("downie"), DownieImporter)


# --- Critical TikTok Slideshow Import Fix (see MIGRATION_PLAN.md) -------
#
# The real bug: _wait_for_stable_download used to trust a stable
# snapshot the instant it saw one, with no idea how many files a
# slideshow *should* eventually produce - if file 1 landed before files
# 2-4 even existed as .downiepart placeholders, it would see a stable
# 1-file snapshot and return early. The existing _writes_files fake
# above can't express this (it writes every file synchronously inside
# one subprocess.run call, before polling even starts) - these tests
# instead monkeypatch time.sleep to drop the remaining files into the
# real scratch dir partway through polling, then call through to the
# real (fast, _fast_polling-fixture) sleep.


def _staggered_write(scratch_dir_holder: dict, first: dict[str, bytes], rest: dict[str, bytes], after_calls: int):
    """
    Fake subprocess.run writes `first` immediately (as Downie's very
    first file would land); a monkeypatched time.sleep writes `rest`
    only after being called `after_calls` times - simulating files 2-4
    appearing only after a couple of poll cycles have already run.
    """
    calls = {"n": 0}

    def _fake_run(cmd, check):
        destination, title = _destination_from_downie_url(cmd[-1])
        scratch_dir_holder["path"] = destination
        scratch_dir_holder["title"] = title
        for suffix, content in first.items():
            (destination / f"{title}{suffix}").write_bytes(content)
        return subprocess.CompletedProcess(cmd, 0)

    real_sleep = downie_module.time.sleep

    def _fake_sleep(seconds):
        calls["n"] += 1
        if calls["n"] == after_calls and "path" in scratch_dir_holder:
            destination = scratch_dir_holder["path"]
            title = scratch_dir_holder["title"]
            for suffix, content in rest.items():
                (destination / f"{title}{suffix}").write_bytes(content)
        real_sleep(seconds)

    return _fake_run, _fake_sleep


def test_expected_count_none_returns_early_on_a_stable_but_incomplete_snapshot(monkeypatch):
    """
    Documents the real, original bug as a still-correct legacy case:
    with no expected_count (the only mode this importer had before this
    fix), a stable 1-file snapshot is trusted immediately even though 3
    more files are about to appear - exactly the race that produced a
    real 4-image TikTok slideshow silently importing as 1 image.
    """
    holder = {}
    fake_run, fake_sleep = _staggered_write(
        holder,
        first={" [1 - 4].jpg": _real_jpeg_bytes((1, 1, 1))},
        rest={
            " [2 - 4].jpg": _real_jpeg_bytes((2, 2, 2)),
            " [3 - 4].jpg": _real_jpeg_bytes((3, 3, 3)),
            " [4 - 4].jpg": _real_jpeg_bytes((4, 4, 4)),
        },
        after_calls=3,
    )
    monkeypatch.setattr(downie_module.subprocess, "run", fake_run)
    monkeypatch.setattr(downie_module.time, "sleep", fake_sleep)

    package = DownieImporter().import_source({"url": "https://example.com/staggered"})

    assert len(package.media_assets) == 1


def test_expected_count_waits_for_every_file_before_returning(monkeypatch):
    """The fix: with expected_count given, the same staggered write now correctly waits for all 4 files."""
    holder = {}
    fake_run, fake_sleep = _staggered_write(
        holder,
        first={" [1 - 4].jpg": _real_jpeg_bytes((1, 1, 1))},
        rest={
            " [2 - 4].jpg": _real_jpeg_bytes((2, 2, 2)),
            " [3 - 4].jpg": _real_jpeg_bytes((3, 3, 3)),
            " [4 - 4].jpg": _real_jpeg_bytes((4, 4, 4)),
        },
        after_calls=3,
    )
    monkeypatch.setattr(downie_module.subprocess, "run", fake_run)
    monkeypatch.setattr(downie_module.time, "sleep", fake_sleep)

    package = DownieImporter().import_source({"url": "https://example.com/staggered", "expected_count": 4})

    assert len(package.media_assets) == 4
    assert package.downloaded_count == 4
    assert package.expected_count == 4


def test_marketing_creative_index_is_sorted_position_not_raw_bracket_number(monkeypatch):
    """
    Regression lock for a real off-by-one risk: Downie's own bracket
    numbering is 1-based ([1 - 3], [2 - 3], [3 - 3]); raw_metadata["index"]
    must be the 0-based *position* in the sorted list, not the raw
    capture, or the ordering-verification check downstream would fail on
    every real Downie import.
    """
    monkeypatch.setattr(
        downie_module.subprocess,
        "run",
        _writes_files(
            {
                " [2 - 3].jpg": _real_jpeg_bytes((10, 10, 10)),
                " [1 - 3].jpg": _real_jpeg_bytes((20, 20, 20)),
                " [3 - 3].jpg": _real_jpeg_bytes((30, 30, 30)),
            }
        ),
    )

    package = DownieImporter().import_source({"url": "https://example.com/post/8"})

    assert [m.raw_metadata["index"] for m in package.media_assets] == [0, 1, 2]


def test_failed_assets_and_downloaded_count_are_reported_not_silently_dropped(monkeypatch):
    monkeypatch.setattr(
        downie_module.subprocess,
        "run",
        _writes_files({".jpg": _real_jpeg_bytes(), ".mp4": b"not a real video, just garbage bytes"}),
    )

    package = DownieImporter().import_source({"url": "https://example.com/post/9"})

    assert package.downloaded_count == 2
    assert len(package.media_assets) == 1
    assert len(package.failed_assets) == 1
    assert "did not open as a real image" in package.failed_assets[0]["reason"]
