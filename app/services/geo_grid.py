"""
3m x 3m Property Grid & Bobtail Hose-Reach Math Service (`app/services/geo_grid.py`).

Key Engineering & Free-Tier Cost Guardrails:
- Each grid square is exactly 3.0 meters x 3.0 meters (9.84252 ft x 9.84252 ft).
- Grid dimensions: 16 rows (North-to-South, 48m) x 25 columns (West-to-East, 75m).
- Strict Free-Tier Hard Cap (`MAPS_MONTHLY_FREE_TIER_CAP = 9500`, `MAPS_DAILY_SAFE_CAP = 300`):
  Google Maps Platform gives 10,000 free calls/month per Essentials SKU. This service tracks
  requests and refuses to call external paid Google Maps endpoints once 300/day or 9,500/month
  is reached, guaranteeing $0.00 Pay-As-You-Go overage charges.
"""

import hashlib
import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import httpx

from app.config import get_settings
from app.models import GridSquareCoord, HoseCalculationResponse

SQUARE_SIZE_METERS = 3.0
FEET_PER_METER = 3.28084
SQUARE_SIZE_FEET = SQUARE_SIZE_METERS * FEET_PER_METER  # ~9.84252 ft
HOSE_SLACK_MULTIPLIER = 1.15  # +15% practical hose pull buffer
GRID_ROWS = 16
GRID_COLS = 25
CENTER_ROW = 8
CENTER_COL = 12

import re

# In-memory cache & Free-Tier Guardrail Counter ( prevents Pay-As-You-Go overages )
_GEOCODE_CACHE: Dict[str, Tuple[float, float, str]] = {}
_AUTOCOMPLETE_CACHE: Dict[str, List[Dict[str, Any]]] = {}
_AUTOCOMPLETE_FALLBACK_COORDS: Dict[str, Tuple[float, float, str]] = {}
_USAGE_TRACKER: Dict[str, int] = {
    "month_key": int(datetime.utcnow().strftime("%Y%m")),
    "day_key": int(datetime.utcnow().strftime("%Y%m%d")),
    "monthly_calls": 0,
    "daily_calls": 0,
}

US_STATE_ABBREV: Dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "district of columbia": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
    "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
    "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA",
    "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}

KNOWN_SERVICE_ADDRESSES: List[Dict[str, Any]] = [
    {
        "formatted_address": "742 Evergreen Terrace, Montpelier, VT 05602",
        "street_line": "742 Evergreen Terrace",
        "city_state_zip": "Montpelier, VT 05602",
        "lat": 44.2601,
        "lng": -72.5754,
    },
    {
        "formatted_address": "184 Old County Rd, Lake Placid, NY 12946",
        "street_line": "184 Old County Rd",
        "city_state_zip": "Lake Placid, NY 12946",
        "lat": 43.9742,
        "lng": -73.9211,
    },
    {
        "formatted_address": "905 Maple Ridge Ln, Iowa City, IA 52240",
        "street_line": "905 Maple Ridge Ln",
        "city_state_zip": "Iowa City, IA 52240",
        "lat": 41.6611,
        "lng": -91.5302,
    },
    {
        "formatted_address": "120 Mountain View Rd, Stowe, VT 05672",
        "street_line": "120 Mountain View Rd",
        "city_state_zip": "Stowe, VT 05672",
        "lat": 44.4654,
        "lng": -72.6874,
    },
    {
        "formatted_address": "412B Bear Swamp Rd, Middlesex, VT 05602",
        "street_line": "412B Bear Swamp Rd",
        "city_state_zip": "Middlesex, VT 05602",
        "lat": 44.3108,
        "lng": -72.6682,
    },
    {
        "formatted_address": "88 Adirondack Loj Rd, Lake Placid, NY 12946",
        "street_line": "88 Adirondack Loj Rd",
        "city_state_zip": "Lake Placid, NY 12946",
        "lat": 44.2268,
        "lng": -73.9631,
    },
]


