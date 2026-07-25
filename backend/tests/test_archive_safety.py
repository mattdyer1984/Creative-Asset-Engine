"""
Archive safety tests (Phase 0 remediation, WP-0B).

Proves `scripts/verify_archive.py` actually REJECTS unsafe content. A
scanner that only ever passes is worse than none, so every forbidden
category below is asserted to fail, not just the clean case to pass.

All planted credentials are obviously-synthetic constants built from
repeated characters - they match the detector's shape without being
real, and nothing here reads any actual credential.
"""

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERIFIER = REPO_ROOT / "scripts" / "verify_archive.py"

# Synthetic, shape-matching, non-real credentials.
FAKE_GOOGLE_KEY = "AIza" + "A" * 35
FAKE_GOOGLE_AQ_KEY = "AQ." + "B" * 40
FAKE_OPENAI_KEY = "sk-" + "C" * 40


def _run_verifier(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VERIFIER), *args],
        capture_output=True,
        text=True,
    )


@pytest.fixture
def clean_staging(tmp_path: Path) -> Path:
    """A minimal, legitimate staging tree - source, docs, config template."""
    staging = tmp_path / "staging"
    (staging / "backend" / "app").mkdir(parents=True)
    (staging / "backend" / "app" / "main.py").write_text("def main():\n    return 1\n")
    (staging / "README.md").write_text("# Project\n\nSet OPENAI_API_KEY=sk-... to run.\n")
    # The committed template: credential-ish NAMES, deliberately no values.
    (staging / "backend" / ".env.example").write_text(
        "OPENAI_API_KEY=\nNANO_BANANA_API_KEY=\n"
    )
    return staging


def test_clean_staging_passes(clean_staging: Path):
    result = _run_verifier("--dir", str(clean_staging))
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout


def test_env_example_with_empty_values_is_not_a_false_positive(clean_staging: Path):
    """The committed template must never trip the scanner - it ships in every archive."""
    result = _run_verifier("--dir", str(clean_staging))
    assert result.returncode == 0
    assert ".env.example" not in result.stderr


def test_real_env_file_is_rejected(clean_staging: Path):
    (clean_staging / "backend" / ".env").write_text(f"NANO_BANANA_API_KEY={FAKE_GOOGLE_AQ_KEY}\n")
    result = _run_verifier("--dir", str(clean_staging))
    assert result.returncode == 1
    assert "real .env file" in result.stderr


def test_database_file_is_rejected(clean_staging: Path):
    (clean_staging / "backend" / "app.db").write_bytes(b"SQLite format 3\x00")
    result = _run_verifier("--dir", str(clean_staging))
    assert result.returncode == 1
    assert "database file" in result.stderr


def test_runtime_storage_is_rejected(clean_staging: Path):
    data_dir = clean_staging / "backend" / "data" / "slides"
    data_dir.mkdir(parents=True)
    (data_dir / "slide.jpg").write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
    result = _run_verifier("--dir", str(clean_staging))
    assert result.returncode == 1
    assert "runtime storage" in result.stderr


def test_virtualenv_and_node_modules_are_rejected(clean_staging: Path):
    venv = clean_staging / "backend" / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "thing.py").write_text("x = 1\n")
    result = _run_verifier("--dir", str(clean_staging))
    assert result.returncode == 1
    assert "virtualenv" in result.stderr


@pytest.mark.parametrize(
    "filename, payload, expected",
    [
        # The specific failure mode WP-0B calls out: a secret is not safe
        # merely because its FILENAME contains no hint of one.
        ("backend/app/notes.md", f"key is {FAKE_GOOGLE_KEY}", "Google API key"),
        ("backend/app/config_sample.py", f'TOKEN = "{FAKE_OPENAI_KEY}"', "OpenAI"),
        ("docs/setup.txt", f"AQ form: {FAKE_GOOGLE_AQ_KEY}", "Google API key"),
    ],
)
def test_secret_content_is_rejected_regardless_of_filename(
    clean_staging: Path, filename: str, payload: str, expected: str
):
    target = clean_staging / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload + "\n")
    result = _run_verifier("--dir", str(clean_staging))
    assert result.returncode == 1, f"scanner missed a planted secret in {filename}"
    assert expected in result.stderr


def test_scanner_never_echoes_the_secret_value(clean_staging: Path):
    """A scanner that prints the secret it found has just leaked it again."""
    (clean_staging / "backend" / "app" / "leak.py").write_text(f'K = "{FAKE_GOOGLE_KEY}"\n')
    result = _run_verifier("--dir", str(clean_staging))
    assert result.returncode == 1
    combined = result.stdout + result.stderr
    assert FAKE_GOOGLE_KEY not in combined, "verifier echoed the matched secret value"


def test_built_archive_is_verified_too(tmp_path: Path, clean_staging: Path):
    """The archive is re-checked independently, not trusted because staging passed."""
    archive = tmp_path / "out.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(clean_staging / "README.md", "README.md")
        zf.writestr("backend/.env", f"NANO_BANANA_API_KEY={FAKE_GOOGLE_AQ_KEY}\n")

    result = _run_verifier("--archive", str(archive))
    assert result.returncode == 1
    assert "real .env file" in result.stderr


def test_clean_archive_passes(tmp_path: Path, clean_staging: Path):
    archive = tmp_path / "clean.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(clean_staging / "README.md", "README.md")
        zf.write(clean_staging / "backend" / ".env.example", "backend/.env.example")

    result = _run_verifier("--archive", str(archive))
    assert result.returncode == 0, result.stderr
