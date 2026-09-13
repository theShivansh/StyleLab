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

#: The local default. File-backed so a fresh clone runs and its wardrobe survives a restart.
DEFAULT_DATABASE_URL = "sqlite+pysqlite:///./stylelab.db"


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
    #: Output ceiling for one extraction. Set explicitly rather than left to the provider's
    #: default, because on these models it is a correctness setting and not only a cost one:
    #: a reasoning-capable model spends its budget thinking first, so too low a ceiling
    #: returns an *empty* response rather than a short one. `groq_transport._to_result` names
    #: that case; `tests/live/test_model_availability.py` holds it to it.
    #:
    #: Stays at 2048. S7 tried lowering it, measured, and put it back — the note is here so
    #: nobody spends the afternoon again.
    #:
    #: The account's on-demand tier caps **output tokens per minute, per model**, at 1000,
    #: and refuses requests whose expected output exceeds what the minute has left
    #: (`Limit 1000, Requested 1579`). It looks like the ceiling is the lever. It is not:
    #: ceilings of 960, 896 and 800 were refused just as readily once the window was spent,
    #: so the refusal tracks the *remaining budget*, not the number we send.
    #:
    #: What lowering it does do is take away the model's room to think. At 768 the request is
    #: admitted and comes back `json_validate_failed` with nothing generated — the same
    #: reasoning-budget failure S6 found at 32, arriving as a burned call and a failed card
    #: rather than as a retryable refusal. A ceiling that fails *after* admission is strictly
    #: worse than one that is sometimes refused before it.
    #:
    #: So: 2048, and the tier is the thing to fix (blocker B17). A real extraction uses only
    #: ~205 output tokens (823 characters, measured) — the rest of this budget is the space
    #: the model reasons in before it writes any of them.
    groq_vision_max_tokens: int = 2048

    # --- Agent crew (docs/AGENT-SYSTEM.md) ---
    agent_framework: Literal["crewai"] = "crewai"
    agent_latency_budget_ms: int = 15_000
    agent_max_output_tokens: int = 800
    agent_trend_scout_enabled: bool = True

    # --- Trend source: Exa (docs/AGENT-SYSTEM.md) ---
    #: Required for the Trend Scout, and for nothing else. Absent, the crew runs without
    #: that role and discloses degradation level 2 — which is the honest state of affairs
    #: rather than a silent omission. It is deliberately *not* a boot failure the way
    #: `groq_api_key` is: the product composes outfits without trends, and cannot compose
    #: them at all without a vision and text model.
    exa_api_key: str = ""
    #: `auto` lets Exa pick keyword or neural retrieval per query. The others are here so a
    #: deployment can pin the behaviour; nothing in the product chooses between them.
    exa_search_type: Literal["auto", "neural", "keyword", "fast"] = "auto"
    #: Results per query. The spec asks for six to eight — enough that deduplication and the
    #: attribution filter have something to work with, few enough to stay inside the latency
    #: budget the Trend Scout shares with five other agents.
    exa_max_results: int = 8
    exa_timeout_s: float = 8.0
    #: How long a normalised trend lookup is reused, keyed by region + season + style
    #: profile. A day: fashion journalism does not turn over hourly, and the alternative is
    #: paying for a search on every compose of every session.
    trend_cache_ttl_s: int = 24 * 60 * 60
    #: Where the user is, for region-aware queries. One value for now; a per-user setting is
    #: S9's, and guessing it from an IP address would be an inference about a person.
    trend_region: str = "global"
    trend_max_age_days: int = 120

    # --- Uploads ---
    max_upload_bytes: int = 10 * 1024 * 1024
    max_images_per_batch: int = 12
    #: Resolution bounds (docs/SECURITY-PRIVACY.md). The floor rejects thumbnails a vision
    #: model cannot read; the ceiling rejects decompression bombs whose byte size is small.
    min_image_edge_px: int = 128
    max_image_pixels: int = 40_000_000
    #: The provider gets a downscaled copy, not the stored original: a 4000px photograph of a
    #: shirt carries no more garment information than a 1024px one, and costs more to send.
    analysis_max_edge_px: int = 1024

    # --- Storage / persistence ---
    #: Read as configured, which may be blank: `.env.example` ships the key with no value,
    #: and pydantic-settings faithfully reports that as `""` rather than as absent. Use
    #: `resolved_database_url` — a blank line in a template means "not configured", and
    #: treating it as a configured empty URL is how the API refused to boot for a developer
    #: who had done nothing wrong.
    database_url: str = ""
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    storage_bucket: str = "stylelab-private"
    #: Where `LocalObjectStore` keeps uploaded images. Private directory, never under a web
    #: root, and gitignored.
    storage_root: str = "var/uploads"

    # --- Identity and signed references ---
    #: HMAC key for session tokens and image URLs. Generated per process when unset, which
    #: means tokens do not survive a restart — see `app/security/tokens.py`.
    session_secret: str = ""
    session_ttl_s: int = 60 * 60 * 24 * 30
    #: How long an image URL handed to the browser stays valid.
    image_url_ttl_s: int = 60 * 30

    # --- Web ---
    #: Browser origin allowed to call this API with credentials.
    web_origin: str = "http://localhost:3000"

    #: Below this, a field is presented as a hedge and offered for correction.
    confidence_floor: float = 0.7

    @property
    def resolved_database_url(self) -> str:
        """Where the wardrobe lives, with the local default filled in.

        A **file**, never `:memory:`. The rule `db/session.py` states — no silent fallback to
        a throwaway database — is about data that vanishes on restart while looking like it
        worked. A named file in the working directory is neither throwaway nor silent: the
        dialect is logged at boot, and the file is on disk where anyone can see it.

        Postgres via Supabase lands with deployment in S11, at which point this default stops
        being reached in any environment that matters.
        """
        return self.database_url or DEFAULT_DATABASE_URL


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor.

    Raises pydantic.ValidationError at first call if GROQ_API_KEY is absent. Call this
    during application startup so the failure surfaces at boot rather than at a user's
    first request.
    """
    return Settings()  # type: ignore[call-arg]  # values come from env
