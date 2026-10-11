"""
B2B Fuel Vendor & ERP Integration Router (`app/routers/vendors.py`).

Handles multi-vendor tenant onboarding, Plaid-style zero-login session token issuance,
strictly isolated site pass listings, and ERP-formatted exports (Cargas, ADD Systems, RCC, Destwin).
"""

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Request

from app.models import (
    SessionCreateRequest,
    SessionResponse,
    SitePass,
    VendorConfig,
    VendorCreateRequest,
)
from app.services.gcp_store import get_store

router = APIRouter(prefix="/api/v1/vendors", tags=["1. B2B Fuel Vendors & ERP Sync"])


@router.get("", response_model=List[VendorConfig])
def list_vendors() -> List[VendorConfig]:
    """List all registered propane and heating-oil vendor tenants."""
    store = get_store()
    return store.list_vendors()


@router.post("", response_model=VendorConfig, status_code=201)
def register_or_update_vendor(req: VendorCreateRequest) -> VendorConfig:
    """Register or update a propane/heating-oil provider tenant in GCP Firestore."""
    store = get_store()
    vendor = VendorConfig(
        vendor_id=req.vendor_id.strip().lower(),
        name=req.name,
        tagline=req.tagline or "Residential Fuel Delivery Portal",
        primary_color=req.primary_color or "#15803d",
        accent_color=req.accent_color or "#f97316",
        max_hose_ft=req.max_hose_ft,
        supported_fuels=req.supported_fuels,
        erp_system=req.erp_system,
        webhook_url=req.webhook_url,
        support_phone=req.support_phone or "1-800-555-TANK",
    )
    return store.upsert_vendor(vendor)


@router.get("/{vendor_id}", response_model=VendorConfig)
def get_vendor_config(vendor_id: str) -> VendorConfig:
    """Fetch branding and max-hose-length rules for a specific propane provider."""
    store = get_store()
    vendor = store.get_vendor(vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' not found")
    return vendor


@router.post("/{vendor_id}/sessions", response_model=SessionResponse, status_code=201)
def create_resident_session(
    vendor_id: str,
    req: SessionCreateRequest,
    request: Request,
) -> SessionResponse:
    """
    Issue a Plaid-style zero-login session token for a resident.
    - Residents NEVER create a TankSquare account (`resident_account_required=False`).
    - Residents are NEVER billed (`resident_billing_enabled=False`).
    """
    store = get_store()
    if not store.get_vendor(vendor_id):
        raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' not found")

    base_url = str(request.base_url).rstrip("/")
    return store.create_session(vendor_id=vendor_id, req=req, base_url=base_url)


@router.get("/{vendor_id}/sites", response_model=List[SitePass])
def list_vendor_sites(vendor_id: str) -> List[SitePass]:
    """List all customer TankSquare passes isolated strictly to `vendor_id`."""
    store = get_store()
    if not store.get_vendor(vendor_id):
        raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' not found")
    return store.list_site_passes(vendor_id=vendor_id)


@router.get("/{vendor_id}/erp-export")
def export_vendor_passes_for_erp(vendor_id: str) -> Dict[str, Any]:
    """
    Export all TankSquare passes for `vendor_id` formatted for their configured fuel ERP
    (Cargas Energy, ADD Systems E3/Raven, RCC MOGO, or Destwin).
    """
    store = get_store()
    vendor = store.get_vendor(vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' not found")

    passes = store.list_site_passes(vendor_id=vendor_id)
    records = []
    for sp in passes:
        records.append(
            {
                "erp_target": vendor.erp_system.value,
                "CustomerAccountID": sp.customer_account_id,
                "CustomerName": sp.customer_name,
                "ServiceAddress": sp.street_address,
                "FuelType": sp.fuel_type.value.upper(),
                "TankType": sp.tank_type.value,
                "TankSizeGallons": sp.tank_size_gallons,
                "TankSquare_W3W": sp.tank_square.w3w,
                "TankSquare_LatLng": f"{sp.tank_square.lat},{sp.tank_square.lng}",
                "PrimaryParking_P1_W3W": sp.park_p1_square.w3w,
                "PrimaryParking_P1_LatLng": f"{sp.park_p1_square.lat},{sp.park_p1_square.lng}",
                "ParkingVerificationStatus": sp.parking_status.value.upper(),
                "VerifiedByDriver": sp.verified_by_driver_id,
                "PracticalHosePullFeet": sp.hose_metrics.practical_pull_ft,
                "WithinBobtailReelLimit": sp.hose_metrics.within_limit,
                "NFPA58_LineOfSightClear": sp.hose_metrics.line_of_sight_clear,
                "GateCode": sp.gate_code or "",
                "DriverDispatchNotes": (
                    f"[TankSquare {sp.parking_status.value.upper()}] "
                    f"Tank: {sp.tank_square.w3w} | Park P1: {sp.park_p1_square.w3w} | "
                    f"Pull: {sp.hose_metrics.practical_pull_ft}ft / {vendor.max_hose_ft}ft max | "
                    f"Notes: {sp.access_notes or 'None'}"
                ),
                "PhotoURLs": [p.public_url for p in sp.photos],
                "LastUpdatedUTC": sp.updated_at,
            }
        )

    return {
        "vendor_id": vendor.vendor_id,
        "vendor_name": vendor.name,
        "erp_system": vendor.erp_system.value,
        "total_records": len(records),
        "records": records,
    }


@router.get("/{vendor_id}/webhooks")
def list_vendor_webhook_logs(vendor_id: str) -> Dict[str, Any]:
    """List outbound ERP webhook notifications dispatched for `vendor_id`."""
    store = get_store()
    if not store.get_vendor(vendor_id):
        raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' not found")
    logs = store.list_webhook_logs(vendor_id=vendor_id)
    return {"vendor_id": vendor_id, "count": len(logs), "webhook_events": logs}
