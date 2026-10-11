"""
what3words On-Demand Resolution Router (`app/routers/w3w.py`).

Resolves any (lat, lng) or (parcel_center_lat, parcel_center_lng, row, col) into a 3m x 3m
what3words address (`///word1.word2.word3`) on demand without violating W3W database storage terms.
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Query

from app.services.geo_grid import format_cell_label, grid_cell_to_lat_lng
from app.services.w3w_service import resolve_w3w_sync

router = APIRouter(prefix="/api/v1/w3w", tags=["4. what3words On-Demand Resolver"])


@router.get("/convert-to-3wa")
def convert_coords_to_w3w(
    lat: float = Query(..., description="WGS84 latitude (or parcel center latitude if row/col provided)"),
    lng: float = Query(..., description="WGS84 longitude (or parcel center longitude if row/col provided)"),
    row: Optional[int] = Query(default=None, ge=0, le=50),
    col: Optional[int] = Query(default=None, ge=0, le=50),
) -> Dict[str, Any]:
    """
    Convert a WGS84 coordinate or a (row, col) cell on the 3m property grid into a
    what3words 3-word address on demand.
    """
    target_lat, target_lng = lat, lng
    cell_label = None
    if row is not None and col is not None:
        target_lat, target_lng = grid_cell_to_lat_lng(lat, lng, row, col)
        cell_label = format_cell_label(row, col)

    w3w = resolve_w3w_sync(target_lat, target_lng)
    return {
        "lat": target_lat,
        "lng": target_lng,
        "row": row,
        "col": col,
        "cell_label": cell_label,
        "w3w": w3w,
        "map_link": f"https://what3words.com/{w3w.lstrip('/')}",
    }
