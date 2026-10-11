"""
Google Cloud Platform Direct Persistence Layer (`app/services/gcp_store.py`).

Uses:
- Google Cloud Firestore (`google-cloud-firestore`) for multi-tenant document storage:
  - `{prefix}vendors`
  - `{prefix}sessions`
  - `{prefix}site_passes`
  - `{prefix}webhook_logs`
- Google Cloud Storage (`google-cloud-storage`) for tank/driveway site photos.

Zero SQLite is used anywhere in TankSquare. If GCP Application Default Credentials (ADC) are not
mounted in the current container (e.g., during automated CI tests or instant sandbox preview),
this service transparently mirrors the exact Firestore document collections in memory.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.models import (
    ErpSystem,
    FuelType,
    GridSquareCoord,
    ParkingStatus,
    PhotoCategory,
    SessionCreateRequest,
    SessionResponse,
    SitePass,
    SitePhoto,
    TankType,
    VendorConfig,
)
from app.services.geo_grid import (
    calculate_hose_reach,
    format_cell_label,
    grid_cell_to_lat_lng,
)
from app.services.w3w_service import resolve_w3w_sync


class GCPDataStore:
    """Direct Google Cloud Firestore & Cloud Storage client with multi-vendor isolation."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.firestore_client = None
        self.storage_client = None
        self.gcp_live_connected = False

        # In-memory Firestore document collection mirror (used when ADC credentials are not mounted)
        self._mem_collections: Dict[str, Dict[str, Dict[str, Any]]] = {
            self.settings.collection_name("vendors"): {},
            self.settings.collection_name("sessions"): {},
            self.settings.collection_name("site_passes"): {},
            self.settings.collection_name("webhook_logs"): {},
        }

        self._init_gcp_clients()
        if self.settings.SEED_DEMO_DATA:
            self._seed_dev_environment()

    def _init_gcp_clients(self) -> None:
        """Attempt direct connection to Google Cloud Firestore & Cloud Storage."""
        try:
            import google.auth
            from google.cloud import firestore, storage

            credentials, project = google.auth.default()
            if credentials is not None:
                target_project = self.settings.GCP_PROJECT_ID or project
                self.firestore_client = firestore.Client(
                    project=target_project,
                    database=self.settings.FIRESTORE_DATABASE,
                    credentials=credentials,
                )
                self.storage_client = storage.Client(
                    project=target_project,
                    credentials=credentials,
                )
                self.gcp_live_connected = True
        except Exception:
            # Running in CI or sandbox without live GCP IAM credentials attached yet
            self.gcp_live_connected = False

    # ------------------------------------------------------------------
    # Low-Level Firestore Document Helpers
    # ------------------------------------------------------------------
    def _set_doc(self, base_collection: str, doc_id: str, data: Dict[str, Any]) -> None:
        col_name = self.settings.collection_name(base_collection)
        if self.gcp_live_connected and self.firestore_client is not None:
            try:
                self.firestore_client.collection(col_name).document(doc_id).set(data)
                return
            except Exception:
                pass
        self._mem_collections.setdefault(col_name, {})[doc_id] = data

    def _get_doc(self, base_collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        col_name = self.settings.collection_name(base_collection)
        if self.gcp_live_connected and self.firestore_client is not None:
            try:
                snap = self.firestore_client.collection(col_name).document(doc_id).get()
                if snap.exists:
                    return snap.to_dict()
            except Exception:
                pass
        return self._mem_collections.get(col_name, {}).get(doc_id)

    def _list_docs(self, base_collection: str, vendor_id: Optional[str] = None) -> List[Dict[str, Any]]:
        col_name = self.settings.collection_name(base_collection)
        if self.gcp_live_connected and self.firestore_client is not None:
            try:
                query = self.firestore_client.collection(col_name)
                if vendor_id:
                    query = query.where("vendor_id", "==", vendor_id)
                return [doc.to_dict() for doc in query.stream()]
            except Exception:
                pass
        docs = list(self._mem_collections.get(col_name, {}).values())
        if vendor_id:
            docs = [d for d in docs if d.get("vendor_id") == vendor_id]
        return docs

    # ------------------------------------------------------------------
    # Vendor Operations
    # ------------------------------------------------------------------
    def upsert_vendor(self, vendor: VendorConfig) -> VendorConfig:
        self._set_doc("vendors", vendor.vendor_id, vendor.model_dump())
        return vendor

    def get_vendor(self, vendor_id: str) -> Optional[VendorConfig]:
        data = self._get_doc("vendors", vendor_id)
        return VendorConfig(**data) if data else None

    def list_vendors(self) -> List[VendorConfig]:
        return [VendorConfig(**d) for d in self._list_docs("vendors")]

    # ------------------------------------------------------------------
    # Session & Zero-Login Token Operations
    # ------------------------------------------------------------------
    def create_session(self, vendor_id: str, req: SessionCreateRequest, base_url: str = "") -> SessionResponse:
        vendor = self.get_vendor(vendor_id)
        if not vendor:
            raise ValueError(f"Unknown vendor_id: {vendor_id}")

        session_token = f"ts_tok_{vendor_id}_{uuid.uuid4().hex[:10]}"
        site_id = f"site_{vendor_id}_{req.customer_account_id.lower().replace('-', '_')}"

        prefix_url = base_url.rstrip("/") if base_url else ""
        magic_link_url = f"{prefix_url}/?token={session_token}&vendor={vendor_id}"
        widget_snippet = (
            f'<script src="{prefix_url}/static/widget.js" '
            f'data-vendor="{vendor_id}" '
            f'data-token="{session_token}"></script>'
        )

        session_resp = SessionResponse(
            session_token=session_token,
            site_id=site_id,
            vendor_id=vendor_id,
            vendor_name=vendor.name,
            customer_account_id=req.customer_account_id,
            customer_name=req.customer_name,
            street_address=req.street_address,
            fuel_type=req.fuel_type,
            tank_type=req.tank_type,
            tank_size_gallons=req.tank_size_gallons,
            magic_link_url=magic_link_url,
            widget_embed_snippet=widget_snippet,
            resident_account_required=False,
            resident_billing_enabled=False,
        )
        self._set_doc("sessions", session_token, session_resp.model_dump())
        return session_resp

    def get_session(self, session_token: str) -> Optional[SessionResponse]:
        data = self._get_doc("sessions", session_token)
        return SessionResponse(**data) if data else None

    # ------------------------------------------------------------------
    # Site Pass Operations (Multi-Vendor Isolated)
    # ------------------------------------------------------------------
    def save_site_pass(self, site_pass: SitePass) -> SitePass:
        site_pass.updated_at = datetime.utcnow().isoformat() + "Z"
        self._set_doc("site_passes", site_pass.site_id, site_pass.model_dump())
        self._record_webhook_event(site_pass, event_type="site_pass.updated")
        return site_pass

    def get_site_pass(self, site_id: str) -> Optional[SitePass]:
        data = self._get_doc("site_passes", site_id)
        return SitePass(**data) if data else None

    def list_site_passes(self, vendor_id: Optional[str] = None) -> List[SitePass]:
        return [SitePass(**d) for d in self._list_docs("site_passes", vendor_id=vendor_id)]

    # ------------------------------------------------------------------
    # Google Cloud Storage (GCS) Photo Upload
    # ------------------------------------------------------------------
    def upload_site_photo(
        self,
        site_id: str,
        vendor_id: str,
        category: PhotoCategory,
        filename: str,
        content_bytes: bytes,
        content_type: str = "image/jpeg",
        caption: Optional[str] = None,
    ) -> SitePhoto:
        photo_id = f"photo_{uuid.uuid4().hex[:8]}"
        ext = filename.split(".")[-1] if "." in filename else "jpg"
        blob_path = f"{self.settings.ENV}/{vendor_id}/{site_id}/{photo_id}.{ext}"
        gcs_uri = f"gs://{self.settings.effective_gcs_bucket}/{blob_path}"
        public_url = f"https://storage.googleapis.com/{self.settings.effective_gcs_bucket}/{blob_path}"

        if self.gcp_live_connected and self.storage_client is not None:
            try:
                bucket = self.storage_client.bucket(self.settings.effective_gcs_bucket)
                blob = bucket.blob(blob_path)
                blob.upload_from_string(content_bytes, content_type=content_type)
            except Exception:
                pass

        return SitePhoto(
            photo_id=photo_id,
            category=category,
            gcs_uri=gcs_uri,
            public_url=public_url,
            caption=caption or f"{category.value.replace('_', ' ').title()} photo",
        )

    # ------------------------------------------------------------------
    # Outbound ERP Webhook Event Log
    # ------------------------------------------------------------------
    def _record_webhook_event(self, site_pass: SitePass, event_type: str) -> Dict[str, Any]:
        vendor = self.get_vendor(site_pass.vendor_id)
        event_id = f"wh_{uuid.uuid4().hex[:10]}"
        payload = {
            "event_id": event_id,
            "event_type": event_type,
            "environment": self.settings.ENV,
            "vendor_id": site_pass.vendor_id,
            "erp_system": vendor.erp_system.value if vendor else "custom_webhook",
            "webhook_url": vendor.webhook_url if vendor else None,
            "site_id": site_pass.site_id,
            "customer_account_id": site_pass.customer_account_id,
            "tank_w3w": site_pass.tank_square.w3w,
            "park_p1_w3w": site_pass.park_p1_square.w3w,
            "practical_pull_ft": site_pass.hose_metrics.practical_pull_ft,
            "parking_status": site_pass.parking_status.value,
            "dispatched_at": datetime.utcnow().isoformat() + "Z",
        }
        self._set_doc("webhook_logs", event_id, payload)
        return payload

    def list_webhook_logs(self, vendor_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self._list_docs("webhook_logs", vendor_id=vendor_id)

    # ------------------------------------------------------------------
    # DEV Environment Multi-Vendor Seed Data
    # ------------------------------------------------------------------
    def _seed_dev_environment(self) -> None:
        """Seed 3 fuel providers and sample rural properties in DEV mode."""
        vendors = [
            VendorConfig(
                vendor_id="gmp_vt",
                name="Green Mountain Propane (VT)",
                tagline="Vermont's Trusted Rural Propane Service",
                primary_color="#15803d",
                accent_color="#f97316",
                max_hose_ft=150,
                supported_fuels=[FuelType.PROPANE],
                erp_system=ErpSystem.CARGAS,
                webhook_url="https://api.myfuelportal.example.com/webhooks/tanksquare",
                support_phone="1-802-555-0144",
            ),
            VendorConfig(
                vendor_id="aho_ny",
                name="Adirondack Heating Oil & Propane (NY)",
                tagline="Upstate NY Heating Oil & Propane Delivery",
                primary_color="#1d4ed8",
                accent_color="#eab308",
                max_hose_ft=125,
                supported_fuels=[FuelType.HEATING_OIL, FuelType.PROPANE],
                erp_system=ErpSystem.ADD_SYSTEMS,
                webhook_url="https://smartconnect.addsystems.example.com/hooks/tanksquare",
                support_phone="1-518-555-0199",
            ),
            VendorConfig(
                vendor_id="hce_ia",
                name="Heartland Co-op Energy (IA)",
                tagline="Member-Owned Farm & Home Propane Co-op",
                primary_color="#b45309",
                accent_color="#10b981",
                max_hose_ft=175,
                supported_fuels=[FuelType.PROPANE],
                erp_system=ErpSystem.RCC,
                webhook_url="https://mogo.rccbi.example.com/api/tanksquare-sync",
                support_phone="1-319-555-0175",
            ),
        ]
        for v in vendors:
            self.upsert_vendor(v)

        # Seed Demo Sessions & Site Passes
        demo_sites = [
            {
                "token": "ts_tok_gmp_vt_demo1",
                "vendor_id": "gmp_vt",
                "account_id": "GMP-88412",
                "name": "Arthur & Martha Pendelton",
                "address": "742 Evergreen Terrace, Montpelier, VT 05602",
                "lat": 44.2601,
                "lng": -72.5754,
                "fuel": FuelType.PROPANE,
                "tank_type": TankType.ABOVEGROUND,
                "gallons": 500,
                "tank_rc": (5, 17),
                "p1_rc": (10, 11),
                "p2_rc": (14, 8),
                "waypoints": [(9, 17)],
                "hazards": [(6, 20), (7, 20)],
                "status": ParkingStatus.SUGGESTED,
                "gate_code": "#4421 (Left driveway gate)",
                "pets": "Friendly Golden Retriever ('Barnaby') - kept indoors on delivery days",
                "notes": "500-gal green tank behind cedar hedge on east side of house. Please avoid septic leach mound at R7-C21.",
            },
            {
                "token": "ts_tok_aho_ny_demo2",
                "vendor_id": "aho_ny",
                "account_id": "AHO-30918",
                "name": "Elena Rostova",
                "address": "184 Old County Rd, Lake Placid, NY 12946",
                "lat": 43.9742,
                "lng": -73.9211,
                "fuel": FuelType.HEATING_OIL,
                "tank_type": TankType.WALL_FILL_PIPE,
                "gallons": 275,
                "tank_rc": (6, 10),
                "p1_rc": (10, 8),
                "p2_rc": (14, 8),
                "waypoints": [],
                "hazards": [(8, 19)],
                "status": ParkingStatus.DRIVER_VERIFIED,
                "gate_code": "None",
                "pets": "No pets",
                "notes": "Basement oil fill pipe + whistle vent on west foundation wall next to garage.",
            },
            {
                "token": "ts_tok_hce_ia_demo3",
                "vendor_id": "hce_ia",
                "account_id": "HCE-55104",
                "name": "caleb & Sarah Miller",
                "address": "905 Maple Ridge Ln, Iowa City, IA 52240",
                "lat": 41.6611,
                "lng": -91.5302,
                "fuel": FuelType.PROPANE,
                "tank_type": TankType.UNDERGROUND_DOME,
                "gallons": 1000,
                "tank_rc": (3, 14),
                "p1_rc": (10, 11),
                "p2_rc": (13, 9),
                "waypoints": [(4, 10)],
                "hazards": [(5, 21), (5, 22)],
                "status": ParkingStatus.SUGGESTED,
                "gate_code": "Open farm lane",
                "pets": "None",
                "notes": "1000-gal underground tank; green plastic dome marked with 4ft orange snow stake.",
            },
        ]

        for item in demo_sites:
            vendor = self.get_vendor(item["vendor_id"])
            assert vendor is not None
            site_id = f"site_{item['vendor_id']}_{item['account_id'].lower().replace('-', '_')}"

            session_resp = SessionResponse(
                session_token=item["token"],
                site_id=site_id,
                vendor_id=item["vendor_id"],
                vendor_name=vendor.name,
                customer_account_id=item["account_id"],
                customer_name=item["name"],
                street_address=item["address"],
                fuel_type=item["fuel"],
                tank_type=item["tank_type"],
                tank_size_gallons=item["gallons"],
                magic_link_url=f"/?token={item['token']}&vendor={item['vendor_id']}",
                widget_embed_snippet=(
                    f'<script src="/static/widget.js" data-vendor="{item["vendor_id"]}" '
                    f'data-token="{item["token"]}"></script>'
                ),
            )
            self._set_doc("sessions", item["token"], session_resp.model_dump())

            t_r, t_c = item["tank_rc"]
            t_lat, t_lng = grid_cell_to_lat_lng(item["lat"], item["lng"], t_r, t_c)
            tank_sq = GridSquareCoord(
                row=t_r,
                col=t_c,
                label=format_cell_label(t_r, t_c),
                lat=t_lat,
                lng=t_lng,
                w3w=resolve_w3w_sync(t_lat, t_lng),
            )

            p1_r, p1_c = item["p1_rc"]
            p1_lat, p1_lng = grid_cell_to_lat_lng(item["lat"], item["lng"], p1_r, p1_c)
            p1_sq = GridSquareCoord(
                row=p1_r,
                col=p1_c,
                label=format_cell_label(p1_r, p1_c),
                lat=p1_lat,
                lng=p1_lng,
                w3w=resolve_w3w_sync(p1_lat, p1_lng),
            )

            p2_r, p2_c = item["p2_rc"]
            p2_lat, p2_lng = grid_cell_to_lat_lng(item["lat"], item["lng"], p2_r, p2_c)
            p2_sq = GridSquareCoord(
                row=p2_r,
                col=p2_c,
                label=format_cell_label(p2_r, p2_c),
                lat=p2_lat,
                lng=p2_lng,
                w3w=resolve_w3w_sync(p2_lat, p2_lng),
            )

            wp_list: List[GridSquareCoord] = []
            for w_r, w_c in item["waypoints"]:
                w_lat, w_lng = grid_cell_to_lat_lng(item["lat"], item["lng"], w_r, w_c)
                wp_list.append(
                    GridSquareCoord(
                        row=w_r,
                        col=w_c,
                        label=format_cell_label(w_r, w_c),
                        lat=w_lat,
                        lng=w_lng,
                        w3w=resolve_w3w_sync(w_lat, w_lng),
                    )
                )

            hz_list: List[GridSquareCoord] = []
            for h_r, h_c in item["hazards"]:
                h_lat, h_lng = grid_cell_to_lat_lng(item["lat"], item["lng"], h_r, h_c)
                hz_list.append(
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
                hose_waypoints=wp_list,
                hazard_squares=hz_list,
            )

            site_pass = SitePass(
                site_id=site_id,
                vendor_id=item["vendor_id"],
                customer_account_id=item["account_id"],
                customer_name=item["name"],
                street_address=item["address"],
                parcel_center_lat=item["lat"],
                parcel_center_lng=item["lng"],
                fuel_type=item["fuel"],
                tank_type=item["tank_type"],
                tank_size_gallons=item["gallons"],
                tank_square=tank_sq,
                park_p1_square=p1_sq,
                park_p2_square=p2_sq,
                hose_waypoints=wp_list,
                hazard_squares=hz_list,
                hose_metrics=hose_metrics,
                parking_status=item["status"],
                verified_by_driver_id="DRV-402 (Mike T.)" if item["status"] == ParkingStatus.DRIVER_VERIFIED else None,
                verified_at="2026-10-10T14:22:00Z" if item["status"] == ParkingStatus.DRIVER_VERIFIED else None,
                driver_verification_notes=(
                    "Verified 10/10: Good gravel turnaround, clear sightline to fill pipe."
                    if item["status"] == ParkingStatus.DRIVER_VERIFIED
                    else None
                ),
                gate_code=item["gate_code"],
                pets_warning=item["pets"],
                access_notes=item["notes"],
                photos=[
                    SitePhoto(
                        photo_id=f"photo_seed_{item['vendor_id']}",
                        category=PhotoCategory.TANK_DOME,
                        gcs_uri=f"gs://{self.settings.effective_gcs_bucket}/{self.settings.ENV}/{item['vendor_id']}/{site_id}/tank.jpg",
                        public_url="https://images.unsplash.com/photo-1513694203232-719a280e022f?auto=format&fit=crop&w=600&q=80",
                        caption="Resident uploaded tank & approach view",
                    )
                ],
            )
            self._set_doc("site_passes", site_id, site_pass.model_dump())


# Singleton store instance
_STORE_INSTANCE: Optional[GCPDataStore] = None


def get_store() -> GCPDataStore:
    global _STORE_INSTANCE
    if _STORE_INSTANCE is None:
        _STORE_INSTANCE = GCPDataStore()
    return _STORE_INSTANCE
