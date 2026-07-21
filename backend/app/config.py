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

    @property
    def database_path(self) -> Path:
        return self.data_dir / "creative_asset_engine.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"

    @property
    def storage_dir(self) -> Path:
        """Root for imported/generated files, organised Project -> Creative -> asset type."""
        return self.data_dir / "storage"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.storage_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
