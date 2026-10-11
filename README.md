# TankSquare (`https://github.com/damiththa/TankSquare.git`)

**TankSquare** is a 100% browser-based, multi-vendor B2B SaaS platform and Plaid-style `<script>` extension for US propane and heating-oil dealers. It bridges **3m × 3m property grid squares (`what3words`)**, satellite parcel layouts, **waypoint-aware bobtail hose-reach calculations**, and **CDL driver parking verification**.

- 📌 **[Parked Roadmap, Reminders & Decision Tracker (`docs/PARKED_ROADMAP_AND_REMINDERS.md`)](./docs/PARKED_ROADMAP_AND_REMINDERS.md)**
- ☁️ **[GCP & Secret Manager Setup Guide (`docs/GCP_SETUP_INSTRUCTIONS.md`)](./docs/GCP_SETUP_INSTRUCTIONS.md)**

---

## Core Architectural Guarantees
1. **100% Browser-Based (Zero App Install):** Works in standard mobile and desktop browsers (Safari, Chrome, Edge) for both homeowners and fuel truck drivers.
2. **Zero Separate Account for Residents:** Homeowners never sign up for or log into a TankSquare account. Identity is passed via a pre-authenticated session token in the propane vendor's `<script>` tag or SMS/email magic link.
3. **100% Free for Residents:** Residents are never billed or shown payment screens. TankSquare is strictly B2B vendor-paid.
4. **Cloud-Direct on Google Cloud Platform (Zero SQLite):** Built directly for **GCP Cloud Run**, **Google Cloud Firestore** (multi-tenant document store isolated by `vendor_id`), and **Google Cloud Storage (GCS)** (for compressed tank/driveway photos).
5. **Zero Hardcoded Secrets:** All sensitive keys (`GOOGLE_MAPS_API_KEY`, `W3W_API_KEY`, `SESSION_SIGNING_SECRET`, `VENDOR_API_SHARED_SECRET`) are stored in **Google Cloud Secret Manager** and referenced dynamically via [`app/services/secret_manager.py`](./app/services/secret_manager.py) or Cloud Run `--set-secrets`. No `.env.*` files (except `.env.example`) are ever tracked in Git.
6. **`DEV` and `PROD` Environments & Git Branches:**
   - **`dev` branch $\rightarrow$ GCP `DEV` Environment** ([`deploy/cloudbuild.dev.yaml`](./deploy/cloudbuild.dev.yaml), Cloud Run `tanksquare-api-dev`, Firestore `dev_*` collections).
   - **`main` branch $\rightarrow$ GCP `PROD` Environment** ([`deploy/cloudbuild.prod.yaml`](./deploy/cloudbuild.prod.yaml), Cloud Run `tanksquare-api-prod`, Firestore `prod_*` collections).

---

## Repository Structure

```text
TankSquare/
├── app/
│   ├── main.py                 # FastAPI entrypoint, CORS, GCP health checks & browser routes
│   ├── config.py               # Zero-hardcoded-secrets configuration module
│   ├── models.py               # Pydantic schemas (Vendors, Sessions, Grid/Hose Math, SitePasses)
│   ├── routers/
│   │   ├── vendors.py          # 1. B2B Vendor onboarding, <script> session tokens, ERP exports
│   │   ├── resident.py         # 2. Zero-login Resident Portal, 3m grid, hose math & GCS photos
│   │   ├── driver.py           # 3. Tanker Driver mobile view & Suggested->Verified parking API
│   │   └── w3w.py              # 4. On-demand what3words v3 resolver with short-TTL cache
│   ├── services/
│   │   ├── secret_manager.py   # Dynamic secret loader (GCP Secret Manager + runtime env vars)
│   │   ├── gcp_store.py        # Direct Google Cloud Firestore & Cloud Storage service
│   │   ├── geo_grid.py         # 25x16 3m x 3m grid math, +15% hose slack & NFPA 58 checks
│   │   └── w3w_service.py      # On-demand what3words API client
│   └── static/
│       ├── widget.js           # Plaid-style 1-line <script> embed SDK for fuel portals
│       ├── index.html          # Approach 1: Resident Zero-Login Browser Portal
│       ├── driver.html         # Approach 2: Mobile-Browser Tanker Driver View
│       └── sw.js               # Rural offline Service Worker for zero-signal dead zones
├── docs/
│   ├── PARKED_ROADMAP_AND_REMINDERS.md  # Git-tracked reminder list & design roadmap
│   └── GCP_SETUP_INSTRUCTIONS.md        # Step-by-step GCP & Secret Manager setup
├── deploy/
│   ├── cloudbuild.dev.yaml     # GCP Cloud Build pipeline for DEV (`dev` branch)
│   └── cloudbuild.prod.yaml    # GCP Cloud Build pipeline for PROD (`main` branch)
├── .github/workflows/
│   └── deploy-gcp.yml          # GitHub Actions CI/CD -> Cloud Run (DEV & PROD)
├── tests/
│   └── test_api.py             # Pytest suite verifying APIs, grid math & tenant isolation
├── .env.example                # Safe template documenting env vars & Secret Manager IDs
├── Dockerfile                  # Cloud Run Python 3.11 container image
└── requirements.txt
```
