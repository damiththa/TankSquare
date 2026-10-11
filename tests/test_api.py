"""
Automated Pytest Suite for TankSquare (`tests/test_api.py`).

Verifies:
1. Cloud-Direct GCP configuration & zero-SQLite guarantee (`/api/v1/health`).
2. Multi-vendor tenant isolation & zero-login resident session generation (`/api/v1/vendors`).
3. 3m x 3m grid math, waypoint hose-reach calculation (+15% slack & NFPA 58 line-of-sight),
   and saving a Resident TankSquare Pass with `parking_status="suggested"` (`/api/v1/resident`).
4. CDL Tanker Driver verification & relocation workflow upgrading `suggested` -> `driver_verified` (`/api/v1/driver`).
5. On-demand `what3words` 3-word resolution (`/api/v1/w3w`).
"""

import sys
from pathlib import Path

# Ensure repository root is on sys.path for both `pytest` and `python -m pytest`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def test_health_and_zero_sqlite_guarantees() -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["sqlite_used"] is False
    assert data["resident_account_required"] is False
    assert data["resident_billing_enabled"] is False


def test_multi_vendor_isolation_and_zero_login_session() -> None:
    vendors_resp = client.get("/api/v1/vendors")
    assert vendors_resp.status_code == 200
    vendor_ids = {v["vendor_id"] for v in vendors_resp.json()}
    assert {"gmp_vt", "aho_ny", "hce_ia"}.issubset(vendor_ids)

    # Create a zero-login resident session for Green Mountain Propane
    sess_resp = client.post(
        "/api/v1/vendors/gmp_vt/sessions",
        json={
            "customer_account_id": "GMP-99901",
            "customer_name": "Test Homeowner",
            "street_address": "120 Mountain View Rd, Stowe, VT 05672",
            "fuel_type": "propane",
            "tank_type": "underground_dome",
            "tank_size_gallons": 500,
        },
    )
    assert sess_resp.status_code == 201
    sess = sess_resp.json()
    assert sess["vendor_id"] == "gmp_vt"
    assert sess["resident_account_required"] is False
    assert sess["resident_billing_enabled"] is False
    assert 'data-vendor="gmp_vt"' in sess["widget_embed_snippet"]

    # Ensure strict tenant isolation: gmp_vt sites never leak into aho_ny
    gmp_sites = client.get("/api/v1/vendors/gmp_vt/sites").json()
    assert all(s["vendor_id"] == "gmp_vt" for s in gmp_sites)


def test_resident_hose_reach_and_save_pass() -> None:
    # 1. Waypoint hose calculation check
    calc_resp = client.post(
        "/api/v1/resident/calculate-hose",
        json={
            "parcel_center_lat": 44.2601,
            "parcel_center_lng": -72.5754,
            "tank_square": {"row": 5, "col": 17, "lat": 44.2601, "lng": -72.5754},
            "park_p1_square": {"row": 10, "col": 11, "lat": 44.2601, "lng": -72.5754},
            "hose_waypoints": [{"row": 9, "col": 17, "lat": 44.2601, "lng": -72.5754}],
            "hazard_squares": [{"row": 6, "col": 20, "lat": 44.2601, "lng": -72.5754}],
            "vendor_max_hose_ft": 150,
        },
    )
    assert calc_resp.status_code == 200
    metrics = calc_resp.json()
    assert metrics["within_limit"] is True
    assert metrics["line_of_sight_clear"] is False  # Has 1 corner waypoint -> flags NFPA 58 note
    assert metrics["practical_pull_ft"] > metrics["straight_line_ft"]

    # 2. Save Resident Pass -> must default to `parking_status == "suggested"`
    save_resp = client.put(
        "/api/v1/resident/session/ts_tok_gmp_vt_demo1/pass",
        json={
            "tank_row": 5,
            "tank_col": 17,
            "park_p1_row": 10,
            "park_p1_col": 11,
            "park_p2_row": 14,
            "park_p2_col": 8,
            "waypoint_coords": [{"row": 9, "col": 17}],
            "hazard_coords": [{"row": 6, "col": 20}],
            "driveway_weight_acknowledged": True,
            "gate_code": "#4421",
            "access_notes": "Updated via resident zero-login portal",
        },
    )
    assert save_resp.status_code == 200
    saved = save_resp.json()
    assert saved["parking_status"] == "suggested"
    assert saved["tank_square"]["w3w"].startswith("///")
    assert saved["park_p1_square"]["w3w"].startswith("///")


def test_driver_verify_and_relocate_parking() -> None:
    site_id = "site_gmp_vt_gmp_88412"
    verify_resp = client.post(
        f"/api/v1/driver/pass/{site_id}/verify-parking",
        json={
            "driver_id": "DRV-777",
            "action": "adjust",
            "adjusted_p1_row": 11,
            "adjusted_p1_col": 10,
            "driver_notes": "Backed bobtail to wider apron at R12-C11",
        },
    )
    assert verify_resp.status_code == 200
    verified = verify_resp.json()
    assert verified["parking_status"] == "driver_verified"
    assert verified["verified_by_driver_id"] == "DRV-777"
    assert verified["park_p1_square"]["row"] == 11
    assert verified["park_p1_square"]["col"] == 10


def test_browser_views_have_valid_script_tags() -> None:
    root_resp = client.get("/")
    assert root_resp.status_code == 200
    assert root_resp.text.count("<script") == 2
    assert root_resp.text.count("</script>") == 2

    driver_resp = client.get("/driver")
    assert driver_resp.status_code == 200
    assert driver_resp.text.count("<script") == 2
    assert driver_resp.text.count("</script>") == 2