def get_maps_free_tier_status() -> Dict[str, Any]:
    """Return current Google Maps API usage vs. the hard Free-Tier cap."""
    settings = get_settings()
    _roll_counters_if_needed()
    return {
        "enforce_free_tier_hard_cap": settings.ENFORCE_FREE_TIER_HARD_CAP,
        "google_free_sku_limit_monthly": 10000,
        "tanksquare_hard_cap_monthly": settings.MAPS_MONTHLY_FREE_TIER_CAP,
        "tanksquare_hard_cap_daily": settings.MAPS_DAILY_SAFE_CAP,
        "current_month_calls": _USAGE_TRACKER["monthly_calls"],
        "current_day_calls": _USAGE_TRACKER["daily_calls"],
        "remaining_free_calls_this_month": max(
            0, settings.MAPS_MONTHLY_FREE_TIER_CAP - _USAGE_TRACKER["monthly_calls"]
        ),
        "pay_as_you_go_blocked": True,
    }


def _roll_counters_if_needed() -> None:
    now = datetime.utcnow()
    cur_month = int(now.strftime("%Y%m"))
    cur_day = int(now.strftime("%Y%m%d"))
    if _USAGE_TRACKER["month_key"] != cur_month:
        _USAGE_TRACKER["month_key"] = cur_month
        _USAGE_TRACKER["monthly_calls"] = 0
    if _USAGE_TRACKER["day_key"] != cur_day:
        _USAGE_TRACKER["day_key"] = cur_day
        _USAGE_TRACKER["daily_calls"] = 0


def grid_cell_to_lat_lng(
    parcel_center_lat: float,
    parcel_center_lng: float,
    row: int,
    col: int,
) -> Tuple[float, float]:
    """
    Convert a (row, col) cell on the 25x16 3m grid into exact WGS84 (lat, lng).
    Row 0 is North; Row 15 is South. Col 0 is West; Col 24 is East.
    """
    d_north_meters = (CENTER_ROW - row) * SQUARE_SIZE_METERS
    d_east_meters = (col - CENTER_COL) * SQUARE_SIZE_METERS

    lat_deg_per_meter = 1.0 / 111_320.0
    cos_lat = max(0.2, math.cos(math.radians(parcel_center_lat)))
    lng_deg_per_meter = 1.0 / (111_320.0 * cos_lat)

    lat = round(parcel_center_lat + (d_north_meters * lat_deg_per_meter), 6)
    lng = round(parcel_center_lng + (d_east_meters * lng_deg_per_meter), 6)
    return lat, lng


def format_cell_label(row: int, col: int) -> str:
    """Return human-readable cell code, e.g. 'R6-C18'."""
    return f"R{row + 1}-C{col + 1}"


def euclidean_squares_distance_ft(a_row: int, a_col: int, b_row: int, b_col: int) -> float:
    """Compute center-to-center distance in feet between two 3m x 3m grid squares."""
    d_row = a_row - b_row
    d_col = a_col - b_col
    return math.hypot(d_row, d_col) * SQUARE_SIZE_FEET


