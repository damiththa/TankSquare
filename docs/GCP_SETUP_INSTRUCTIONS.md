# TankSquare — Google Cloud Shell Setup, Map Provider Analysis & Secret Manager Guide

> **Architecture Decision:** Everything is built and deployed directly in **Google Cloud Shell** (`https://shell.cloud.google.com`) using a **Single Google Cloud Project** to cleanly isolate **`DEV` (`dev` branch)** and **`PROD` (`main` branch)**—requiring **zero local GCP CLI setup** on your Mac.

---

## 1. Single-Project `DEV` vs. `PROD` Isolation in GCP

Inside your single GCP Project (`YOUR_GCP_PROJECT_ID`), `DEV` and `PROD` are completely isolated:

| Layer | `DEV` Environment (`dev` Git branch) | `PROD` Environment (`main` Git branch) |
| :--- | :--- | :--- |
| **Cloud Run Service** | `tanksquare-api-dev` | `tanksquare-api-prod` |
| **Firestore Collections** | `dev_vendors`, `dev_sessions`, `dev_site_passes`, `dev_webhook_logs` | `prod_vendors`, `prod_sessions`, `prod_site_passes`, `prod_webhook_logs` |
| **Cloud Storage Paths** | `gs://YOUR_GCP_PROJECT_ID-media/dev/...` | `gs://YOUR_GCP_PROJECT_ID-media/prod/...` |
| **Demo Data Seeding** | `SEED_DEMO_DATA=true` (3 demo fuel dealers) | `SEED_DEMO_DATA=false` (strictly live B2B tenants) |

---

## 2. Step-by-Step Instructions in Google Cloud Shell (Browser)

Because **Google Cloud Shell** runs directly inside your browser at [console.cloud.google.com](https://console.cloud.google.com/) (click the **`>_` Activate Cloud Shell** icon in the top-right corner), `gcloud`, `git`, and your Google account permissions are **already pre-authenticated**.

### Step 1: Open Google Cloud Shell & Select Your Project
In the Cloud Shell terminal at the bottom of your browser, set your project ID:
```bash
export PROJECT_ID="YOUR_GCP_PROJECT_ID"
gcloud config set project $PROJECT_ID
```

### Step 2: Enable Required GCP & Google Maps APIs
Copy and paste this block into Cloud Shell:
```bash
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  maps-backend.googleapis.com \
  geocoding-backend.googleapis.com
```

### Step 3: Add Your Secrets to Google Cloud Secret Manager (Hidden Input)
Copy and paste this block into Cloud Shell. It uses `read -s` (silent/hidden input) so when you paste your Google Maps API key, **nothing is echoed to the screen or saved in your Cloud Shell history**:

```bash
# 1. Google Maps Platform API Key (Silent prompt — paste key and press Enter)
read -r -s -p "Paste your Google Maps API Key (or press Enter for PLACEHOLDER): " MAPS_KEY && echo ""
printf "%s" "${MAPS_KEY:-PLACEHOLDER_MAPS_KEY}" | \
  gcloud secrets create tanksquare-google-maps-api-key --replication-policy="automatic" --data-file=-

# 2. what3words v3 API Key (Silent prompt — paste key or press Enter for PLACEHOLDER)
read -r -s -p "Paste your what3words API Key (or press Enter for PLACEHOLDER): " W3W_KEY && echo ""
printf "%s" "${W3W_KEY:-PLACEHOLDER_W3W_KEY}" | \
  gcloud secrets create tanksquare-w3w-api-key --replication-policy="automatic" --data-file=-

# 3. Auto-Generated 32-Byte Resident Zero-Login Session Signing Secret
python3 -c 'import secrets; print(secrets.token_urlsafe(32), end="")' | \
  gcloud secrets create tanksquare-session-signing-secret --replication-policy="automatic" --data-file=-

# 4. Auto-Generated 32-Byte B2B Vendor API Shared Secret
python3 -c 'import secrets; print(secrets.token_urlsafe(32), end="")' | \
  gcloud secrets create tanksquare-vendor-api-secret --replication-policy="automatic" --data-file=-

unset MAPS_KEY W3W_KEY
```

*(Or, once you clone the repo in Cloud Shell, you can simply run `bash scripts/setup_gcp_cloudshell.sh` which automates Steps 1–4 interactively!)*

### Step 4: Grant Cloud Run Permission to Read Secrets & Create Firestore + Storage
```bash
# Allow Cloud Run to read the 4 secrets from Secret Manager
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Create Native Firestore Database (shared by dev_* and prod_* collections)
gcloud firestore databases create --location=nam5 --type=firestore-native

# Create GCS Bucket for Tank/Driveway Photos (shared by dev/ and prod/ folders)
gcloud storage buckets create gs://${PROJECT_ID}-media \
  --location=us-central1 --uniform-bucket-level-access

# Create Artifact Registry Docker Repo for Cloud Run builds
gcloud artifacts repositories create tanksquare \
  --repository-format=docker --location=us-central1
```

### Step 5: Clone Your Repo in Cloud Shell & Deploy `DEV` or `PROD`
```bash
git clone https://github.com/damiththa/TankSquare.git
cd TankSquare

# Deploy DEV (`dev` branch -> Cloud Run `tanksquare-api-dev`)
git checkout dev
gcloud builds submit --config deploy/cloudbuild.dev.yaml

# Deploy PROD (`main` branch -> Cloud Run `tanksquare-api-prod`)
git checkout main
gcloud builds submit --config deploy/cloudbuild.prod.yaml
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
