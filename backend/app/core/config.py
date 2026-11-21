"""
Central configuration for Pacific Rim Auctions.

All secrets (bank webhook secret, DB credentials, etc.) are loaded from
environment variables / a .env file. Nothing sensitive is hardcoded here.
"""
from functools import lru_cache
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- General ---
    app_name: str = "Pacific Rim Auctions"
    environment: str = "development"  # development | staging | production
    api_v1_prefix: str = "/api/v1"

    # Operating target: number of countries the platform serves once each
    # one has passed real legal review (see jurisdiction nodes).
    country_target: int = 190

    # --- Security ---
    secret_key: str = "CHANGE_ME_IN_ENV"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # --- First admin account (created once, only if no admin exists yet) ---
    # Set both on the host, start the service once, then DELETE the password
    # variable. Public signup can never create an admin.
    admin_bootstrap_email: str = ""
    admin_bootstrap_password: str = ""

    # --- Browser access (comma-separated list of allowed website origins) ---
    cors_origins: str = "https://pacificrimauctions.com,https://www.pacificrimauctions.com"

    # --- Database ---
    database_url: str = "sqlite:///./pacific_rim.db"

    # --- First Hawaiian Bank (receive-only settlement rail) ---
    # The platform only RECEIVES money. There is no payout, transfer or
    # withdrawal code anywhere in this codebase.
    fhb_bank_name: str = "First Hawaiian Bank"
    fhb_branch: str = "Lihue Branch, Kauai"
    fhb_routing_number: str = "121301015"
    # Set in the environment of the deployed service (not committed here).
    fhb_account_number: str = ""
    # Shared secret used to verify incoming bank credit notifications.
    fhb_webhook_secret: str = ""

    # --- Platform fee (the "rake"), as decimals e.g. 0.03 = 3% ---
    platform_fee_min: float = 0.03
    platform_fee_max: float = 0.05

    # --- Reply.io (outreach: sellers, agents/brokers, buyer follow-up) ---
    reply_io_api_key: str = ""
    reply_io_base_url: str = "https://api.reply.io/v3"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @model_validator(mode="after")
    def _refuse_placeholder_secret_in_production(self):
        # A live platform must never run with the placeholder signing secret.
        if self.environment == "production" and self.secret_key == "CHANGE_ME_IN_ENV":
            raise ValueError("SECRET_KEY must be set to a real random value when ENVIRONMENT=production.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
