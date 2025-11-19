"""Application-wide configuration helpers."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    """Runtime configuration for the FastAPI application."""

    results_dir: Path = Path("./trail_results")
    static_url_prefix: str = "/static/results"

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def static_root(self) -> Path:
        """Directory exposed via FastAPI's StaticFiles mount."""
        return self.results_dir


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance and ensure directories exist."""
    settings = Settings()
    settings.static_root.mkdir(parents=True, exist_ok=True)
    return settings
