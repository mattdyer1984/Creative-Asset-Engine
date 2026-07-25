#!/usr/bin/env python3
"""
Archive safety verification (Phase 0 remediation, WP-0B).

Two independent layers, run against either a staging directory or a
built archive:

  1. Forbidden-path check - nothing matching a secret/data/build pattern
     may be present at all.
  2. Content-based secret scan - a file is not safe merely because its
     NAME looks innocuous, which is the specific failure mode WP-0B
     calls out.

Deliberately stdlib-only. `gitleaks` is the richer tool and was the
original intent, but Homebrew is not available on this machine, and
downloading and executing a release binary is not something to do
silently. This scanner is narrower than gitleaks but fully auditable
(every pattern is visible below) and adds no dependency. If gitleaks is
installed later, `package_release.sh` picks it up automatically and runs
it as an ADDITIONAL layer - this file is not meant to replace it.

Usage:
    python3 scripts/verify_archive.py --dir  <staging-directory>
    python3 scripts/verify_archive.py --archive <path/to/archive.zip>

Exit code 0 = clean, 1 = at least one finding (never "warn and pass").
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

# Paths that must never appear in a shareable archive. This is a SECOND
# line of defence: package_release.sh builds its file list from
# `git ls-files` (an allowlist of tracked files), so anything gitignored
# is already excluded by construction. This catches the case where that
# primary mechanism is changed or bypassed.
FORBIDDEN_PATH_PATTERNS = [
    (re.compile(r"(^|/)\.env$"), "real .env file"),
    (re.compile(r"(^|/)\.env\.local$"), "local .env override"),
    (re.compile(r"\.(db|sqlite|sqlite3)$"), "database file"),
    (re.compile(r"\.bak$"), "backup file"),
    (re.compile(r"(^|/)backend/data/"), "runtime storage / local data"),
    (re.compile(r"(^|/)\.venv/"), "virtualenv"),
    (re.compile(r"(^|/)node_modules/"), "node modules"),
    (re.compile(r"(^|/)\.git/"), "git internals"),
    (re.compile(r"(^|/)__pycache__/"), "bytecode cache"),
    (re.compile(r"\.zip$"), "nested archive"),
    (re.compile(r"(^|/)settings\.local\.json$"), "machine-local tool settings"),
]

# Content patterns. Each requires a realistically long value so that
# documentation placeholders ("sk-...", "AIza...") and the empty
# assignments in .env.example do not trip it.
SECRET_CONTENT_PATTERNS = [
    (re.compile(r"AIza[0-9A-Za-z_\-]{35}"), "Google API key (AIza form)"),
    (re.compile(r"\bAQ\.[A-Za-z0-9_\-]{30,}"), "Google API key (AQ. form)"),
    (re.compile(r"\bsk-proj-[A-Za-z0-9_\-]{20,}"), "OpenAI project key"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"), "Anthropic key"),
    (re.compile(r"\bsk-[A-Za-z0-9]{32,}"), "OpenAI-style key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|secret|token|password|passwd)\b\s*[:=]\s*"
            r"['\"]?[A-Za-z0-9_\-]{24,}"
        ),
        "long credential-shaped assignment",
    ),
]

# Files whose whole purpose is to describe credential handling. They are
# still content-scanned - the patterns above must not match - but their
# variable NAMES legitimately look credential-ish.
DOC_ALLOWLIST = {".env.example"}

MAX_SCAN_BYTES = 2 * 1024 * 1024


def _scan_text(path_label: str, text: str) -> list[str]:
    findings = []
    for pattern, label in SECRET_CONTENT_PATTERNS:
        for match in pattern.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            # Never echo the matched value itself.
            findings.append(f"{path_label}:{line_no}: possible {label}")
    return findings


def _check_paths(names: list[str]) -> list[str]:
    findings = []
    for name in names:
        for pattern, label in FORBIDDEN_PATH_PATTERNS:
            if pattern.search(name):
                findings.append(f"{name}: forbidden content ({label})")
    return findings


def verify_directory(root: Path) -> list[str]:
    names, findings = [], []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        names.append(rel)
        if path.stat().st_size > MAX_SCAN_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable - path check still applied
        if path.name in DOC_ALLOWLIST or rel in DOC_ALLOWLIST:
            findings.extend(_scan_text(rel, text))
            continue
        findings.extend(_scan_text(rel, text))
    return _check_paths(names) + findings


def verify_archive(archive: Path) -> list[str]:
    findings = []
    with zipfile.ZipFile(archive) as zf:
        names = [i.filename for i in zf.infolist() if not i.is_dir()]
        findings.extend(_check_paths(names))
        for info in zf.infolist():
            if info.is_dir() or info.file_size > MAX_SCAN_BYTES:
                continue
            try:
                text = zf.read(info).decode("utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            findings.extend(_scan_text(info.filename, text))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dir", type=Path, help="staging directory to verify")
    group.add_argument("--archive", type=Path, help="built .zip to verify")
    args = parser.parse_args()

    target = args.dir or args.archive
    if not target.exists():
        print(f"verify_archive: target does not exist: {target}", file=sys.stderr)
        return 1

    findings = verify_directory(args.dir) if args.dir else verify_archive(args.archive)

    if findings:
        print(f"FAIL: {len(findings)} finding(s) in {target}", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        print(
            "\nNothing was shipped. Fix the cause (or narrow the file list) and re-run.",
            file=sys.stderr,
        )
        return 1

    print(f"PASS: {target} contains no forbidden paths and no secret-shaped content.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
