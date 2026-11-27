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

    # --- Memory Lock signing (Ed25519 key is derived from this secret) ---
    # REQUIRED in production. Back it up: losing or changing it means older
    # signatures can no longer be verified with the new key.
    memory_signing_secret: str = ""
    memory_key_version: str = "1"
    system_identity: str = "Pacific Rim Auctions"
    app_version: str = "1.0.0"

    # --- Auction engine defaults (the evolution engine may tune these within bounds) ---
    min_bid_increment_minor: int = 100          # $1.00
    anti_snipe_window_seconds: int = 30
    anti_snipe_extension_seconds: int = 30
    bid_rate_limit_count: int = 20              # bids allowed per window, per user
    bid_rate_limit_window_seconds: int = 10

    # --- Background operations (24/7 loop) ---
    background_enabled: bool = True
    auction_close_interval_seconds: int = 15
    memory_verify_interval_seconds: int = 3600
    gate_recheck_interval_seconds: int = 86400  # daily pass over listings still waiting on the gate

    # --- OneTrust compliance checkpoint ---
    # The platform has a hard-coded compliance checkpoint. When ONETRUST_ENFORCE
    # is true, going live is refused unless OneTrust is connected AND cleared.
    onetrust_enforce: bool = False
    onetrust_api_base_url: str = ""
    onetrust_api_token: str = ""

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

    # --- Platform fee (the "rake"), as decimals e.g. 0.05 = 5% ---
    platform_fee_min: float = 0.05
    platform_fee_max: float = 0.08

    # --- OFAC sanctions screening: ON by default, fail-closed. Set SANCTIONS_SCREENING_ENABLED=false only to switch it off. ---
    sanctions_screening_enabled: bool = True
    ofac_sdn_csv_url: str = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV"
    ofac_alt_csv_url: str = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ALT.CSV"

    # --- Astra legal drafting (OpenAI API) ---
    # Drafts legal research packets for a human to verify and sign. It can never
    # clear a jurisdiction. Not configured = the draft endpoint refuses (fails closed).
    # ASTRA_MODEL must be the exact model id shown in your OpenAI account.
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    astra_model: str = ""
    astra_timeout_seconds: int = 120

    # --- Reply.io (outreach: sellers, agents/brokers, buyer follow-up) ---
    reply_io_api_key: str = ""
    reply_io_base_url: str = "https://api.reply.io/v3"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @model_validator(mode="after")
    def _production_safety(self):
        # A live platform must never run with placeholder secrets.
        if self.environment == "production":
            if self.secret_key == "CHANGE_ME_IN_ENV":
                raise ValueError("SECRET_KEY must be set to a real random value when ENVIRONMENT=production.")
            if len(self.memory_signing_secret) < 32:
                raise ValueError("MEMORY_SIGNING_SECRET (32+ characters) is required when ENVIRONMENT=production.")
        elif not self.memory_signing_secret:
            # Development and tests only. Never reachable in production (checked above).
            self.memory_signing_secret = "development-only-memory-secret-not-for-production"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
