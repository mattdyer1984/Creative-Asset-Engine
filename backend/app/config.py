"""
Application configuration.

Kept deliberately small for M0: just enough to know where the SQLite
database and local file storage live. AI provider config (providers.yaml)
and Import Provider registration are introduced in M1/M2 — this file will
grow to load those, but nothing about its shape needs to change to do so.
"""

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


settings = Settings()
