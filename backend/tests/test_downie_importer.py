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
