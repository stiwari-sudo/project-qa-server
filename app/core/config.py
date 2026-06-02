from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
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
    # Calc-pack tracked question ids (comma-separated). Overview marks a project
    # complete when any of these answers Yes (not No/N-A).
    calc_pack_question_ids: str = Field(
        default="q_detailed_sd_5,q_pretender_sd_5,q_precon_sd_5"
    )

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
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def calc_pack_ids(self) -> list[str]:
        return [q.strip() for q in self.calc_pack_question_ids.split(",") if q.strip()]

    @property
    def reminder_offset_days(self) -> list[int]:
        return [int(x.strip()) for x in self.reminder_offsets.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
