"""
Pydantic Data Models for TankSquare's Multi-Vendor B2B Platform.

Covers:
1. Propane & Heating-Oil Vendors (B2B Tenants & ERP Integrations)
2. Zero-Login Resident Sessions (Plaid-style `<script>` & SMS Magic Links)
3. 3m x 3m Property Grid Coordinates & Waypoint Hose-Reach Calculations
4. TankSquare Site Passes (Suggested vs. Driver-Verified Parking + GCS Photos)
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FuelType(str, Enum):
    PROPANE = "propane"
    HEATING_OIL = "heating_oil"


class TankType(str, Enum):
    ABOVEGROUND = "aboveground"
    UNDERGROUND_DOME = "underground_dome"
    WALL_FILL_PIPE = "wall_fill_pipe"


class ParkingStatus(str, Enum):
    SUGGESTED = "suggested"               # Resident selected; pending CDL driver verification
    DRIVER_VERIFIED = "driver_verified"   # Verified or adjusted by fuel truck driver on site


class ErpSystem(str, Enum):
    CARGAS = "cargas"               # Cargas Energy / MyFuelPortal
    ADD_SYSTEMS = "add_systems"     # ADD Systems E3 / SmartConnect / Raven
    RCC = "rcc"                     # Rural Computer Consultants / MOGO
    DESTWIN = "destwin"             # Destwin Fuel Dealer Solution
    BLUE_COW = "blue_cow"           # Blue Cow Ignite
    CUSTOM_WEBHOOK = "custom_webhook"


class PhotoCategory(str, Enum):
    TANK_DOME = "tank_dome"
    DRIVEWAY_APPROACH = "driveway_approach"
    FILL_PIPE = "fill_pipe"
    GATE_OBSTACLE = "gate_obstacle"


# ---------------------------------------------------------------------------
# 1. Vendor (Propane / Heating-Oil Provider) Models
# ---------------------------------------------------------------------------
class VendorConfig(BaseModel):
    vendor_id: str = Field(..., description="Unique tenant slug, e.g. 'gmp_vt'")
    name: str = Field(..., description="Display name of the fuel provider")
    tagline: str = Field(default="Residential Fuel Delivery Portal")
    primary_color: str = Field(default="#15803d", description="Brand hex color for widget header")
    accent_color: str = Field(default="#f97316", description="Secondary accent hex color")
    max_hose_ft: int = Field(default=150, ge=50, le=300, description="Standard bobtail hose reel length in feet")
    supported_fuels: List[FuelType] = Field(default_factory=lambda: [FuelType.PROPANE])
    erp_system: ErpSystem = Field(default=ErpSystem.CARGAS)
    webhook_url: Optional[str] = Field(default=None, description="ERP webhook URL for real-time pass sync")
    support_phone: str = Field(default="1-800-555-TANK")
    active: bool = Field(default=True)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class VendorCreateRequest(BaseModel):
    vendor_id: str
    name: str
    tagline: Optional[str] = "Residential Fuel Delivery Portal"
    primary_color: Optional[str] = "#15803d"
    accent_color: Optional[str] = "#f97316"
    max_hose_ft: int = 150
    supported_fuels: List[FuelType] = Field(default_factory=lambda: [FuelType.PROPANE])
    erp_system: ErpSystem = ErpSystem.CARGAS
    webhook_url: Optional[str] = None
    support_phone: Optional[str] = "1-800-555-TANK"


# ---------------------------------------------------------------------------
# 2. Zero-Login Resident Session Models
# ---------------------------------------------------------------------------
class SessionCreateRequest(BaseModel):
    customer_account_id: str = Field(..., description="Customer account ID in the propane dealer's ERP")
    customer_name: str = Field(..., description="Homeowner display name")
    street_address: str = Field(..., description="Service delivery street address")
    fuel_type: FuelType = Field(default=FuelType.PROPANE)
    tank_type: TankType = Field(default=TankType.ABOVEGROUND)
    tank_size_gallons: int = Field(default=500)


class SessionResponse(BaseModel):
    session_token: str
    site_id: str
    vendor_id: str
    vendor_name: str
    customer_account_id: str
    customer_name: str
    street_address: str
    fuel_type: FuelType
    tank_type: TankType
    tank_size_gallons: int
    magic_link_url: str
    widget_embed_snippet: str
    resident_account_required: bool = False
    resident_billing_enabled: bool = False
    expires_in_seconds: int = 86400


# ---------------------------------------------------------------------------
# 3. 3m x 3m Grid Square & Hose Calculation Models
# ---------------------------------------------------------------------------
class GridSquareCoord(BaseModel):
    row: int = Field(..., ge=0, le=50, description="0-indexed grid row from North to South")
    col: int = Field(..., ge=0, le=50, description="0-indexed grid col from West to East")
    label: Optional[str] = Field(default=None, description="Human-friendly grid cell code, e.g. 'R5-C18'")
    lat: float = Field(..., description="WGS84 latitude of the 3m x 3m square center")
    lng: float = Field(..., description="WGS84 longitude of the 3m x 3m square center")
    w3w: Optional[str] = Field(default=None, description="Resolved what3words address (resolved on-demand)")


class HoseCalculationRequest(BaseModel):
    parcel_center_lat: float = 44.2601
    parcel_center_lng: float = -72.5754
    tank_square: GridSquareCoord
    park_p1_square: GridSquareCoord
    park_p2_square: Optional[GridSquareCoord] = None
    hose_waypoints: List[GridSquareCoord] = Field(default_factory=list)
    hazard_squares: List[GridSquareCoord] = Field(default_factory=list)
    vendor_max_hose_ft: int = 150


class HoseCalculationResponse(BaseModel):
    straight_line_ft: float
    routed_distance_ft: float
    practical_pull_ft: float = Field(..., description="Includes +15% hose slack buffer around terrain/obstacles")
    p2_practical_pull_ft: Optional[float] = None
    vendor_max_hose_ft: int
    remaining_margin_ft: float
    within_limit: bool
    status: str = Field(..., description="'ok' (<80% max), 'warning' (80-100% max), or 'exceeds' (>100% max)")
    line_of_sight_clear: bool = Field(
        ...,
        description="NFPA 58 check: False if hose bends around building waypoints out of driver line-of-sight",
    )
    hazard_conflict: bool = Field(
        default=False,
        description="True if P1 or P2 overlaps or is within 1 square of a marked septic/no-drive hazard zone",
    )
    recommendation: str


# ---------------------------------------------------------------------------
# 4. TankSquare Site Pass & Driver Verification Models
# ---------------------------------------------------------------------------
class SitePhoto(BaseModel):
    photo_id: str
    category: PhotoCategory = PhotoCategory.TANK_DOME
    gcs_uri: str
    public_url: str
    caption: Optional[str] = None
    uploaded_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class SitePass(BaseModel):
    site_id: str
    vendor_id: str
    customer_account_id: str
    customer_name: str
    street_address: str
    parcel_center_lat: float
    parcel_center_lng: float
    fuel_type: FuelType = FuelType.PROPANE
    tank_type: TankType = TankType.ABOVEGROUND
    tank_size_gallons: int = 500
    tank_square: GridSquareCoord
    park_p1_square: GridSquareCoord
    park_p2_square: Optional[GridSquareCoord] = None
    hose_waypoints: List[GridSquareCoord] = Field(default_factory=list)
    hazard_squares: List[GridSquareCoord] = Field(default_factory=list)
    hose_metrics: HoseCalculationResponse
    parking_status: ParkingStatus = ParkingStatus.SUGGESTED
    verified_by_driver_id: Optional[str] = None
    verified_at: Optional[str] = None
    driver_verification_notes: Optional[str] = None
    driveway_weight_acknowledged: bool = True
    gate_code: Optional[str] = None
    pets_warning: Optional[str] = None
    access_notes: Optional[str] = None
    photos: List[SitePhoto] = Field(default_factory=list)
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class SitePassUpdateRequest(BaseModel):
    street_address: Optional[str] = None
    parcel_center_lat: Optional[float] = None
    parcel_center_lng: Optional[float] = None
    fuel_type: Optional[FuelType] = None
    tank_type: Optional[TankType] = None
    tank_size_gallons: Optional[int] = None
    tank_row: int = Field(..., ge=0, le=50)
    tank_col: int = Field(..., ge=0, le=50)
    park_p1_row: int = Field(..., ge=0, le=50)
    park_p1_col: int = Field(..., ge=0, le=50)
    park_p2_row: Optional[int] = Field(default=None, ge=0, le=50)
    park_p2_col: Optional[int] = Field(default=None, ge=0, le=50)
    waypoint_coords: List[Dict[str, int]] = Field(
        default_factory=list,
        description="List of {'row': r, 'col': c} waypoints where hose bends around a corner",
    )
    hazard_coords: List[Dict[str, int]] = Field(
        default_factory=list,
        description="List of {'row': r, 'col': c} septic/soft-ground squares truck must avoid",
    )
    driveway_weight_acknowledged: bool = True
    gate_code: Optional[str] = None
    pets_warning: Optional[str] = None
    access_notes: Optional[str] = None


class DriverVerifyParkingRequest(BaseModel):
    driver_id: str = Field(..., description="CDL Driver ID or badge code")
    action: str = Field(
        default="confirm",
        description="'confirm' to approve resident's Suggested P1, or 'adjust' to move P1 to actual safe square",
    )
    adjusted_p1_row: Optional[int] = Field(default=None, ge=0, le=50)
    adjusted_p1_col: Optional[int] = Field(default=None, ge=0, le=50)
    driver_notes: Optional[str] = Field(default=None, description="Driver field note, e.g. 'Backed to turnaround'")
