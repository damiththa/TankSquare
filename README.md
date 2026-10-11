# TankSquare (`https://github.com/damiththa/TankSquare.git`)

**TankSquare** is a 100% browser-based, multi-vendor B2B SaaS platform and Plaid-style `<script>` extension for US propane and heating-oil dealers. It bridges **3m × 3m property grid squares (`what3words`)**, satellite parcel layouts, **waypoint-aware bobtail hose-reach calculations**, and **CDL driver parking verification**.

---

## Core Architectural Guarantees
1. **100% Browser-Based (Zero App Install):** Works in standard mobile and desktop browsers (Safari, Chrome, Edge) for both homeowners and fuel truck drivers.
2. **Zero Separate Account for Residents:** Homeowners never sign up for or log into a TankSquare account. Identity is passed via a pre-authenticated session token in the propane vendor's `<script>` tag or SMS/email magic link.
3. **100% Free for Residents:** Residents are never billed or shown payment screens. TankSquare is strictly B2B vendor-paid.
4. **Cloud-Direct on Google Cloud Platform (Zero SQLite):** Built directly for **GCP Cloud Run**, **Google Cloud Firestore** (multi-tenant document store isolated by `vendor_id`), and **Google Cloud Storage (GCS)** (for compressed tank/driveway photos).
5. **`DEV` and `PROD` Environments & Git Branches:**
   - **`dev` branch $\rightarrow$ GCP `DEV` Environment** (`.env.dev`, Cloud Run `tanksquare-api-dev`, Firestore `dev_*` collections, pre-seeded with 3 demo fuel providers).
   - **`main` branch $\rightarrow$ GCP `PROD` Environment** (`.env.prod`, Cloud Run `tanksquare-api-prod`, Firestore `prod_*` collections, strict vendor API key & origin enforcement).

---

## Repository Structure

```text
TankSquare/
├── app/
│   ├── main.py                 # FastAPI entrypoint, CORS, GCP health checks & browser routes
│   ├── config.py               # DEV vs PROD GCP settings (.env.dev / .env.prod)
│   ├── models.py               # Pydantic schemas (Vendors, Sessions, Grid/Hose Math, SitePasses)
│   ├── routers/
│   │   ├── vendors.py          # 1. B2B Vendor onboarding, <script> session tokens, ERP exports
│   │   ├── resident.py         # 2. Zero-login Resident Portal, 3m grid, hose math & GCS photos
│   │   ├── driver.py           # 3. Tanker Driver mobile view & Suggested->Verified parking API
│   │   └── w3w.py              # 4. On-demand what3words v3 resolver with short-TTL cache
│   ├── services/
│   │   ├── gcp_store.py        # Direct Google Cloud Firestore & Cloud Storage service
│   │   ├── geo_grid.py         # 25x16 3m x 3m grid math, +15% hose slack & NFPA 58 checks
│   │   └── w3w_service.py      # On-demand what3words API client
│   └── static/
│       ├── widget.js           # Plaid-style 1-line <script> embed SDK for fuel portals
│       ├── index.html          # Approach 1: Resident Zero-Login Browser Portal
│       ├── driver.html         # Approach 2: Mobile-Browser Tanker Driver View
│       └── sw.js               # Rural offline Service Worker for zero-signal dead zones
├── deploy/
│   ├── cloudbuild.dev.yaml     # GCP Cloud Build pipeline for DEV (`dev` branch)
│   └── cloudbuild.prod.yaml    # GCP Cloud Build pipeline for PROD (`main` branch)
├── .github/workflows/
│   └── deploy-gcp.yml          # GitHub Actions CI/CD -> Cloud Run (DEV & PROD)
├── tests/
│   └── test_api.py             # Pytest suite verifying APIs, grid math & tenant isolation
├── .env.dev                    # GCP DEV configuration
├── .env.prod                   # GCP PROD configuration
├── Dockerfile                  # Cloud Run Python 3.11 container image
└── requirements.txt
```

---

## REST API Summary (`/docs`)

| Actor / Domain | Method & Endpoint | Purpose |
| :--- | :--- | :--- |
| **0. System & GCP** | `GET /api/v1/health` | Cloud Run readiness probe, active `ENV` (`dev`/`prod`), Firestore status |
| **0. System & GCP** | `GET /api/v1/config/public` | Browser public config & zero-login / zero-billing flags |
| **1. Fuel Vendors & ERPs** | `GET /api/v1/vendors` | List registered propane/heating-oil providers |
| **1. Fuel Vendors & ERPs** | `POST /api/v1/vendors` | Register/update a vendor (`max_hose_ft`, `erp_system`, `webhook_url`) |
| **1. Fuel Vendors & ERPs** | `POST /api/v1/vendors/{vendor_id}/sessions` | Issue a Plaid-style zero-login session token & `<script>` snippet |
| **1. Fuel Vendors & ERPs** | `GET /api/v1/vendors/{vendor_id}/erp-export` | Export passes formatted for **Cargas**, **ADD Systems**, **RCC**, or **Destwin** |
| **2. Resident Portal** | `GET /api/v1/resident/session/{token}` | Resolve resident token, vendor branding, parcel layout & existing pass |
| **2. Resident Portal** | `POST /api/v1/resident/geocode` | Geocode street address or phone browser GPS into 25×16 3m grid |
| **2. Resident Portal** | `POST /api/v1/resident/calculate-hose` | Live waypoint hose-reach calculator (+15% slack & NFPA 58 check) |
| **2. Resident Portal** | `PUT /api/v1/resident/session/{token}/pass` | Save TankSquare Pass to GCP Firestore (`parking_status="suggested"`) |
| **2. Resident Portal** | `POST /api/v1/resident/session/{token}/photos` | Upload tank/driveway photo to Google Cloud Storage (GCS) |
| **3. Tanker Driver** | `GET /api/v1/driver/routes` | Fetch daily route passes (cached offline by `sw.js`) |
| **3. Tanker Driver** | `POST /api/v1/driver/pass/{site_id}/verify-parking` | 1-tap Confirm or Relocate Suggested Parking $\rightarrow$ `driver_verified` |
| **4. what3words** | `GET /api/v1/w3w/convert-to-3wa` | Convert `(lat, lng)` or `(row, col)` to `///word.word.word` on demand |

---

## Deploying to Google Cloud Platform (`DEV` & `PROD`)

```bash
# Deploy DEV (`dev` branch) to Google Cloud Run
gcloud builds submit --config deploy/cloudbuild.dev.yaml --project tanksquare-dev

# Deploy PROD (`main` branch) to Google Cloud Run
gcloud builds submit --config deploy/cloudbuild.prod.yaml --project tanksquare-prod
```
