# TankSquare — Parked Roadmap, Reminders & Decision Tracker

> **Purpose:** This file is tracked in Git across `dev` and `main` so we have a single source of truth for all parked topics, architectural guardrails, and upcoming items to review together.

---

## 1. Locked-In Architectural & Business Guardrails (Completed)

- [x] **Product Name:** **TankSquare** (`https://github.com/damiththa/TankSquare.git`).
- [x] **100% Browser-Based (Zero App Install):** Both the Resident Portal (`/`) and the Tanker Driver Mobile View (`/driver`) run in standard mobile and desktop browsers (Safari, Chrome, Edge) with zero app store downloads or desktop software installs.
- [x] **Zero Separate Account for Residents:** Residents never sign up for or log into a TankSquare account (`resident_account_required = False`). Identity is passed via a pre-authenticated session token in the propane vendor's `<script>` tag (`widget.js`) or SMS/email magic link.
- [x] **100% Free for Residents:** Residents are never billed or shown payment screens (`resident_billing_enabled = False`). TankSquare is strictly B2B vendor-paid.
- [x] **Single-Project Cloud-Direct GCP Isolation (Zero SQLite):** Both `DEV` (`dev` branch $\rightarrow$ `tanksquare-api-dev`, `dev_*` Firestore collections, `dev/` GCS prefix) and `PROD` (`main` branch $\rightarrow$ `tanksquare-api-prod`, `prod_*` Firestore collections, `prod/` GCS prefix) run isolated inside a single GCP project to maximize the **Google AI Pro ($10/mo GCP credit)** and **GCP Free Tier**.
- [x] **Zero Hardcoded Secrets:** All sensitive keys (`GOOGLE_MAPS_API_KEY`, `W3W_API_KEY`, `SESSION_SIGNING_SECRET`, `VENDOR_API_SHARED_SECRET`) live in **Google Cloud Secret Manager** and are referenced dynamically via [`app/services/secret_manager.py`](../app/services/secret_manager.py) or Cloud Run `--set-secrets`.
- [x] **Map & Geocoding Strategy:** Evaluated **Google Maps Platform** vs. **Esri ArcGIS/USGS NAIP** vs. **Mapbox** vs. **HERE** vs. **OpenStreetMap** (documented in [`docs/GCP_SETUP_INSTRUCTIONS.md`](./GCP_SETUP_INSTRUCTIONS.md)). Selected **Google Maps Platform** as primary for #1 rural US rooftop geocoding accuracy + 15cm leaf-off aerials (10,000 free calls/mo per SKU), with optional **Esri/USGS NAIP** aerial tile fallback for high-volume scale.

---

## 2. Active Parked Reminder List (To Review & Refine Next)

### Item 1: GCP Secret Manager Setup & Pushing `dev` / `main` to GitHub
- **Status:** 🟡 Instructions ready in [`docs/GCP_SETUP_INSTRUCTIONS.md`](./GCP_SETUP_INSTRUCTIONS.md).
- **Next Step:** Add the 4 secrets in Google Cloud Secret Manager and push `dev` and `main` branches to `https://github.com/damiththa/TankSquare.git`.

### Item 2: Approach 2 — Mobile-Browser Tanker Driver View (`/driver`) & Workflow Refinements
- **Status:** 🟡 Initial browser view & API built ([`app/static/driver.html`](../app/static/driver.html), [`app/routers/driver.py`](../app/routers/driver.py)); ready for UX review.
- **Key Questions to Review Together:**
  - How the fuel truck driver launches the view from their in-cab tablet or phone browser (Cargas Mobile / ADD Systems Raven link vs. daily route view).
  - Offline caching behavior via [`app/static/sw.js`](../app/static/sw.js) when driving into rural zero-bar dead zones.
  - Whether drivers should also be able to snap a quick verification photo of the tank/fill pipe on delivery day.

### Item 3: "Suggested Parking" (`P1`) vs. Driver-Verified Parking Workflow
- **Status:** 🟡 Core state machine implemented (`parking_status: "suggested" | "driver_verified"`).
- **Why We Parked This:**
  - A loaded propane bobtail or heating-oil tanker weighs **26,000–33,000 lbs** (class 7/8 Hazmat vehicle).
  - Homeowners might click a driveway square over a buried septic tank, weak culvert, or beneath low tree branches.
  - Therefore, any homeowner selection is saved strictly as **`SUGGESTED` (*Pending CDL Driver Verification*)** along with a 33,000-lb weight/septic disclaimer checkbox.
  - On first delivery, the CDL driver either taps **"1-Tap Confirm Suggested Parking"** or taps the actual square where they safely parked to upgrade the pass to **`DRIVER_VERIFIED`**.
- **To Review:** Should a driver adjustment automatically notify the homeowner (e.g., *"Your driver verified safe tanker parking at square R12-C11"*), or stay internal for dispatchers/drivers?

### Item 4: Propane Provider Billing & Pricing Model (B2B SaaS)
- **Status:** ⏳ Parked for business model discussion.
- **Core Rule:** **100% Free for Residents** — all billing is paid by the propane/heating-oil dealer.
- **Options to Evaluate Together:**
  1. **Flat Monthly SaaS Tier by Dealer Size** (e.g., Starter up to 1,500 active tanks; Growth up to 5,000 tanks; Enterprise/Co-op).
  2. **Per-Verified-TankSquare Pass Fee** (e.g., small annual or one-time fee per mapped property, similar to Plaid's per-connected-account model).
  3. **ROI Anchor for Dealers:** Avoiding just 1 winter "no-fill / couldn't find buried dome / short-hose" dry-run truck roll saves a propane dealer **$150–$300** in CDL driver hours and fuel.

### Item 5: Low-Tech / Elderly Homeowner Ease-of-Use Refinements
- **Status:** 🟡 Initial 3-step zero-jargon flow built; ready for usability review.
- **Built-in Simplifications So Far:**
  - Resident never sees or types `what3words` slashes (`///`) unless they want to—they just click visual squares on their roof/driveway photo.
  - Step 1 auto-centers on their pre-filled address; Step 2 has large color-coded buttons; Step 3 is a single save button with no password or account creation.
- **To Review:** Adding a "Need Help? Let Dispatch Pin It With You on a 30-Second Call" button or large-font accessibility toggle.

### Item 6: Data Privacy, Homeowner Consent & Multi-Vendor Ownership Rules
- **Status:** ⏳ Parked for legal/privacy architecture review.
- **Key Questions to Review Together:**
  - **Strict Tenant Isolation (`vendor_id`):** Ensuring Vendor A (`gmp_vt`) can never query or view Vendor B's (`aho_ny`) customer passes or GCS photos.
  - **Photo & Gate-Code Privacy:** Signed/expiring GCS URLs vs. vendor-scoped access tokens; automatic redaction or retention policies when a homeowner moves or switches fuel providers.

### Item 7: Earlier Option 1 — E-Commerce / Package Delivery "Context Pass"
- **Status:** ⏳ Parked for future product expansion after TankSquare (Propane & Heating Oil).
