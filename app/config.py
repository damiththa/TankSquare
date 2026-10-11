"""
TankSquare Configuration Module (`app/config.py`).

Zero Hardcoded Secrets & Strict Free-Tier Cost Protection Architecture:
- All sensitive keys (`GOOGLE_MAPS_API_KEY`, `W3W_API_KEY`, `SESSION_SIGNING_SECRET`,
  `VENDOR_API_SHARED_SECRET`) are loaded at runtime via `app/services/secret_manager.py`
  from Cloud Run `--set-secrets` environment bindings or directly from Google Cloud Secret Manager.
- Enforces hard monthly request caps (`MAPS_MONTHLY_FREE_TIER_CAP=9500`, below Google Maps'
  10,000/month free SKU limit) so TankSquare never spills into paid Pay-As-You-Go billing.
"""

import os
from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.services.secret_manager import get_secret


class Settings(BaseSettings):
    """Application & Google Cloud Platform configuration settings (Zero hardcoded secrets)."""

    ENV: str = "dev"  # "dev" or "prod"
    APP_NAME: str = "TankSquare"
    API_VERSION: str = "1.0.0"
    PORT: int = 8080

    # Google Cloud Platform Project & Resource Identifiers (Injected by Cloud Run / CI)
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT", "")
    FIRESTORE_DATABASE: str = "(default)"
    FIRESTORE_COLLECTION_PREFIX: str = ""
    GCS_BUCKET_NAME: str = ""
    USE_GCP_SECRET_MANAGER: bool = False

    # Non-sensitive cache TTL (<30 days per W3W ToS)
    W3W_CACHE_TTL_SECONDS: int = 86400

    # Strict Free-Tier Hard Caps (Prevents Pay-As-You-Go Overage Charges)
    ENFORCE_FREE_TIER_HARD_CAP: bool = True
    MAPS_MONTHLY_FREE_TIER_CAP: int = 9500  # Google Maps Essentials gives 10,000 free/mo; stop at 9,500
    MAPS_DAILY_SAFE_CAP: int = 300          # 300/day * 30 days = 9,000/mo (< 10,000 free/mo)

    # Multi-Vendor Security & Environment Controls
    ALLOWED_ORIGINS: str = "*"
    REQUIRE_VENDOR_API_KEY: bool = False
    SEED_DEMO_DATA: bool = True

    # Core Product Guardrails (Enforced across DEV and PROD)
    RESIDENT_ACCOUNT_REQUIRED: bool = False  # Residents NEVER create a TankSquare account
    RESIDENT_BILLING_ENABLED: bool = False   # 100% Free for residents; B2B vendor-paid only

    model_config = SettingsConfigDict(
        env_file=".env" if os.path.exists(".env") else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_prod(self) -> bool:
        return self.ENV.lower().strip() == "prod"

    @property
    def effective_collection_prefix(self) -> str:
        if self.FIRESTORE_COLLECTION_PREFIX:
            return self.FIRESTORE_COLLECTION_PREFIX
        return "prod_" if self.is_prod else "dev_"

    @property
    def effective_gcs_bucket(self) -> str:
        if self.GCS_BUCKET_NAME:
            return self.GCS_BUCKET_NAME
        if self.GCP_PROJECT_ID:
            return f"{self.GCP_PROJECT_ID}-media"
        return f"tanksquare-{self.ENV.lower()}-media"

    @property
    def google_maps_api_key(self) -> str:
        return get_secret(
            "GOOGLE_MAPS_API_KEY",
            gcp_secret_id="tanksquare-google-maps-api-key",
            project_id=self.GCP_PROJECT_ID,
        )

    @property
    def w3w_api_key(self) -> str:
        return get_secret(
            "W3W_API_KEY",
            gcp_secret_id="tanksquare-w3w-api-key",
            project_id=self.GCP_PROJECT_ID,
        )

    @property
    def session_signing_secret(self) -> str:
        return get_secret(
            "SESSION_SIGNING_SECRET",
            gcp_secret_id="tanksquare-session-signing-secret",
            project_id=self.GCP_PROJECT_ID,
            generate_ephemeral_if_missing=True,
        )

    @property
    def vendor_api_shared_secret(self) -> str:
        return get_secret(
            "VENDOR_API_SHARED_SECRET",
            gcp_secret_id="tanksquare-vendor-api-secret",
            project_id=self.GCP_PROJECT_ID,
            generate_ephemeral_if_missing=not self.is_prod,
        )

    @property
    def cors_origins(self) -> List[str]:
        if self.ALLOWED_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    def collection_name(self, base_name: str) -> str:
        """Return the environment-isolated Firestore collection name (`dev_vendors` vs `prod_vendors`)."""
        return f"{self.effective_collection_prefix}{base_name}"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
