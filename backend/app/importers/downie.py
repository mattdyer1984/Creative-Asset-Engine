"""
DownieImporter — the documented fallback TikTok (and general-purpose)
Import Provider (Phase 10.6b of AI Creative Engine vNext, see
MIGRATION_PLAN.md's "ADR: AI Creative Engine vNext" §5a). Never the
primary path (PlaywrightTikTokImporter is, per that section) - this
exists for when TikTok's anti-bot posture blocks the native path, and
for other platforms a general-purpose downloader already covers.

source_config shape: {"url": "<any URL Downie can extract from>"}.

Trigger mechanism and parameter grammar, confirmed directly from Downie
4.12.9's own bundled help documentation (Contents/Resources/
DownieHelp.help - the app's own primary-source docs, not the secondary/
AI-summarized search results §5a's own investigation had to rely on
before this phase) - the exact gap §5a flagged as needing "a quick
empirical confirmation... before implementation relies on it":

    downie://XUOpenURL?url=<url-encoded>&destination=<path>&title=<title>

`destination` must already exist; `title` becomes the base filename
Downie writes into it. Confirmed via a real, live empirical spike this
phase (2026-07-23): triggered `open -a "Downie 4" "downie://..."`
against one of the real TikTok URLs supplied earlier this session,
pointed at a scratch folder - Downie correctly wrote every downloaded
file into exactly that folder, named `<title> [N - 8].jpg`. That real
post turned out to be a genuine 8-image photo-mode slideshow, not a
video - confirmed by opening every file with Pillow (real 1080-wide
JPEGs, not corrupted) - so completion detection below is built around
"one or more files," never "exactly one," from the start.

**Honest limitation, not glossed over**: that same spike never observed
a real `.downiepart` in-progress marker, because all 8 images were
already fully written by the first 2-second poll - too fast to catch
the transient state. The `.downiepart` check below is kept anyway
(defensive, cheap, and exactly what §5a's design calls for) since a
slower download - a real video, a large batch, a slow connection - is
exactly the case it exists for; it just wasn't exercised by this
specific spike, an honest gap in this confirmation, not a claim it
works beyond what was actually observed.

**Completion detection, per §5a's own design**: neither the URL scheme
nor Shortcuts hands back a file path or a "done" signal, so this
importer opens every request into a unique, per-request scratch folder
(never Downie's shared default download folder, to avoid disambiguation
problems under concurrent imports) and polls it until every file
present (a) doesn't end in `.downiepart` and (b) has a stable byte size
across two consecutive polls - then treats every remaining file as one
real download. A bounded timeout fails cleanly with
`DownieImportTimeoutError` rather than hanging forever.

**Scope boundary, same reasoning as PlaywrightTikTokImporter**: this
codebase's Slide-analysis pipeline opens every Slide with
`PIL.Image.open()` directly - it has no video-decoding capability
anywhere. Any downloaded file that doesn't open as a real image is
dropped; if every file in the batch turns out to be one (a video-only
download), `DownieImportUnsupportedContentError` is raised rather than
silently shipping unreadable bytes downstream.

**What Downie's own automation surface cannot provide, left honestly
empty rather than guessed**: creator, caption, hashtags, and platform-
native product tags - none of that exists anywhere in Downie's
automation surface, only raw downloaded media. This is a real, concrete
reason the native importer is the better default (per §5a) - Downie can
hand back pixels, never the richer EvidencePackage provenance the
native path already provides.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from PIL import Image, UnidentifiedImageError

from app.config import settings
from app.domain import EvidencePackage, MarketingCreative

DOWNIE_APP_NAME = "Downie 4"
DOWNIE_APP_PATH = Path("/Applications/Downie 4.app")
POLL_INTERVAL_SECONDS = 2.0
MAX_WAIT_SECONDS = 90.0

_INDEX_RE = re.compile(r"\[(\d+)\s*-\s*\d+\]")


class DownieImportError(Exception):
    """Base for every real failure this importer can raise - never a silent empty EvidencePackage."""


class DownieImportUnavailableError(DownieImportError):
    """Downie 4 isn't installed on this machine - this importer is deliberately local/macOS-only glue."""