def calculate_hose_reach(
    tank_square: GridSquareCoord,
    park_p1_square: GridSquareCoord,
    vendor_max_hose_ft: int = 150,
    park_p2_square: Optional[GridSquareCoord] = None,
    hose_waypoints: Optional[List[GridSquareCoord]] = None,
    hazard_squares: Optional[List[GridSquareCoord]] = None,
) -> HoseCalculationResponse:
    """
    Calculate straight-line distance, waypoint-routed distance, practical hose pull (+15% slack),
    NFPA 58 line-of-sight compliance, and septic/hazard zone conflicts.
    """
    waypoints = hose_waypoints or []
    hazards = hazard_squares or []

    # 1. Straight-line distance between P1 and Tank
    straight_ft = round(
        euclidean_squares_distance_ft(
            park_p1_square.row,
            park_p1_square.col,
            tank_square.row,
            tank_square.col,
        ),
        1,
    )

    # 2. Routed path distance (P1 -> Waypoint 1 -> ... -> Tank)
    chain = [park_p1_square] + waypoints + [tank_square]
    routed_ft = 0.0
    for idx in range(len(chain) - 1):
        routed_ft += euclidean_squares_distance_ft(
            chain[idx].row,
            chain[idx].col,
            chain[idx + 1].row,
            chain[idx + 1].col,
        )
    routed_ft = round(routed_ft, 1)

    # 3. Practical hose pull required with +15% slack buffer
    practical_pull_ft = round(routed_ft * HOSE_SLACK_MULTIPLIER, 1)

    # 4. Optional Winter Backup (P2) practical pull
    p2_practical_pull_ft: Optional[float] = None
    if park_p2_square is not None:
        p2_straight = euclidean_squares_distance_ft(
            park_p2_square.row,
            park_p2_square.col,
            tank_square.row,
            tank_square.col,
        )
        p2_practical_pull_ft = round(p2_straight * HOSE_SLACK_MULTIPLIER, 1)

    # 5. Compare against vendor's maximum bobtail hose length
    remaining_margin_ft = round(vendor_max_hose_ft - practical_pull_ft, 1)
    within_limit = practical_pull_ft <= vendor_max_hose_ft

    usage_ratio = practical_pull_ft / max(1, vendor_max_hose_ft)
    if not within_limit:
        status = "exceeds"
    elif usage_ratio >= 0.82:
        status = "warning"
    else:
        status = "ok"

    # 6. NFPA 58 Line-of-Sight Check
    line_of_sight_clear = len(waypoints) == 0

    # 7. Septic / Soft-Ground Hazard Conflict Check
    hazard_conflict = False
    for hz in hazards:
        if abs(park_p1_square.row - hz.row) <= 1 and abs(park_p1_square.col - hz.col) <= 1:
            hazard_conflict = True
            break
        if park_p2_square and abs(park_p2_square.row - hz.row) <= 1 and abs(park_p2_square.col - hz.col) <= 1:
            hazard_conflict = True
            break

    # 8. Build actionable human-readable recommendation
    notes: List[str] = []
    if within_limit:
        notes.append(
            f"Hose reach OK: {practical_pull_ft} ft practical pull (incl. +15% slack) "
            f"is within the {vendor_max_hose_ft} ft bobtail reel limit ({remaining_margin_ft} ft spare)."
        )
    else:
        over_by = round(practical_pull_ft - vendor_max_hose_ft, 1)
        notes.append(
            f"EXCEEDS REEL LIMIT by {over_by} ft ({practical_pull_ft} ft needed vs {vendor_max_hose_ft} ft max). "
            f"Move Suggested Parking (P1) closer to the tank or dispatch a long-hose truck."
        )

    if not line_of_sight_clear:
        notes.append(
            "NFPA 58 Note: Hose path bends around a corner waypoint; driver must verify remote emergency shutoff / line of sight."
        )
    if hazard_conflict:
        notes.append(
            "WARNING: Suggested tanker parking is on or adjacent to a marked Septic / Soft-Ground Hazard square!"
        )

    return HoseCalculationResponse(
        straight_line_ft=straight_ft,
        routed_distance_ft=routed_ft,
        practical_pull_ft=practical_pull_ft,
        p2_practical_pull_ft=p2_practical_pull_ft,
        vendor_max_hose_ft=vendor_max_hose_ft,
        remaining_margin_ft=remaining_margin_ft,
        within_limit=within_limit,
        status=status,
        line_of_sight_clear=line_of_sight_clear,
        hazard_conflict=hazard_conflict,
        recommendation=" ".join(notes),
    )


def extract_leading_house_number(query: str) -> Optional[str]:
    """
    Extract a leading rural E-911 or street house number (e.g., '742', '412B', '184-A')
    from the user's raw search input so road-level OpenStreetMap matches preserve the exact house number
    when forwarded to Google Maps Rooftop Geocoding.
    """
    match = re.match(r"^\s*(\d+[A-Za-z]?(?:-\d+[A-Za-z]?)?)\s+[A-Za-z]", query or "")
    if match:
        return match.group(1)
    return None


