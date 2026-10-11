# TankSquare — Local Mac Terminal GCP Setup, Map Provider Analysis & Secret Manager Guide

> **Architecture Decision:** TankSquare uses a **Single Google Cloud Project** to cleanly isolate **`DEV` (`dev` branch)** and **`PROD` (`main` branch)** while maximizing your **Google AI Pro ($10/mo GCP credit)** and **GCP / Google Maps Free Tiers**. Everything can be provisioned and managed **directly from your local Mac terminal**.

---

## 1. Permissions & Workspace Setup for Local Mac Terminal

1. **Antigravity Workspace Permission (Recommended):**
   - In Antigravity, open [`/Users/madushan/GitStuff/TankSquare`](file:///Users/madushan/GitStuff/TankSquare) as your **Active Workspace** (`File -> Open Folder...`).
   - Once set as your active workspace, Antigravity can run commands and tests inside `/Users/madushan/GitStuff/TankSquare` natively without prompting you for external folder permissions on every step.
2. **GCP IAM Permissions (On Your Google Account):**
   - Your personal Google account is the **Project Owner (`roles/owner`)** on your GCP project.
   - By running `gcloud auth login` and `gcloud auth application-default login` in your local Mac terminal, your Mac receives an OAuth token stored in `~/.config/gcloud/application_default_credentials.json`.
   - **Why this is cleaner & safer:** You **never** need to download or store a service-account `.json` key file on your Mac! Both [`app/services/gcp_store.py`](../app/services/gcp_store.py) and [`app/services/secret_manager.py`](../app/services/secret_manager.py) automatically use your local Application Default Credentials (`google.auth.default()`) to talk directly to Cloud Firestore, Cloud Storage, and Secret Manager.

---

## 2. Step-by-Step Local Mac Terminal Setup

### Step 1: Install the `gcloud` CLI on Your Mac (One-Time)
We checked your Mac's `/usr/local/bin` and noticed `gcloud` isn't installed yet. Run the official Google Cloud SDK macOS installer in your local terminal (`zsh`):
```bash
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
```

### Step 2: Authenticate Your Local Mac Terminal with GCP
Run these two commands in your Mac terminal (each will pop open a browser tab for you to sign in with your Google account):
```bash
# 1. Authenticate the gcloud CLI for project & Cloud Run commands
gcloud auth login

# 2. Authenticate Python Application Default Credentials (so FastAPI talks directly to Firestore & Secret Manager)
gcloud auth application-default login
```

### Step 3: Run Our Interactive Local Setup Script (`scripts/setup_gcp_local.py`)
Instead of typing long `gcloud` commands or pasting keys where they get saved in your `.zsh_history`, run our interactive Python provisioning script from `/Users/madushan/GitStuff/TankSquare`:
```bash
cd /Users/madushan/GitStuff/TankSquare
python3 scripts/setup_gcp_local.py
```

**What [`scripts/setup_gcp_local.py`](../scripts/setup_gcp_local.py) does automatically from your Mac terminal:**
1. Prompts for your single **`GCP_PROJECT_ID`**.
2. Uses hidden terminal prompts (`getpass`) so you can paste your **`GOOGLE_MAPS_API_KEY`** and **`W3W_API_KEY`** invisibly without them ever appearing on screen or in `.zsh_history`.
3. Auto-generates cryptographically random 32-byte secrets for `SESSION_SIGNING_SECRET` and `VENDOR_API_SHARED_SECRET`.
4. Enables all required GCP APIs (`run`, `firestore`, `storage`, `secretmanager`, `cloudbuild`, `artifactregistry`, `maps-backend`, `geocoding-backend`).
5. Uploads all 4 secrets directly into **Google Cloud Secret Manager**:
   - `tanksquare-google-maps-api-key`
   - `tanksquare-w3w-api-key`
   - `tanksquare-session-signing-secret`
   - `tanksquare-vendor-api-secret`
6. Binds `roles/secretmanager.secretAccessor` to your Cloud Run runtime service account.
7. Creates your Native **Cloud Firestore** database (`nam5`) and **Cloud Storage** media bucket (`gs://<PROJECT_ID>-media`).
8. Writes a **secret-free `.env` pointer file** (`USE_GCP_SECRET_MANAGER=true`, `GCP_PROJECT_ID=...`) that is ignored by Git so your local terminal runs pull secrets live from GCP Secret Manager.

---

## 3. Deploying `DEV` and `PROD` from Your Local Mac Terminal

Once [`scripts/setup_gcp_local.py`](../scripts/setup_gcp_local.py) finishes, you can deploy either environment to **Google Cloud Run** right from your Mac terminal:

```bash
# Deploy DEV (`dev` branch -> Cloud Run service `tanksquare-api-dev`, Firestore `dev_*`)
gcloud builds submit --config deploy/cloudbuild.dev.yaml

# Deploy PROD (`main` branch -> Cloud Run service `tanksquare-api-prod`, Firestore `prod_*`)
gcloud builds submit --config deploy/cloudbuild.prod.yaml
```

---

## 4. Reference: Google AI Pro Plan & Map Provider Comparison (2026)

| Provider | Rural US Rooftop Accuracy | Rural Aerial Clarity (Zoom 19–21) | Monthly Free Tier (2026) | Cost After Free Tier | Verdict for TankSquare |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Google Maps Platform** | **#1 (96–99%)** — Lands directly on rural house roofs (not the highway mailbox 600 ft away). | **#1 (15–30cm aerials)** — Sharpest leaf-off view of driveways, sheds & propane domes. | **10,000 free/mo per SKU** (10k Geocodes + 10k Dynamic Maps + 10k Static Maps). | $5.00/1k geocodes; $7.00/1k map loads. | **Best Primary Choice** — Highest rural rooftop & driveway accuracy; lives inside the same GCP project & Secret Manager. |
| **2. Esri ArcGIS + USGS NAIP** | **#2 (93–96%)** — Uses county GIS parcel & address points. | **#1 Tied (15–30cm)** — Blends US Gov **USGS NAIP** public-domain aerials + Nearmap (20cm). | **2,000,000 free basemap tiles/mo** + 20k non-stored geocodes/mo. | $0.15/1k tiles; $0.50/1k geocodes. | **Best Low-Cost Aerial Tile Backup** if tile volume exceeds 10k/mo. |
| **3. Mapbox** | **#3 (85–90%)** — Often falls back to street-interpolation on long rural driveways. | **#3 (30–50cm)** — Maxar satellite; can blur at Zoom 20+ in rural counties. | **50,000 free map loads/mo** + **100,000 free geocodes/mo**. | $5.00/1k map loads; $0.75–$5.00/1k geocodes. | Good developer SDK, but weaker rural US rooftop precision than Google. |
| **4. HERE Technologies** | **#3 (88–92%)** — Strong road network, weaker backyard/rooftop pin placement. | **#4** — Built for road navigation, not backyard tank inspection. | **30,000 free map loads/mo** + **250,000 free geocodes/mo**. | $1.00/1k geocodes after 250k. | Best saved for future **CDL Hazmat Truck Routing** (bridge weights/tunnels). |
| **5. OpenStreetMap (Nominatim)** | **Poor in Rural US (~60–75%)** — Missing rural house numbers; drops pin on road center. | **None built-in** (vector streets only; requires external aerial tiles). | **100% Free** | $0 | Too inaccurate for rural US residential addresses on its own. |
