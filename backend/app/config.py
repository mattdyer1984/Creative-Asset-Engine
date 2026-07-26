"""
Application configuration.

Kept deliberately small for M0: just enough to know where the SQLite
database and local file storage live. AI provider config (providers.yaml)
and Import Provider registration are introduced in M1/M2 — this file will
grow to load those, but nothing about its shape needs to change to do so.
"""

import os
from collections.abc import Mapping
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CAE_")

    # Root directory for all persistent local data (DB file + stored assets).
    # Defaults to a `data/` folder alongside the backend package so the app
    # is fully self-contained on this machine.
    data_dir: Path = Path(__file__).resolve().parent.parent / "data"

    # ADR 0001 WP-1.5A. Off by default: the previous rendering path stays
    # live until case 4 passes end to end, the three regression cases pass,
    # manifests prove ownership is correct and the benchmark does not
    # regress. Rollback is this flag, not a database intervention.
    typography_renderer_enabled: bool = False

    # O1. Concurrent stage execution is on by default; this forces the old
    # strictly-sequential schedule. An escape hatch that must be reachable in
    # an incident without a deploy, which is why it is a setting rather than
    # only a code path.
    sequential_stages: bool = False

    @property
    def database_path(self) -> Path:
        return self.data_dir / "creative_asset_engine.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"

    @property
    def storage_dir(self) -> Path:
        """Root for imported/generated files, organised Project -> Slideshow/Slide -> asset type."""
        return self.data_dir / "storage"

    @property
    def generation_logs_dir(self) -> Path:
        """
        Phase 12 (Human Feedback & Learning System, see MIGRATION_PLAN.md) -
        root for the permanent, self-contained archive folder created for
        every generate-creative call - one subfolder per call, named by
        its exact timestamp (YYYY-MM-DD_HH-MM-SS). Deliberately separate
        from storage_dir: this is a human-facing archive meant to be
        browsed/opened directly (see "Generation Logs" in the spec),
        not internal asset storage keyed by entity id.
        """
        return self.data_dir / "Generation Logs"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.generation_logs_dir.mkdir(parents=True, exist_ok=True)


class UnknownSetting(RuntimeError):
    """A `CAE_` variable was set that this build does not understand."""


def reject_unknown_env_overrides(environ: Mapping[str, str] | None = None) -> None:
    """
    Fail on a `CAE_` variable that no field would read.

    pydantic-settings only ever looks up the fields it declares, so an
    unrecognised `CAE_` variable is silently discarded. That is dangerous
    rather than merely untidy: `CAE_DATABASE_URL` looks like it redirects the
    database - `database_url` is a real attribute - but it is a derived
    property, so the override does nothing and the caller carries on believing
    they are pointed at a scratch copy. That mistake has already migrated the
    real development database once.

    An override that silently does nothing is worse than one that fails.
    """
    environ = os.environ if environ is None else environ
    known = {f"CAE_{name.upper()}" for name in Settings.model_fields}
    unknown = sorted(
        name for name in environ
        if name.startswith("CAE_") and name.upper() not in known
    )
    if unknown:
        raise UnknownSetting(
            f"unrecognised setting(s): {', '.join(unknown)}. "
            f"This build reads: {', '.join(sorted(known))}. "
            "To point the application at a different database, set CAE_DATA_DIR."
        )


reject_unknown_env_overrides()
settings = Settings()