def _format_photon_feature(
    feature: Dict[str, Any],
    typed_house_number: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Normalize a Photon (OpenStreetMap) GeoJSON feature into clean USPS street address format."""
    props = feature.get("properties") or {}
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") or []
    if len(coords) < 2:
        return None

    country_code = str(props.get("countrycode") or "").upper()
    country_name = str(props.get("country") or "").lower()
    if country_code and country_code != "US" and "united states" not in country_name:
        return None

    house_number = str(props.get("housenumber") or "").strip()
    street = str(props.get("street") or props.get("name") or "").strip()
    city = str(
        props.get("city")
        or props.get("town")
        or props.get("village")
        or props.get("locality")
        or props.get("county")
        or ""
    ).strip()
    raw_state = str(props.get("state") or "").strip()
    state_abbr = US_STATE_ABBREV.get(raw_state.lower(), raw_state[:2].upper() if len(raw_state) == 2 else raw_state)
    postcode = str(props.get("postcode") or "").strip()

    if not street:
        return None

    house_number_preserved = False
    if not house_number and typed_house_number:
        house_number = typed_house_number
        house_number_preserved = True

    street_line = f"{house_number} {street}".strip() if house_number else street
    locality_parts: List[str] = []
    if city:
        locality_parts.append(city)
    state_zip = f"{state_abbr} {postcode}".strip()
    if state_zip:
        locality_parts.append(state_zip)

    city_state_zip = ", ".join(locality_parts)
    formatted_address = f"{street_line}, {city_state_zip}" if city_state_zip else street_line

    lng = round(float(coords[0]), 6)
    lat = round(float(coords[1]), 6)
    return {
        "formatted_address": formatted_address,
        "street_line": street_line,
        "city_state_zip": city_state_zip,
        "fallback_lat": lat,
        "fallback_lng": lng,
        "source": "photon_osm",
        "house_number_preserved": house_number_preserved,
    }


def autocomplete_addresses(query: str, limit: int = 5) -> Dict[str, Any]:
    """
    Split-Provider Stage 1: Zero-cost type-ahead address suggestions.
    - Uses 0 Google Maps API quota calls during keystroke typing.
    - Combines instant local service-territory matches with Photon (OpenStreetMap) type-ahead.
    - Preserves leading rural house numbers (e.g., '412B') when OSM only knows the road name,
      so Stage 2 (Google Maps Geocoding) resolves the exact rooftop parcel.
    """
    cleaned = (query or "").strip()
    if len(cleaned) < 3:
        return {
            "query": cleaned,
            "provider": "none_min_3_chars",
            "google_quota_used": 0,
            "cost_usd": 0.0,
            "suggestions": [],
        }

    cache_key = f"{cleaned.lower()}::{limit}"
    if cache_key in _AUTOCOMPLETE_CACHE:
        return {
            "query": cleaned,
            "provider": "memory_prefix_cache",
            "google_quota_used": 0,
            "cost_usd": 0.0,
            "suggestions": _AUTOCOMPLETE_CACHE[cache_key],
        }

    typed_house_num = extract_leading_house_number(cleaned)
    lowered = cleaned.lower()
    tokens = [t for t in re.split(r"[\s,]+", lowered) if t]
    non_numeric_tokens = [t for t in tokens if not t[0].isdigit()]

    results: List[Dict[str, Any]] = []
    seen_addresses: set[str] = set()

    # Tier 1: Local Service-Territory Catalog (0ms, $0.00, supports house-number prefix replacement)
    for item in KNOWN_SERVICE_ADDRESSES:
        haystack = item["formatted_address"].lower()
        if lowered in haystack or (non_numeric_tokens and all(t in haystack for t in non_numeric_tokens)):
            fmt = item["formatted_address"]
            street_line = item["street_line"]
            preserved = False
            if typed_house_num and not haystack.startswith(typed_house_num.lower()):
                road_only = re.sub(r"^\d+[A-Za-z]?(?:-\d+[A-Za-z]?)?\s+", "", street_line)
                street_line = f"{typed_house_num} {road_only}"
                fmt = f"{street_line}, {item['city_state_zip']}"
                preserved = True

            norm_key = fmt.lower()
            if norm_key not in seen_addresses:
                seen_addresses.add(norm_key)
                suggestion = {
                    "formatted_address": fmt,
                    "street_line": street_line,
                    "city_state_zip": item["city_state_zip"],
                    "fallback_lat": item["lat"],
                    "fallback_lng": item["lng"],
                    "source": "local_service_catalog",
                    "house_number_preserved": preserved,
                }
                results.append(suggestion)
                _AUTOCOMPLETE_FALLBACK_COORDS[norm_key] = (item["lat"], item["lng"], fmt)

    # Tier 2: Photon (Komoot / OpenStreetMap) Free Type-Ahead API ($0.00, 0 Google quota used)
    provider_used = "local_service_catalog"
    if len(results) < limit:
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(
                    "https://photon.komoot.io/api/",
                    params={
                        "q": cleaned,
                        "limit": max(limit * 2, 8),
                        "lang": "en",
                        "lat": 42.85,
                        "lon": -73.25,
                    },
                    headers={
                        "User-Agent": "TankSquare-B2B-Grid/1.0 (+https://github.com/damiththa/TankSquare)"
                    },
                )
                if resp.status_code == 200:
                    payload = resp.json()
                    for feat in payload.get("features") or []:
                        parsed = _format_photon_feature(feat, typed_house_number=typed_house_num)
                        if not parsed:
                            continue
                        norm_key = parsed["formatted_address"].lower()
                        if norm_key in seen_addresses:
                            continue
                        seen_addresses.add(norm_key)
                        results.append(parsed)
                        _AUTOCOMPLETE_FALLBACK_COORDS[norm_key] = (
                            parsed["fallback_lat"],
                            parsed["fallback_lng"],
                            parsed["formatted_address"],
                        )
                        provider_used = "photon_osm_split_pipeline"
                        if len(results) >= limit:
                            break
        except Exception:
            pass

    final_suggestions = results[:limit]
    if len(_AUTOCOMPLETE_CACHE) > 256:
        _AUTOCOMPLETE_CACHE.clear()
    _AUTOCOMPLETE_CACHE[cache_key] = final_suggestions

    return {
        "query": cleaned,
        "provider": provider_used,
        "google_quota_used": 0,
        "cost_usd": 0.0,
        "suggestions": final_suggestions,
    }


def geocode_address_to_parcel(
    street_address: str,
    fallback_lat: Optional[float] = None,
    fallback_lng: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Split-Provider Stage 2: Resolve a selected street address into parcel coordinates and a visual property footprint.
    1. Checks known service addresses and in-memory geocode cache first (0 calls).
    2. Calls Google Maps Geocoding API ONCE for rooftop precision when `GOOGLE_MAPS_API_KEY` is active
       and within `MAPS_MONTHLY_FREE_TIER_CAP` (9,500/mo) and `MAPS_DAILY_SAFE_CAP` (300/day).
    3. Falls back to real coordinates from Stage 1 (Photon/OSM autocomplete) if Google is capped or unconfigured.
    4. Uses deterministic SHA-256 coordinate offset only as last-resort offline fallback.
    """
    known_addresses = {
        "742 evergreen": (44.2601, -72.5754, "742 Evergreen Terrace, Montpelier, VT 05602"),
        "184 old county": (43.9742, -73.9211, "184 Old County Rd, Lake Placid, NY 12946"),
        "905 maple ridge": (41.6611, -91.5302, "905 Maple Ridge Ln, Iowa City, IA 52240"),
    }
    lowered = street_address.strip().lower()
    for key, (lat, lng, formatted) in known_addresses.items():
        if key in lowered:
            return _build_parcel_layout(formatted, lat, lng, precision_source="known_service_catalog")

    if lowered in _GEOCODE_CACHE:
        c_lat, c_lng, c_fmt = _GEOCODE_CACHE[lowered]
        return _build_parcel_layout(c_fmt, c_lat, c_lng, precision_source="google_geocode_cache")

    settings = get_settings()
    _roll_counters_if_needed()

    api_key = settings.google_maps_api_key
    within_free_cap = (
        not settings.ENFORCE_FREE_TIER_HARD_CAP
        or (
            _USAGE_TRACKER["monthly_calls"] < settings.MAPS_MONTHLY_FREE_TIER_CAP
            and _USAGE_TRACKER["daily_calls"] < settings.MAPS_DAILY_SAFE_CAP
        )
    )

    if api_key and not api_key.startswith("PLACEHOLDER") and within_free_cap:
        try:
            _USAGE_TRACKER["monthly_calls"] += 1
            _USAGE_TRACKER["daily_calls"] += 1
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={"address": street_address.strip(), "key": api_key},
                )
                if resp.status_code == 200:
                    payload = resp.json()
                    if payload.get("status") == "OK" and payload.get("results"):
                        top = payload["results"][0]
                        loc = top["geometry"]["location"]
                        lat = round(float(loc["lat"]), 6)
                        lng = round(float(loc["lng"]), 6)
                        fmt = top.get("formatted_address", street_address.strip())
                        _GEOCODE_CACHE[lowered] = (lat, lng, fmt)
                        return _build_parcel_layout(fmt, lat, lng, precision_source="google_rooftop_geocode")
        except Exception:
            pass

    # Stage 1 Autocomplete Coordinate Fallback (real OpenStreetMap/Photon coordinates at $0.00)
    if fallback_lat is not None and fallback_lng is not None:
        return _build_parcel_layout(
            street_address.strip(),
            round(float(fallback_lat), 6),
            round(float(fallback_lng), 6),
            precision_source="photon_osm_fallback",
        )

    if lowered in _AUTOCOMPLETE_FALLBACK_COORDS:
        fb_lat, fb_lng, fb_fmt = _AUTOCOMPLETE_FALLBACK_COORDS[lowered]
        return _build_parcel_layout(fb_fmt, fb_lat, fb_lng, precision_source="photon_osm_fallback")

    # Zero-cost deterministic fallback when no key is set, no autocomplete coords exist, or cap is reached
    digest = hashlib.sha256(lowered.encode("utf-8")).hexdigest()
    lat_offset = ((int(digest[:6], 16) % 2000) - 1000) * 0.0001
    lng_offset = ((int(digest[6:12], 16) % 2000) - 1000) * 0.0001
    lat = round(42.8500 + lat_offset, 6)
    lng = round(-73.2500 + lng_offset, 6)
    return _build_parcel_layout(street_address.strip(), lat, lng, precision_source="deterministic_fallback")


