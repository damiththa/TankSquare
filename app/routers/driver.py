"""
Tanker Driver Mobile Browser & Parking Verification Router (`app/routers/driver.py`).

Powers Approach 2 (Fuel Truck Driver Mobile Browser View):
- Lists daily route delivery passes for a vendor.
- Supports offline Service Worker pre-caching for rural dead zones.
- Implements the 'Suggested Parking' -> 'Driver-Verified Parking' workflow so CDL drivers
  can either confirm the resident's suggested parking square (P1) with 1 tap or relocate P1
  to the actual safe square where the 33,000-lb bobtail parked.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Query

from app.models import (
    DriverVerifyParkingRequest,
    GridSquareCoord,
    ParkingStatus,
    SitePass,
)
from app.services.gcp_store import get_store
from app.services.geo_grid import (
    calculate_hose_reach,
    format_cell_label,
    grid_cell_to_lat_lng,
)
from app.services.w3w_service import resolve_w3w_sync

router = APIRouter(prefix="/api/v1/driver", tags=["3. Tanker Driver Mobile View & Parking Verification"])


@router.get("/routes")
def get_driver_route_passes(
    vendor_id: Optional[str] = Query(default=None, description="Filter route stops by fuel vendor_id"),
) -> Dict[str, Any]:
    """
    Fetch all active delivery stops and their complete TankSquare SitePasses.
    Designed to be cached in the browser's Service Worker (`sw.js`) at morning dispatch
    so drivers have full access in rural zero-bars cell dead zones.
    """
    store = get_store()
    passes = store.list_site_passes(vendor_id=vendor_id)
    return {
        "vendor_id_filter": vendor_id,
        "total_stops": len(passes),
        "offline_cache_ready": True,
        "stops": [p.model_dump() for p in passes],
    }


@router.get("/pass/{site_id}", response_model=SitePass)
def get_driver_site_pass(site_id: str) -> SitePass:
    """Fetch a single property's TankSquare Pass for the fuel truck driver's mobile browser."""
    store = get_store()
    site_pass = store.get_site_pass(site_id)
    if not site_pass:
        raise HTTPException(status_code=404, detail=f"SitePass '{site_id}' not found")
    return site_pass


@router.post("/pass/{site_id}/verify-parking", response_model=SitePass)
def verify_or_adjust_suggested_parking(
    site_id: str,
    req: DriverVerifyParkingRequest,
) -> SitePass:
    """
    Upgrade a resident's 'Suggested Parking' (`parking_status='suggested'`) to
    'Driver-Verified Parking' (`parking_status='driver_verified'`).

    - If `action == 'confirm'`, confirms the existing P1 square as safe for a 33,000-lb tanker.
    - If `action == 'adjust'`, updates P1 to `(adjusted_p1_row, adjusted_p1_col)`, resolves the new
      `what3words` address, recalculates hose reach, and marks `driver_verified`.
    """
    store = get_store()
    site_pass = store.get_site_pass(site_id)
    if not site_pass:
        raise HTTPException(status_code=404, detail=f"SitePass '{site_id}' not found")

    vendor = store.get_vendor(site_pass.vendor_id)
    max_hose_ft = vendor.max_hose_ft if vendor else 150

    if req.action.lower() == "adjust":
        if req.adjusted_p1_row is None or req.adjusted_p1_col is None:
            raise HTTPException(
                status_code=400,
                detail="adjusted_p1_row and adjusted_p1_col are required when action='adjust'",
            )
        new_lat, new_lng = grid_cell_to_lat_lng(
            site_pass.parcel_center_lat,
            site_pass.parcel_center_lng,
            req.adjusted_p1_row,
            req.adjusted_p1_col,
        )
        site_pass.park_p1_square = GridSquareCoord(
            row=req.adjusted_p1_row,
            col=req.adjusted_p1_col,
            label=format_cell_label(req.adjusted_p1_row, req.adjusted_p1_col),
            lat=new_lat,
            lng=new_lng,
            w3w=resolve_w3w_sync(new_lat, new_lng),
        )
        site_pass.hose_metrics = calculate_hose_reach(
            tank_square=site_pass.tank_square,
            park_p1_square=site_pass.park_p1_square,
            vendor_max_hose_ft=max_hose_ft,
            park_p2_square=site_pass.park_p2_square,
            hose_waypoints=site_pass.hose_waypoints,
            hazard_squares=site_pass.hazard_squares,
        )

    site_pass.parking_status = ParkingStatus.DRIVER_VERIFIED
    site_pass.verified_by_driver_id = req.driver_id
    site_pass.verified_at = datetime.utcnow().isoformat() + "Z"
    site_pass.driver_verification_notes = (
        req.driver_notes
        or f"Verified safe bobtail parking at {site_pass.park_p1_square.label} ({site_pass.park_p1_square.w3w})"
    )

    return store.save_site_pass(site_pass)
