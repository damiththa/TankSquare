"""
Resident Zero-Login Portal & 3m Grid Router (`app/routers/resident.py`).

Powers Approach 1 (Resident Browser Widget / Portal):
- Zero account creation (`resident_account_required=False`)
- Zero resident billing (`resident_billing_enabled=False`)
- Address-to-3m-Parcel-Grid geocoding
- Live Waypoint-Aware Bobtail Hose-Reach Calculator (+15% slack + NFPA 58 line-of-sight)
- Saving TankSquare Pass to GCP Firestore (`parking_status="suggested"`)
- Uploading Tank/Driveway Photos to Google Cloud Storage (GCS)
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.models import (
    GridSquareCoord,
    HoseCalculationRequest,
    HoseCalculationResponse,
    ParkingStatus,
    PhotoCategory,
    SitePass,
    SitePassUpdateRequest,
    SitePhoto,
)
from app.services.gcp_store import get_store
from app.services.geo_grid import (
    autocomplete_addresses,
    calculate_hose_reach,
    format_cell_label,
    geocode_address_to_parcel,
    grid_cell_to_lat_lng,
)
from app.services.w3w_service import resolve_w3w_sync

router = APIRouter(prefix="/api/v1/resident", tags=["2. Resident Zero-Login Portal & 3m Grid"])


class GeocodeAddressRequest(BaseModel):
    street_address: str
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None
    fallback_lat: Optional[float] = None
    fallback_lng: Optional[float] = None


@router.get("/autocomplete")
def autocomplete_resident_address(q: str = "", limit: int = 5) -> Dict[str, Any]:
    """
    Split-Provider Stage 1: Zero-cost type-ahead address autocomplete (Local Catalog + Photon/OSM).
    Consumes 0 Google Maps API quota calls while typing; the selected address is then passed
    to `POST /api/v1/resident/geocode` (Stage 2) for Google Maps rooftop precision.
    """
    return autocomplete_addresses(query=q, limit=max(1, min(limit, 8)))


@router.get("/session/{token}")
def get_resident_session_context(token: str) -> Dict[str, Any]:
    """
    Resolve a resident's zero-login session token (from `<script>` tag or SMS magic link).
    Returns vendor branding, parcel layout, and the existing TankSquare SitePass if saved.
    """
    store = get_store()
    session = store.get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session token '{token}' not found or expired")

    vendor = store.get_vendor(session.vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail=f"Vendor '{session.vendor_id}' not found")

    site_pass = store.get_site_pass(session.site_id)
    parcel = geocode_address_to_parcel(session.street_address)

    return {
        "session": session.model_dump(),
        "vendor": vendor.model_dump(),
        "parcel": parcel,
        "site_pass": site_pass.model_dump() if site_pass else None,
        "guarantees": {
            "resident_account_required": False,
            "resident_billing_enabled": False,
            "browser_only_zero_install": True,
        },
    }


@router.post("/geocode")
def geocode_resident_address(req: GeocodeAddressRequest) -> Dict[str, Any]:
    """
    Split-Provider Stage 2: Convert a selected street address (or optional phone browser GPS coordinates)
    into a centered 25x16 grid of 3m x 3m squares using Google Maps Rooftop Geocoding (within free-tier cap)
    with automatic fallback to Stage 1 autocomplete coordinates.
    """
    parcel = geocode_address_to_parcel(
        req.street_address,
        fallback_lat=req.fallback_lat,
        fallback_lng=req.fallback_lng,
    )
    if req.gps_lat is not None and req.gps_lng is not None:
        parcel["parcel_center_lat"] = round(req.gps_lat, 6)
        parcel["parcel_center_lng"] = round(req.gps_lng, 6)
        parcel["gps_override_active"] = True
    return parcel


@router.post("/calculate-hose", response_model=HoseCalculationResponse)
def compute_live_hose_reach(req: HoseCalculationRequest) -> HoseCalculationResponse:
    """
    Calculate real-time bobtail hose reach in feet between Suggested Parking (P1)
    and Tank (T), routing through any corner waypoints and adding +15% practical slack.
    """
    return calculate_hose_reach(
        tank_square=req.tank_square,
        park_p1_square=req.park_p1_square,
        vendor_max_hose_ft=req.vendor_max_hose_ft,
        park_p2_square=req.park_p2_square,
        hose_waypoints=req.hose_waypoints,
        hazard_squares=req.hazard_squares,
    )


@router.put("/session/{token}/pass", response_model=SitePass)
def save_resident_tanksquare_pass(token: str, req: SitePassUpdateRequest) -> SitePass:
    """
    Save the resident's TankSquare Pass directly to Google Cloud Firestore.
    - Resolves `what3words` addresses on-demand for Tank, P1, P2, Waypoints, and Hazards.
    - Sets `parking_status = "suggested"` (Pending CDL Driver Verification on next delivery).
    - Dispatches real-time ERP webhook notification to the propane provider.
    """
    store = get_store()
    session = store.get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session token '{token}' not found")

    vendor = store.get_vendor(session.vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail=f"Vendor '{session.vendor_id}' not found")

    existing = store.get_site_pass(session.site_id)
    address = req.street_address or (existing.street_address if existing else session.street_address)
    parcel = geocode_address_to_parcel(address)
    c_lat = req.parcel_center_lat or parcel["parcel_center_lat"]
    c_lng = req.parcel_center_lng or parcel["parcel_center_lng"]

    # Build Tank Square
    t_lat, t_lng = grid_cell_to_lat_lng(c_lat, c_lng, req.tank_row, req.tank_col)
    tank_sq = GridSquareCoord(
        row=req.tank_row,
        col=req.tank_col,
        label=format_cell_label(req.tank_row, req.tank_col),
        lat=t_lat,
        lng=t_lng,
        w3w=resolve_w3w_sync(t_lat, t_lng),
    )

    # Build Suggested Primary Parking (P1) Square
    p1_lat, p1_lng = grid_cell_to_lat_lng(c_lat, c_lng, req.park_p1_row, req.park_p1_col)
    p1_sq = GridSquareCoord(
        row=req.park_p1_row,
        col=req.park_p1_col,
        label=format_cell_label(req.park_p1_row, req.park_p1_col),
        lat=p1_lat,
        lng=p1_lng,
        w3w=resolve_w3w_sync(p1_lat, p1_lng),
    )

    # Build Optional Winter Backup Parking (P2) Square
    p2_sq: Optional[GridSquareCoord] = None
    if req.park_p2_row is not None and req.park_p2_col is not None:
        p2_lat, p2_lng = grid_cell_to_lat_lng(c_lat, c_lng, req.park_p2_row, req.park_p2_col)
        p2_sq = GridSquareCoord(
            row=req.park_p2_row,
            col=req.park_p2_col,
            label=format_cell_label(req.park_p2_row, req.park_p2_col),
            lat=p2_lat,
            lng=p2_lng,
            w3w=resolve_w3w_sync(p2_lat, p2_lng),
        )

    # Build Hose Waypoints
    waypoints: List[GridSquareCoord] = []
    for wp in req.waypoint_coords:
        w_r, w_c = int(wp["row"]), int(wp["col"])
        w_lat, w_lng = grid_cell_to_lat_lng(c_lat, c_lng, w_r, w_c)
        waypoints.append(
            GridSquareCoord(
                row=w_r,
                col=w_c,
                label=format_cell_label(w_r, w_c),
                lat=w_lat,
                lng=w_lng,
                w3w=resolve_w3w_sync(w_lat, w_lng),
            )
        )

    # Build Septic / Soft-Ground Hazard Squares
    hazards: List[GridSquareCoord] = []
    for hz in req.hazard_coords:
        h_r, h_c = int(hz["row"]), int(hz["col"])
        h_lat, h_lng = grid_cell_to_lat_lng(c_lat, c_lng, h_r, h_c)
        hazards.append(
            GridSquareCoord(
                row=h_r,
                col=h_c,
                label=format_cell_label(h_r, h_c),
                lat=h_lat,
                lng=h_lng,
                w3w=resolve_w3w_sync(h_lat, h_lng),
            )
        )

    hose_metrics = calculate_hose_reach(
        tank_square=tank_sq,
        park_p1_square=p1_sq,
        vendor_max_hose_ft=vendor.max_hose_ft,
        park_p2_square=p2_sq,
        hose_waypoints=waypoints,
        hazard_squares=hazards,
    )

    site_pass = SitePass(
        site_id=session.site_id,
        vendor_id=session.vendor_id,
        customer_account_id=session.customer_account_id,
        customer_name=session.customer_name,
        street_address=address,
        parcel_center_lat=c_lat,
        parcel_center_lng=c_lng,
        fuel_type=req.fuel_type or session.fuel_type,
        tank_type=req.tank_type or session.tank_type,
        tank_size_gallons=req.tank_size_gallons or session.tank_size_gallons,
        tank_square=tank_sq,
        park_p1_square=p1_sq,
        park_p2_square=p2_sq,
        hose_waypoints=waypoints,
        hazard_squares=hazards,
        hose_metrics=hose_metrics,
        parking_status=ParkingStatus.SUGGESTED,  # Always 'suggested' until verified by CDL driver
        driveway_weight_acknowledged=req.driveway_weight_acknowledged,
        gate_code=req.gate_code,
        pets_warning=req.pets_warning,
        access_notes=req.access_notes,
        photos=existing.photos if existing else [],
    )
    return store.save_site_pass(site_pass)


@router.post("/session/{token}/photos", response_model=SitePhoto, status_code=201)
async def upload_resident_site_photo(
    token: str,
    category: PhotoCategory = Form(default=PhotoCategory.TANK_DOME),
    caption: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
) -> SitePhoto:
    """Upload a tank/driveway photo to Google Cloud Storage (GCS) and attach to the SitePass."""
    store = get_store()
    session = store.get_session(token)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session token '{token}' not found")

    site_pass = store.get_site_pass(session.site_id)
    if not site_pass:
        raise HTTPException(status_code=404, detail="Save or initialize the site pass before uploading photos")

    content_bytes = await file.read()
    photo = store.upload_site_photo(
        site_id=session.site_id,
        vendor_id=session.vendor_id,
        category=category,
        filename=file.filename or "site_photo.jpg",
        content_bytes=content_bytes,
        content_type=file.content_type or "image/jpeg",
        caption=caption,
    )
    site_pass.photos.append(photo)
    store.save_site_pass(site_pass)
    return photo