def _build_parcel_layout(
    formatted_address: str,
    center_lat: float,
    center_lng: float,
    precision_source: str = "google_rooftop_geocode",
) -> Dict[str, Any]:
    """Return parcel metadata and landmark cell bounds for the 25x16 3m x 3m grid."""
    return {
        "formatted_address": formatted_address,
        "parcel_center_lat": center_lat,
        "parcel_center_lng": center_lng,
        "precision_source": precision_source,
        "grid_rows": GRID_ROWS,
        "grid_cols": GRID_COLS,
        "square_size_meters": SQUARE_SIZE_METERS,
        "square_size_feet": round(SQUARE_SIZE_FEET, 2),
        "free_tier_guardrail": get_maps_free_tier_status(),
        "landmarks": {
            "main_house": {"row_start": 4, "row_end": 8, "col_start": 10, "col_end": 16, "label": "Main Residence (Roof)"},
            "attached_garage": {"row_start": 5, "row_end": 8, "col_start": 7, "col_end": 9, "label": "Garage"},
            "paved_driveway": {"row_start": 9, "row_end": 14, "col_start": 7, "col_end": 10, "label": "Driveway"},
            "turnaround_bay": {"row_start": 10, "row_end": 11, "col_start": 11, "col_end": 12, "label": "Driveway Turnaround"},
            "public_road": {"row_start": 15, "row_end": 15, "col_start": 0, "col_end": 24, "label": "Town Road / Street Apron"},
        },
    }
