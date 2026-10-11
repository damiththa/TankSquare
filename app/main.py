"""
TankSquare - Main FastAPI Application Entrypoint (`app/main.py`).

Cloud-Direct on Google Cloud Platform (Cloud Run + Cloud Firestore + Cloud Storage).
Zero SQLite, Zero Resident Account Creation, Zero Resident Billing, 100% Browser-Based.
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

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.API_VERSION,
    description=(
        "Multi-Vendor B2B SaaS & Plaid-Style `<script>` Browser Grid Extension for US Propane "
        "and Heating-Oil Providers. Built directly on Google Cloud Platform (Cloud Run, "
        "Cloud Firestore, Cloud Storage, Google Maps Platform, and what3words API)."
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
    """Cloud Run readiness/liveness probe and active GCP environment summary."""
    store = get_store()
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "version": settings.API_VERSION,
        "environment": settings.ENV,
        "is_prod": settings.is_prod,
        "gcp_project_id": settings.GCP_PROJECT_ID,
        "firestore_collection_prefix": settings.FIRESTORE_COLLECTION_PREFIX,
        "gcs_bucket": settings.GCS_BUCKET_NAME,
        "gcp_live_adc_connected": store.gcp_live_connected,
        "sqlite_used": False,
        "resident_account_required": settings.RESIDENT_ACCOUNT_REQUIRED,
        "resident_billing_enabled": settings.RESIDENT_BILLING_ENABLED,
    }


@app.get("/api/v1/config/public", tags=["0. System & GCP Environment"])
def get_public_browser_config() -> Dict[str, Any]:
    """Return safe public configuration for the 100% browser-based frontends (`index.html`, `driver.html`, `widget.js`)."""
    store = get_store()
    return {
        "environment": settings.ENV.upper(),
        "gcp_project_id": settings.GCP_PROJECT_ID,
        "google_maps_configured": bool(settings.GOOGLE_MAPS_API_KEY),
        "w3w_live_api_configured": bool(settings.W3W_API_KEY),
        "resident_account_required": False,
        "resident_billing_enabled": False,
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
