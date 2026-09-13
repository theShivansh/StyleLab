"""Runtime configuration.

There is no demo mode (docs/DECISIONS.md, 2026-09-12). A missing or invalid key is a loud
boot failure, never a silent downgrade into a stub — AI-EVAL-CASES Case 25 asserts this.

Model IDs live here and in docs/DEPLOYMENT.md. Nowhere else. They must never appear in a
route handler, a domain module, or a prompt template.

(The second place was `.env.example` until S12. It is untracked now — it held a live key
from S2 until GitHub's scanner refused the first push.)
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: The local default. File-backed so a fresh clone runs and its wardrobe survives a restart.
DEFAULT_DATABASE_URL = "sqlite+pysqlite:///./stylelab.db"

#: What the application actually distinguishes: two behaviours, in `app/preflight.py`.
Environment = Literal["local", "production"]

#: Spellings people actually write, mapped to the two the application has. `development` is
#: here because it is the conventional value and S12 found it failing; `staging` maps to
#: `production` deliberately — a staging deployment has the same ephemeral filesystem and the
#: same shared signing key as a real one, and is exactly where those defaults should be caught.
ENV_SYNONYMS = {
    "local": "local",
    "development": "local",
    "dev": "local",
    "test": "local",
    "ci": "local",
    "production": "production",
    "prod": "production",
    "staging": "production",
    "stage": "production",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    #: Which environment this is. Every other default in this file leans toward *a fresh
    #: clone runs*, and `app/preflight.py` is the one place that knows those accommodations
    #: are wrong in a deployment. `local` keeps them and warns; `production` refuses to boot
    #: on the ones that make the application incorrect rather than merely worse.
    #:
    #: Default `local` on purpose. A default of `production` would make a fresh clone fail
    #: on three settings nobody has heard of yet; the cost of this direction is one
    #: environment variable in a deploy config, which is the one place somebody is already
    #: setting environment variables.
    #:
    #: **Synonyms are accepted and normalised**, which S12 added after the obvious thing
    #: happened: somebody set `APP_ENV=development` — the most common spelling of this
    #: variable anywhere — and the API stopped booting with a pydantic literal error about a
    #: value that was, by every convention outside this file, correct. A setting invented in
    #: S11 that rejects the industry-standard value for itself is the setting's bug, not the
    #: operator's.
    app_env: Environment = "local"

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

    # --- Rate limits (docs/SECURITY-PRIVACY.md, "rate limiting on upload and extraction") ---
    #: One window for all three quotas. Fifteen minutes is long enough that a real session —
    #: upload a batch, correct a few fields, compose, swap, compose again — never touches a
    #: limit, and short enough that a throttled client recovers within a coffee.
    rate_limit_window_s: float = 15 * 60
    #: **Images**, not requests. One POST carrying twelve photographs is twelve provider
    #: calls, so the bucket is spent per image (`app/services/ratelimit.py`). 24 is two full
    #: batches at the documented `max_images_per_batch`.
    rate_limit_images: float = 24
    #: Compositions. Each one is a six-agent crew run — the single most expensive thing the
    #: product does, and the one blocker B17 says the account cannot sustain anyway.
    rate_limit_composes: float = 12
    #: New anonymous sessions, per client address. There is no signup to throttle instead
    #: (blocker B15), so this is the only thing standing between a public URL and an
    #: unlimited supply of identities that can each spend the quotas above.
    rate_limit_sessions: float = 10
    #: How many proxies sit in front of this API and can be believed about who called.
    #:
    #: `0` means none: the session limiter keys on the socket peer, which is right on a
    #: laptop and on any host reachable directly. On a platform that terminates TLS and
    #: forwards — FastAPI Cloud, and every other managed runtime — the socket peer is the
    #: platform, so **every visitor on earth shares one bucket** and the eleventh person to
    #: open the product in fifteen minutes is refused a session. That is the failure this
    #: setting exists for, and it is not hypothetical: the quota above is 10.
    #:
    #: The value is a count of hops, not a switch, because the entry to believe is the one
    #: the *nearest trusted proxy* appended. `app/deps.py` counts from the right, so a wrong
    #: value degrades toward over-throttling (the proxy's own address, one shared bucket)
    #: rather than toward an open door. Reading the leftmost entry instead — the thing that
    #: looks equivalent — is a limiter any caller switches off with one header.
    trusted_proxy_hops: int = 0

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
    #: Which `ObjectStore` holds the bytes (`app/services/storage.py`).
    #:
    #: `local` is a directory, and is right on a laptop and on any host with a volume mounted
    #: at `STORAGE_ROOT`. `database` puts them in the same database as the wardrobe, which is
    #: the only correct answer on a runtime that scales to zero and replaces containers: a
    #: directory there stops existing between two visits, while the rows pointing into it do
    #: not, and the user is shown broken pictures of clothes they own.
    #:
    #: Default `local` for the same reason every other default here leans that way — a fresh
    #: clone should work and should keep its photographs somewhere a person can look at them.
    #: Preflight says so when a production boot leaves it here.
    storage_backend: Literal["local", "database"] = "local"

    # --- Identity and signed references ---
    #: HMAC key for session tokens and image URLs. Generated per process when unset, which
    #: means tokens do not survive a restart — see `app/security/tokens.py`.
    session_secret: str = ""
    session_ttl_s: int = 60 * 60 * 24 * 30
    #: How long an image URL handed to the browser stays valid.
    image_url_ttl_s: int = 60 * 30

    #: Operations credential for `GET /internal/db-activity` (`app/routers/internal.py`).
    #: Empty means the endpoint answers 503 rather than answering at all — unconfigured is
    #: closed, not open, because the alternative leaves a database-touching route reachable
    #: by anyone the moment somebody forgets a variable.
    #:
    #: Not a session secret and deliberately a different variable: an operations credential
    #: and a user identity should not be interchangeable, and this one lives in a CI secret
    #: store rather than in the application's own signing key.
    db_activity_token: str = ""

    # --- Web ---
    #: Browser origin allowed to call this API with credentials.
    web_origin: str = "http://localhost:3000"

    #: Below this, a field is presented as a hedge and offered for correction.
    confidence_floor: float = 0.7

    @field_validator("app_env", mode="before")
    @classmethod
    def _normalise_env(cls, value: object) -> object:
        """Accept the spellings people write; refuse the ones nobody means.

        An unknown value is still an error, and deliberately so — silently treating
        `APP_ENV=produciton` as local would switch off every production check over a typo,
        which is the failure this whole mechanism exists to prevent. The message names what
        is accepted, because a literal error listing two values when nine are allowed is a
        message that sends somebody to read the source.
        """
        if not isinstance(value, str):
            return value
        key = value.strip().lower()
        if not key:
            return "local"
        if key not in ENV_SYNONYMS:
            allowed = ", ".join(sorted(ENV_SYNONYMS))
            raise ValueError(f"APP_ENV={value!r} is not one of: {allowed}")
        return ENV_SYNONYMS[key]

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
