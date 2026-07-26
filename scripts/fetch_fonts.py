"""
Install the redistributable font set (P2).

Rendering must not depend on which machine drew it. Every face here is
SIL Open Font License 1.1, redistributable, and pinned by SHA-256 - a font
fetched over the network without a checksum is an unverified binary that
gets loaded into the renderer.

Run once per environment, or bake into the container image:

    python scripts/fetch_fonts.py

Offline installs: download the files by hand into `backend/assets/fonts/`
and re-run to verify the checksums.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys
import urllib.request

FONT_DIR = pathlib.Path(__file__).resolve().parents[1] / "backend" / "assets" / "fonts"

#: filename -> (url, sha256). Checksums must be filled in from a verified
#: download before this script will install anything - see `--record`.
#: A blank checksum FAILS rather than installs, so an unverified binary
#: cannot reach the renderer by default.
FONTS: dict[str, tuple[str, str]] = {
    "SourceSerif4-Regular.ttf": (
        "https://github.com/adobe-fonts/source-serif/releases/download/4.005R/"
        "source-serif-4.005R.zip#SourceSerif4-Regular.ttf", ""),
    "SourceSerif4-Italic.ttf": (
        "https://github.com/adobe-fonts/source-serif/releases/download/4.005R/"
        "source-serif-4.005R.zip#SourceSerif4-It.ttf", ""),
    "SourceSerif4-Bold.ttf": (
        "https://github.com/adobe-fonts/source-serif/releases/download/4.005R/"
        "source-serif-4.005R.zip#SourceSerif4-Bold.ttf", ""),
    "Inter-Regular.ttf": ("https://github.com/rsms/inter/releases/latest", ""),
    "Inter-Bold.ttf": ("https://github.com/rsms/inter/releases/latest", ""),
    "Poppins-Regular.ttf": ("https://fonts.google.com/specimen/Poppins", ""),
    "Poppins-Bold.ttf": ("https://fonts.google.com/specimen/Poppins", ""),
    "Oswald-Regular.ttf": ("https://fonts.google.com/specimen/Oswald", ""),
    "Oswald-Bold.ttf": ("https://fonts.google.com/specimen/Oswald", ""),
    "RobotoSlab-Regular.ttf": ("https://fonts.google.com/specimen/Roboto+Slab", ""),
    "DancingScript-Regular.ttf": ("https://fonts.google.com/specimen/Dancing+Script", ""),
    "Anton-Regular.ttf": ("https://fonts.google.com/specimen/Anton", ""),
}


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify() -> int:
    """Report what is present, and whether it matches its pin."""
    problems = 0
    for name, (_, expected) in sorted(FONTS.items()):
        path = FONT_DIR / name
        if not path.exists():
            print(f"  MISSING   {name}")
            problems += 1
            continue
        actual = _sha256(path)
        if not expected:
            print(f"  UNPINNED  {name}  sha256={actual}")
            problems += 1
        elif actual != expected:
            print(f"  MISMATCH  {name}\n            expected {expected}\n            actual   {actual}")
            problems += 1
        else:
            print(f"  ok        {name}")
    return problems


def record() -> int:
    """Print the checksums of what is present, for pasting into FONTS."""
    for name in sorted(FONTS):
        path = FONT_DIR / name
        if path.exists():
            print(f'    "{name}": ("...", "{_sha256(path)}"),')
    return 0


def install() -> int:
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    failures = 0
    for name, (url, expected) in sorted(FONTS.items()):
        path = FONT_DIR / name
        if path.exists() and expected and _sha256(path) == expected:
            print(f"  ok        {name} (already installed)")
            continue
        if not expected:
            print(f"  REFUSED   {name} - no checksum pinned; download by hand, "
                  f"then run --record and paste the digest into FONTS")
            failures += 1
            continue
        if "#" in url:
            print(f"  MANUAL    {name} - inside an archive, extract by hand from {url}")
            failures += 1
            continue
        try:
            print(f"  fetching  {name}")
            urllib.request.urlretrieve(url, path)
        except Exception as exc:  # noqa: BLE001 - report, do not abort the batch
            print(f"  FAILED    {name}: {type(exc).__name__}")
            failures += 1
            continue
        if _sha256(path) != expected:
            path.unlink(missing_ok=True)
            print(f"  MISMATCH  {name} - deleted; the download did not match its pin")
            failures += 1
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="check what is installed")
    parser.add_argument("--record", action="store_true", help="print checksums to pin")
    args = parser.parse_args()

    print(f"font directory: {FONT_DIR}")
    if args.record:
        return record()
    problems = verify() if args.verify else install()
    if problems:
        print(f"\n{problems} font(s) need attention - see docs/FONT_PORTABILITY.md")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
