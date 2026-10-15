"""Central configuration. Everything is read from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    # --- Mesh API (mandatory LLM gateway) ---
    mesh_api_key: str = ""
    mesh_base_url: str = "https://api.meshapi.ai/v1"
    # Chat model used by strategist / writer / editor / learner agents
    mesh_chat_model: str = "openai/gpt-4o-mini"
    # Stronger model for the editor (critique quality matters most)
    mesh_editor_model: str = "openai/gpt-4o-mini"
    # Image model reachable through Mesh
    mesh_image_model: str = "openai/gpt-image-1"
    # Embedding model used for brand-voice similarity scoring
    mesh_embedding_model: str = "openai/text-embedding-3-small"
    # When true, the Mesh client returns deterministic canned responses (tests / offline demo only).
    mesh_mock: bool = False
    mesh_timeout_seconds: float = 90.0

    # --- Database ---
    database_url: str = "sqlite:///./data/creatoros.db"

    # --- Pipeline knobs ---
    editor_max_rounds: int = 2
    editor_pass_score: float = 7.5  # editor score (0-10) at which a draft is accepted

    # --- Scheduling / publishing ---
    scheduler_enabled: bool = True
    scheduler_poll_seconds: int = 20
    simulate_engagement: bool = True  # after a (simulated) publish, synthesize engagement metrics
    # Optional real publishing (X / Twitter). When unset the publisher runs in "simulated" mode.
    x_api_key: str = ""
    x_api_secret: str = ""
    x_access_token: str = ""
    x_access_secret: str = ""

    # --- Storage ---
    data_dir: Path = BASE_DIR / "data"

    # --- Misc ---
    app_name: str = "CreatorOS"
    log_level: str = "INFO"

    @property
    def images_dir(self) -> Path:
        d = self.data_dir / "images"
        d.mkdir(parents=True, exist_ok=True)
        return d


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
