"""Runtime configuration.

There is no demo mode (docs/DECISIONS.md, 2026-09-12). A missing or invalid key is a loud
boot failure, never a silent downgrade into a stub — AI-EVAL-CASES Case 25 asserts this.

Model IDs live here and in .env.example. Nowhere else. They must never appear in a route
handler, a domain module, or a prompt template.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Groq. Required; see docs/DECISIONS.md (B5) for the model choice. ---
    groq_api_key: str = Field(min_length=1)
    groq_text_model: str = "openai/gpt-oss-120b"
    groq_vision_model: str = "qwen/qwen3.8-27b"
    #: Availability fallback only. Never triggered by low confidence — a low-confidence
    #: extraction is a signal to surface to the user, not a reason to retry cheaper.
    groq_vision_fallback_model: str = "qwen/qwen3.6-27b"

    # --- Agent crew (docs/AGENT-SYSTEM.md) ---
    agent_framework: Literal["crewai"] = "crewai"
    agent_latency_budget_ms: int = 15_000
    agent_max_output_tokens: int = 800
    agent_trend_scout_enabled: bool = True

    # --- Trend source ---
    trend_source: Literal["corpus", "web"] = "corpus"
    trend_corpus_path: str = "data/trends"
    trend_max_age_days: int = 120

    # --- Uploads ---
    max_upload_bytes: int = 10 * 1024 * 1024
    max_images_per_batch: int = 12

    # --- Storage / persistence ---
    database_url: str = ""
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    storage_bucket: str = "stylelab-private"

    #: Below this, a field is presented as a hedge and offered for correction.
    confidence_floor: float = 0.7


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor.

    Raises pydantic.ValidationError at first call if GROQ_API_KEY is absent. Call this
    during application startup so the failure surfaces at boot rather than at a user's
    first request.
    """
    return Settings()  # type: ignore[call-arg]  # values come from env
