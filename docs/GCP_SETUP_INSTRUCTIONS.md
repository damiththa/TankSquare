# TankSquare — Google Cloud Shell Setup, Map Provider Analysis & Secret Manager Guide

> **Architecture Decision:** Everything is built and deployed directly in **Google Cloud Shell** (`https://shell.cloud.google.com`) using a **Single Google Cloud Project** to cleanly isolate **`DEV` (`dev` branch)** and **`PROD` (`main` branch)**—requiring **zero local GCP CLI setup** on your Mac.

---

## 1. Single-Project `DEV` vs. `PROD` Isolation in GCP

Inside your single GCP Project (`$PROJECT_ID`), `DEV` and `PROD` are completely isolated:

| Layer | `DEV` Environment (`dev` Git branch) | `PROD` Environment (`main` Git branch) |
| :--- | :--- | :--- |
| **Cloud Run Service** | `tanksquare-api-dev` | `tanksquare-api-prod` |
| **Firestore Collections** | `dev_vendors`, `dev_sessions`, `dev_site_passes`, `dev_webhook_logs` | `prod_vendors`, `prod_sessions`, `prod_site_passes`, `prod_webhook_logs` |
| **Cloud Storage Paths** | `gs://${PROJECT_ID}-media/dev/...` | `gs://${PROJECT_ID}-media/prod/...` |
| **Demo Data Seeding** | `SEED_DEMO_DATA=true` (3 demo fuel dealers) | `SEED_DEMO_DATA=false` (strictly live B2B tenants) |

---

## 2. Step-by-Step Instructions in Google Cloud Shell (Browser)

> **Important Note on Project Number vs. Project ID:**
> GCP gives every project both a numeric **Project Number** (e.g., `339694762975`) and a string **Project ID** (e.g., `tanksquare-...`). Commands like `gcloud firestore` and `gcloud artifacts` require the string **Project ID**. Step 1 below automatically resolves your string `PROJECT_ID` from either value!

### Step 1: Resolve Your String `PROJECT_ID` & Set It in Cloud Shell
Copy and paste this into Cloud Shell (works whether you pass your Project Number or Project ID):
```bash
export PROJECT_NUMBER="339694762975"
export PROJECT_ID=$(gcloud projects describe $PROJECT_NUMBER --format="value(projectId)")
echo "Resolved String Project ID: $PROJECT_ID"
gcloud config set project "$PROJECT_ID"
```

### Step 2: Enable Required GCP & Google Maps APIs
```bash
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  maps-backend.googleapis.com \
  geocoding-backend.googleapis.com \
  --project="$PROJECT_ID"
```

### Step 3: Add Your Secrets to Google Cloud Secret Manager (Silent Input)
*(If you already ran this step earlier, your 4 secrets are already saved in Secret Manager! This version safely creates or updates them using `--project="$PROJECT_ID"`):*
```bash
upsert_secret() {
  local name="$1"
  local val="$2"
  gcloud secrets describe "$name" --project="$PROJECT_ID" >/dev/null 2>&1 || \
    gcloud secrets create "$name" --replication-policy="automatic" --project="$PROJECT_ID"
  printf "%s" "$val" | gcloud secrets versions add "$name" --data-file=- --project="$PROJECT_ID"
}

read -r -s -p "Paste your Google Maps API Key (or press Enter for PLACEHOLDER): " MAPS_KEY && echo ""
upsert_secret "tanksquare-google-maps-api-key" "${MAPS_KEY:-PLACEHOLDER_MAPS_KEY}"

read -r -s -p "Paste your what3words API Key (or press Enter for PLACEHOLDER): " W3W_KEY && echo ""
upsert_secret "tanksquare-w3w-api-key" "${W3W_KEY:-PLACEHOLDER_W3W_KEY}"

upsert_secret "tanksquare-session-signing-secret" "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32), end="")')"
upsert_secret "tanksquare-vendor-api-secret" "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32), end="")')"
unset MAPS_KEY W3W_KEY
```

### Step 4: Grant Cloud Run Access & Create Firestore, Storage & Artifact Registry
```bash
# 1. Allow Cloud Run service account to read the 4 secrets from Secret Manager
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# 2. Create Native Firestore Database (requires string $PROJECT_ID)
gcloud firestore databases create \
  --location=nam5 \
  --type=firestore-native \
  --project="$PROJECT_ID"

# 3. Ensure GCS Bucket exists (ignores if already created)
gcloud storage buckets create "gs://${PROJECT_ID}-media" \
  --location=us-central1 \
  --uniform-bucket-level-access \
  --project="$PROJECT_ID" 2>/dev/null || true

# 4. Create Artifact Registry Docker Repo (requires string $PROJECT_ID)
gcloud artifacts repositories create tanksquare \
  --repository-format=docker \
  --location=us-central1 \
  --project="$PROJECT_ID"
```

---

## 3. Reference: Google AI Pro Plan & Map Provider Comparison (2026)

| Provider | Rural US Rooftop Accuracy | Rural Aerial Clarity (Zoom 19–21) | Monthly Free Tier (2026) | Cost After Free Tier | Verdict for TankSquare |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Google Maps Platform** | **#1 (96–99%)** — Lands directly on rural house roofs (not the highway mailbox 600 ft away). | **#1 (15–30cm aerials)** — Sharpest leaf-off view of driveways, sheds & propane domes. | **10,000 free/mo per SKU** (10k Geocodes + 10k Dynamic Maps + 10k Static Maps). | $5.00/1k geocodes; $7.00/1k map loads. | **Best Primary Choice** — Highest rural rooftop & driveway accuracy; lives inside the same GCP project & Secret Manager. |
| **2. Esri ArcGIS + USGS NAIP** | **#2 (93–96%)** — Uses county GIS parcel & address points. | **#1 Tied (15–30cm)** — Blends US Gov **USGS NAIP** public-domain aerials + Nearmap (20cm). | **2,000,000 free basemap tiles/mo** + 20k non-stored geocodes/mo. | $0.15/1k tiles; $0.50/1k geocodes. | **Best Low-Cost Aerial Tile Backup** if tile volume exceeds 10k/mo. |
| **3. Mapbox** | **#3 (85–90%)** — Often falls back to street-interpolation on long rural driveways. | **#3 (30–50cm)** — Maxar satellite; can blur at Zoom 20+ in rural counties. | **50,000 free map loads/mo** + **100,000 free geocodes/mo**. | $5.00/1k map loads; $0.75–$5.00/1k geocodes. | Good developer SDK, but weaker rural US rooftop precision than Google. |
| **4. HERE Technologies** | **#3 (88–92%)** — Strong road network, weaker backyard/rooftop pin placement. | **#4** — Built for road navigation, not backyard tank inspection. | **30,000 free map loads/mo** + **250,000 free geocodes/mo**. | $1.00/1k geocodes after 250k. | Best saved for future **CDL Hazmat Truck Routing** (bridge weights/tunnels). |
| **5. OpenStreetMap (Nominatim)** | **Poor in Rural US (~60–75%)** — Missing rural house numbers; drops pin on road center. | **None built-in** (vector streets only; requires external aerial tiles). | **100% Free** | $0 | Too inaccurate for rural US residential addresses on its own. |
