# TankSquare — Parked Roadmap, Reminders & Decision Tracker

> **Purpose:** This file is tracked in Git across `dev` and `main` so we have a single source of truth for all parked topics, architectural guardrails, and upcoming items to review together.

---

## 1. Locked-In Architectural & Business Guardrails (Completed)

- [x] **Product Name:** **TankSquare** (`https://github.com/damiththa/TankSquare.git`).
- [x] **100% Browser-Based (Zero App Install):** Both the Resident Portal (`/`) and the Tanker Driver Mobile View (`/driver`) run in standard mobile and desktop browsers (Safari, Chrome, Edge) with zero app store downloads or desktop software installs.
- [x] **Zero Separate Account for Residents:** Residents never sign up for or log into a TankSquare account (`resident_account_required = False`). Identity is passed via a pre-authenticated session token in the propane vendor's `<script>` tag (`widget.js`) or SMS/email magic link.
- [x] **100% Free for Residents:** Residents are never billed or shown payment screens (`resident_billing_enabled = False`). TankSquare is strictly B2B vendor-paid.
- [x] **Single-Project Cloud-Direct GCP Isolation via Cloud Shell (Zero SQLite):** Both `DEV` (`dev` branch $\rightarrow$ `tanksquare-api-dev`, `dev_*` Firestore collections, `dev/` GCS prefix) and `PROD` (`main` branch $\rightarrow$ `tanksquare-api-prod`, `prod_*` Firestore collections, `prod/` GCS prefix) run isolated inside a single GCP project managed via **Google Cloud Shell** to maximize the **Google AI Pro ($10/mo GCP credit)** and **GCP Free Tier**.
- [x] **Zero Hardcoded Secrets:** All sensitive keys (`GOOGLE_MAPS_API_KEY`, `W3W_API_KEY`, `SESSION_SIGNING_SECRET`, `VENDOR_API_SHARED_SECRET`) live in **Google Cloud Secret Manager** and are referenced dynamically via [`app/services/secret_manager.py`](../app/services/secret_manager.py) or Cloud Run `--set-secrets`.
- [x] **Map & Geocoding Strategy:** Evaluated **Google Maps Platform** vs. **Esri ArcGIS/USGS NAIP** vs. **Mapbox** vs. **HERE** vs. **OpenStreetMap** (documented in [`docs/GCP_SETUP_INSTRUCTIONS.md`](./GCP_SETUP_INSTRUCTIONS.md)). Selected **Google Maps Platform** as primary for #1 rural US rooftop geocoding accuracy + 15cm leaf-off aerials (10,000 free calls/mo per SKU), with optional **Esri/USGS NAIP** aerial tile fallback for high-volume scale.

---

## 2. GitHub Backlog Tasks (Post-MVP Roadmap)

- [x] **Task 1: GCP Secret Manager, GitHub Actions CI/CD & Live Cloud Run Deployment**
  - `DEV` (`dev` branch $\rightarrow$ `tanksquare-api-dev`): `https://tanksquare-api-dev-339694762975.us-central1.run.app/`
  - `PROD` (`main` branch $\rightarrow$ `tanksquare-api-prod`, manual dispatch only): `https://tanksquare-api-prod-339694762975.us-central1.run.app/`
- [ ] **Task 2: Approach 2 — Mobile-Browser Tanker Driver View (`/driver`) & Workflow Refinements**
  - Review how the fuel truck driver launches the view from their in-cab tablet or phone browser (Cargas Mobile / ADD Systems Raven link vs. daily route view).
  - Verify offline caching behavior via [`app/static/sw.js`](../app/static/sw.js) when driving into rural zero-bar dead zones.
  - Decide whether drivers can snap a quick verification photo of the tank/fill pipe on delivery day.
- [ ] **Task 3: "Suggested Parking" (`P1`) vs. CDL Driver-Verified Parking Workflow**
  - Loaded propane bobtails / heating-oil tankers weigh **26,000–33,000 lbs**; resident selections save as `SUGGESTED` (*Pending CDL Driver Verification*) until a CDL driver confirms or relocates `P1` to `DRIVER_VERIFIED`.
  - Decide whether a driver adjustment notifies the homeowner or remains internal to dispatch/drivers.
- [ ] **Task 4: Propane Provider Billing & Pricing Model (B2B SaaS — 100% Free for Residents)**
  - Evaluate Flat Monthly SaaS Tiers by dealer size vs. Per-Verified-TankSquare Pass fee.
- [ ] **Task 5: Low-Tech / Elderly Homeowner Ease-of-Use Refinements**
  - Review adding a *"Need Help? Let Dispatch Pin It With You on a 30-Second Call"* option and large-font accessibility toggle.
- [ ] **Task 6: Data Privacy, Homeowner Consent & Multi-Vendor Ownership Rules**
  - Review strict tenant isolation (`vendor_id`), signed/expiring GCS photo URLs, and retention policies when a homeowner moves or switches fuel providers.
- [ ] **Task 7: E-Commerce / Package Delivery "Context Pass" Expansion**
  - Future product expansion after TankSquare (Propane & Heating Oil).
