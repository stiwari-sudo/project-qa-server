from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env from the project root (projectqa-api/) regardless of the process's
# working directory — config.py is at projectqa-api/app/core/, so parents[2] is
# projectqa-api/. Launching uvicorn from elsewhere previously skipped .env and
# silently fell back to the defaults (wrong DB → InvalidPassword, wrong auth).
# Real environment variables still take precedence over the file.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Application settings, loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = Field(default="development")
    api_v1_prefix: str = Field(default="/api/v1")

    # Database (asyncpg DSN), e.g. postgresql+asyncpg://qa:qa@db:5432/projectqa
    database_url: str = Field(
        default="postgresql+asyncpg://qa:qa@localhost:5432/projectqa"
    )

    # CORS — comma-separated list of allowed origins.
    cors_origins: str = Field(default="http://localhost:3000")

    # Auth: "dev" (stub) now, "azure" later. The dev stub resolves to this user.
    auth_provider: str = Field(default="dev")
    dev_user_email: str = Field(default="engineer@hts.uk.com")

    # Azure AD (used only when auth_provider == "azure").
    azure_tenant_id: str = Field(default="")
    azure_client_id: str = Field(default="")
    azure_audience: str = Field(default="")

    # Director overview — how "construction stage" is detected: "site" | "cmap".
    construction_source: str = Field(default="site")
    # Which stage order the "site" proxy treats as construction (Site=5 by
    # default; set to 4=Pre-construction for datasets with no Site-stage QA).
    construction_stage_order: int = Field(default=5)
    # Calc-pack tracked question ids (comma-separated). Overview marks a project
    # complete when any of these answers Yes (not No/N-A).
    calc_pack_question_ids: str = Field(
        default="q_detailed_sd_5,q_pretender_sd_5,q_precon_sd_5"
    )
    # The single calc-pack question a director's Building Control "confirm" writes
    # to (the canonical value the form + overview both read). Aligns with the
    # construction stage — precon for datasets with no Site-stage QA.
    calc_pack_primary_question_id: str = Field(default="q_precon_sd_5")

    # QA file share root for building folder scaffolding. Empty = disabled (local
    # dev): adding a building won't touch the share. On the J:-connected VM set
    # this to the UNC root (e.g. \\server\share) — NOT a mapped drive letter,
    # which is per-user and invisible to the service account — so adding an extra
    # building scaffolds its QA + calc folders. See app/services/qa_folders.py.
    qa_share_root: str = Field(default="")

    # Demo/sample seed data (fake users + projects 24001-24008), applied by
    # seeds.run only when true. Keep OFF against any database holding real QA
    # data; refused outright when APP_ENV is production.
    seed_sample_data: bool = Field(default=False)

    # CMAP integration (daily users + projects sync). OAuth2 client-credentials
    # against CMap's identity server. Secrets live in .env only (never commit).
    cmap_base_url: str = Field(default="https://api.cmaphq.com")
    cmap_token_url: str = Field(default="https://id.cmaphq.com/connect/token")
    cmap_resource: str = Field(default="https://api.cmaphq.com")
    cmap_scope: str = Field(default="api_access")
    cmap_client_id: str = Field(default="")
    cmap_client_secret: str = Field(default="")
    # CMap is multi-tenant; each API call carries a `tenant_id` header (the GUID
    # from GET /v1/tenants). Not required for the token request itself.
    cmap_tenant_id: str = Field(default="")
    cmap_page_size: int = Field(default=100)
    # Map CMap role/security-group names to our QA roles, comma-separated
    # "CMapName=our_role" pairs, e.g. "Director=director,Associate=associate".
    # A CMap role with no mapping grants NO role (fail closed → own-only).
    cmap_role_map: str = Field(default="")

    # Deadline reminder offsets (days before deadline), comma-separated.
    reminder_offsets: str = Field(default="14,7,3,1")

    # SMTP (Phase 3 — deadline reminders).
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from: str = Field(default="qa-noreply@hts.uk.com")
    smtp_tls: bool = Field(default=True)

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in ("production", "prod")

    @model_validator(mode="after")
    def _validate_auth_provider(self) -> Settings:
        """Fail closed on auth misconfiguration instead of booting with the
        dev stub, which trusts a client-supplied header and would hand any
        caller director-level access to the real dataset."""
        provider = self.auth_provider.strip().lower()
        if provider not in ("dev", "azure"):
            raise ValueError(
                f"AUTH_PROVIDER must be 'dev' or 'azure', got {self.auth_provider!r}"
            )
        self.auth_provider = provider
        if self.is_production and provider != "azure":
            raise ValueError(
                "AUTH_PROVIDER must be 'azure' when APP_ENV is production — the dev "
                "stub resolves users from a client-supplied header"
            )
        if provider == "azure" and not (self.azure_tenant_id and self.azure_client_id):
            raise ValueError(
                "AUTH_PROVIDER=azure requires AZURE_TENANT_ID and AZURE_CLIENT_ID"
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def calc_pack_ids(self) -> list[str]:
        return [q.strip() for q in self.calc_pack_question_ids.split(",") if q.strip()]

    @property
    def cmap_enabled(self) -> bool:
        return bool(self.cmap_client_id and self.cmap_client_secret)

    @property
    def cmap_role_map_parsed(self) -> dict[str, str]:
        """CMap role name (lowercased) -> our QA role string."""
        out: dict[str, str] = {}
        for pair in self.cmap_role_map.split(","):
            name, sep, role = pair.partition("=")
            if sep and name.strip() and role.strip():
                out[name.strip().lower()] = role.strip()
        return out

    @property
    def reminder_offset_days(self) -> list[int]:
        return [int(x.strip()) for x in self.reminder_offsets.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
