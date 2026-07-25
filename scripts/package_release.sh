#!/usr/bin/env bash
#
# Safe project packaging (Phase 0 remediation, WP-0B).
#
# Design note - why this is not `zip -r ... -x <deny-list>`:
# a deny-list ships anything you forgot to name. This instead builds an
# ALLOWLIST from `git ls-files`, i.e. exactly the tracked files. Anything
# gitignored (.env, backend/data/, .venv, node_modules) is excluded by
# construction rather than by remembering to exclude it. verify_archive.py
# then re-checks independently, so a change to this script cannot silently
# start shipping secrets.
#
# Steps: stage tracked files -> scan staging -> build archive OUTSIDE the
# repo -> verify built archive -> remove staging.
#
# Usage:  ./scripts/package_release.sh [output-directory]
# Default output directory is the repo's parent.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${1:-$(dirname "$REPO_ROOT")}"
PROJECT_NAME="$(basename "$REPO_ROOT")"
STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE_PATH="${OUTPUT_DIR}/${PROJECT_NAME}-${STAMP}.zip"

# Staging lives in the system temp dir, never inside the repo - so a
# failed run can never leave a half-built copy that a later run picks up.
STAGING_DIR="$(mktemp -d "${TMPDIR:-/tmp}/${PROJECT_NAME}-package.XXXXXX")"
cleanup() { rm -rf "$STAGING_DIR"; }
trap cleanup EXIT

cd "$REPO_ROOT"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "WARNING: working tree has uncommitted changes; packaging tracked files as they exist on disk." >&2
fi

echo "==> Staging tracked files (allowlist from git ls-files)"
FILE_COUNT=0
while IFS= read -r -d '' file; do
  mkdir -p "$STAGING_DIR/$(dirname "$file")"
  cp "$file" "$STAGING_DIR/$file"
  FILE_COUNT=$((FILE_COUNT + 1))
done < <(git ls-files -z)
echo "    staged $FILE_COUNT tracked file(s)"

echo "==> Verifying staging directory (forbidden paths + secret content)"
python3 "$REPO_ROOT/scripts/verify_archive.py" --dir "$STAGING_DIR"

# gitleaks is the richer scanner and runs as an ADDITIONAL layer when
# present. It is intentionally not required: Homebrew is unavailable on
# the current machine, and silently downloading a release binary is not
# an acceptable default. Install it and this picks it up automatically.
if command -v gitleaks >/dev/null 2>&1; then
  echo "==> gitleaks found - running as an additional scan layer"
  gitleaks detect --source "$STAGING_DIR" --no-git --redact --exit-code 1
else
  echo "==> gitleaks not installed - skipping (stdlib scanner above already ran)"
fi

echo "==> Building archive outside the repo: $ARCHIVE_PATH"
mkdir -p "$OUTPUT_DIR"
rm -f "$ARCHIVE_PATH"
( cd "$STAGING_DIR" && zip -rq "$ARCHIVE_PATH" . )

echo "==> Verifying the built archive independently"
python3 "$REPO_ROOT/scripts/verify_archive.py" --archive "$ARCHIVE_PATH"

echo
echo "Done: $ARCHIVE_PATH"
echo "      $(unzip -l "$ARCHIVE_PATH" | tail -1 | tr -s ' ')"
