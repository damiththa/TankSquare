"""
TankSquare Configuration Module (DEV & PROD GCP Environments).

Supports direct execution on Google Cloud Run with Cloud Firestore and Cloud Storage.
Automatically selects `.env.dev` or `.env.prod` based on the `ENV` environment variable.
"""

import os
from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_env_file() -> str:
    env = os.getenv("ENV", "dev").lower().strip()
    if os.path.exists(".env"):
        return ".env"
    return ".env.prod" if env == "prod" else ".env.dev"


class Settings(BaseSettings):
    """Application & Google Cloud Platform configuration settings."""

    ENV: str = "dev"  # "dev" or "prod"
    APP_NAME: str = "TankSquare"
    API_VERSION: str = "1.0.0"
    PORT: int = 8080

    # Google Cloud Platform (Direct Firestore & Cloud Storage — Zero SQLite)
    GCP_PROJECT_ID: str = "tanksquare-dev"
    FIRESTORE_DATABASE: str = "(default)"
    FIRESTORE_COLLECTION_PREFIX: str = "dev_"
    GCS_BUCKET_NAME: str = "tanksquare-dev-media"

    # External Geo & Grid APIs
    GOOGLE_MAPS_API_KEY: str = ""
    W3W_API_KEY: str = ""
    W3W_CACHE_TTL_SECONDS: int = 86400  # Compliant short-TTL cache (<30 days per W3W ToS)

    # Multi-Vendor Security & Environment Controls
    ALLOWED_ORIGINS: str = "*"
    REQUIRE_VENDOR_API_KEY: bool = False
    SEED_DEMO_DATA: bool = True

    # Core Product Guardrails (Enforced across DEV and PROD)
    RESIDENT_ACCOUNT_REQUIRED: bool = False  # Residents NEVER create a TankSquare account
    RESIDENT_BILLING_ENABLED: bool = False   # 100% Free for residents; B2B vendor-paid only

    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_prod(self) -> bool:
        return self.ENV.lower().strip() == "prod"

    @property
    def cors_origins(self) -> List[str]:
        if self.ALLOWED_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    def collection_name(self, base_name: str) -> str:
        """Return the environment-isolated Firestore collection name (`dev_vendors` vs `prod_vendors`)."""
        return f"{self.FIRESTORE_COLLECTION_PREFIX}{base_name}"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