class DownieImportTimeoutError(DownieImportError):
    """No stable, complete download appeared in the scratch folder within the timeout."""


class DownieImportUnsupportedContentError(DownieImportError):
    """Every downloaded file failed to open as a real image (e.g. a video-only download) - see module docstring."""


def _build_downie_url(source_url: str, destination: Path, title: str) -> str:
    return (
        "downie://XUOpenURL"
        f"?url={quote(source_url, safe='')}"
        f"&destination={quote(str(destination), safe='')}"
        f"&title={quote(title, safe='')}"
    )


def _sort_key(path: Path) -> tuple[int, str]:
    match = _INDEX_RE.search(path.name)
    return (int(match.group(1)) if match else 0, path.name)


def _wait_for_stable_download(scratch_dir: Path, deadline: float) -> list[Path]:
    previous_snapshot: dict[str, int] | None = None
    while True:
        files = [p for p in scratch_dir.iterdir() if p.is_file()]
        in_progress = any(p.name.endswith(".downiepart") for p in files)
        complete_files = [p for p in files if not p.name.endswith(".downiepart")]
        snapshot = {p.name: p.stat().st_size for p in complete_files}

        if complete_files and not in_progress and snapshot == previous_snapshot:
            return sorted(complete_files, key=_sort_key)

        if time.monotonic() >= deadline:
            raise DownieImportTimeoutError(
                f"No stable download appeared in {scratch_dir} within {MAX_WAIT_SECONDS}s "
                f"(found {len(files)} file(s), {'still writing' if in_progress else 'not yet stable'})"
            )

        previous_snapshot = snapshot
        time.sleep(POLL_INTERVAL_SECONDS)


def _as_marketing_creatives(files: list[Path], url: str, now: datetime) -> list[MarketingCreative]:
    media_assets = []
    for path in files:
        data = path.read_bytes()
        try:
            Image.open(BytesIO(data)).load()
        except UnidentifiedImageError:
            continue
        media_assets.append(
            MarketingCreative(
                image_bytes=data,
                original_filename=path.name,
                source_type="downie",
                source_locator=url,
                imported_at=now,
                raw_metadata={"downloaded_filename": path.name},
            )
        )
    return media_assets


class DownieImporter:
    """source_config shape: {"url": "<any URL Downie can extract from>"}."""

    def import_source(self, source_config: dict) -> EvidencePackage:
        if not DOWNIE_APP_PATH.exists():
            raise DownieImportUnavailableError(
                f"{DOWNIE_APP_NAME} is not installed at {DOWNIE_APP_PATH} - "
                "DownieImporter is local/macOS-only glue, only usable on a machine with a "
                "real, licensed Downie 4 copy"
            )

        url = source_config["url"]
        now = datetime.now(timezone.utc)
        request_id = uuid.uuid4().hex
        title = f"downie_import_{request_id}"
        scratch_dir = settings.storage_dir / "downie_scratch" / request_id
        scratch_dir.mkdir(parents=True, exist_ok=True)

        try:
            downie_url = _build_downie_url(url, scratch_dir, title)
            try:
                subprocess.run(["open", "-a", DOWNIE_APP_NAME, downie_url], check=True)
            except subprocess.CalledProcessError as exc:
                raise DownieImportError(f"Failed to open {DOWNIE_APP_NAME} for {url}: {exc}") from exc

            deadline = time.monotonic() + MAX_WAIT_SECONDS
            files = _wait_for_stable_download(scratch_dir, deadline)

            media_assets = _as_marketing_creatives(files, url, now)
            if not media_assets:
                raise DownieImportUnsupportedContentError(
                    f"Downie downloaded {len(files)} file(s) for {url}, but none of them "
                    "opened as a real image - likely a video-only download, which this "
                    "pipeline's Slide-analysis stages cannot read (see module docstring)"
                )

            return EvidencePackage(
                source_platform="downie",
                media_assets=media_assets,
                original_url=url,
                creator=None,
                caption=None,
                hashtags=[],
                product_references=[],
                platform_metadata={"title": title, "triggered_via": "downie://XUOpenURL"},
                imported_at=now,
                raw={},
            )
        finally:
            shutil.rmtree(scratch_dir, ignore_errors=True)
