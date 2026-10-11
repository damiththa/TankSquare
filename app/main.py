"""
TankSquare - Main FastAPI Application Entrypoint (`app/main.py`).

Cloud-Direct on Google Cloud Platform (Cloud Run + Cloud Firestore + Cloud Storage + Secret Manager).
Zero SQLite, Zero Hardcoded Secrets, Zero Resident Account Creation, Zero Resident Billing.
"""

import os
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import driver, resident, vendors, w3w
from app.services.gcp_store import get_store
from app.services.geo_grid import get_maps_free_tier_status

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.API_VERSION,
    description=(
        "Multi-Vendor B2B SaaS & Plaid-Style `<script>` Browser Grid Extension for US Propane "
        "and Heating-Oil Providers. Built directly on Google Cloud Platform (Cloud Run, "
        "Cloud Firestore, Cloud Storage, Secret Manager, Google Maps Platform, and what3words API)."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(vendors.router)
app.include_router(resident.router)
app.include_router(driver.router)
app.include_router(w3w.router)

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/api/v1/health", tags=["0. System & GCP Environment"])
def health_check() -> Dict[str, Any]:
    """Cloud Run readiness/liveness probe, active GCP environment, and Free-Tier hard cap status."""
    store = get_store()
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "version": settings.API_VERSION,
        "environment": settings.ENV,
        "is_prod": settings.is_prod,
        "gcp_project_configured": bool(settings.GCP_PROJECT_ID),
        "firestore_collection_prefix": settings.effective_collection_prefix,
        "gcs_bucket": settings.effective_gcs_bucket,
        "gcp_live_adc_connected": store.gcp_live_connected,
        "secret_manager_enabled": settings.USE_GCP_SECRET_MANAGER,
        "sqlite_used": False,
        "resident_account_required": settings.RESIDENT_ACCOUNT_REQUIRED,
        "resident_billing_enabled": settings.RESIDENT_BILLING_ENABLED,
        "maps_free_tier_guardrail": get_maps_free_tier_status(),
    }


@app.get("/api/v1/config/public", tags=["0. System & GCP Environment"])
def get_public_browser_config() -> Dict[str, Any]:
    """Return safe public configuration for the 100% browser-based frontends (never exposes raw secret keys)."""
    store = get_store()
    return {
        "environment": settings.ENV.upper(),
        "gcp_project_configured": bool(settings.GCP_PROJECT_ID),
        "google_maps_configured": bool(settings.google_maps_api_key),
        "w3w_live_api_configured": bool(settings.w3w_api_key),
        "resident_account_required": False,
        "resident_billing_enabled": False,
        "maps_free_tier_guardrail": get_maps_free_tier_status(),
        "available_vendors": [v.model_dump() for v in store.list_vendors()],
    }


@app.get("/", include_in_schema=False)
def serve_resident_portal() -> FileResponse:
    """Serve Approach 1: 100% Browser-Based Resident Portal & Multi-Vendor `<script>` Widget."""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/driver", include_in_schema=False)
def serve_driver_mobile_view() -> FileResponse:
    """Serve Approach 2: 100% Mobile-Browser Tanker Driver View & Parking Verification."""
    return FileResponse(os.path.join(STATIC_DIR, "driver.html"))
