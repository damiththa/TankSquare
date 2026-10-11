# TankSquare — Single-Project GCP Setup, Map Provider Analysis & Secret Manager Guide

> **Architecture Decision:** TankSquare uses a **Single Google Cloud Project** to cleanly isolate **`DEV` (`dev` branch)** and **`PROD` (`main` branch)** while maximizing your **Google AI Pro ($10/mo GCP credit)** and **GCP / Google Maps Free Tiers**.

---

## 1. How Single-Project `DEV` vs. `PROD` Isolation Works in GCP

Inside your single GCP Project (`YOUR_GCP_PROJECT_ID`), `DEV` and `PROD` never collide:

| Layer | `DEV` Environment (`dev` Git branch) | `PROD` Environment (`main` Git branch) |
| :--- | :--- | :--- |
| **Cloud Run Service** | `tanksquare-api-dev` | `tanksquare-api-prod` |
| **Firestore Collections** | `dev_vendors`, `dev_sessions`, `dev_site_passes`, `dev_webhook_logs` | `prod_vendors`, `prod_sessions`, `prod_site_passes`, `prod_webhook_logs` |
| **Cloud Storage Paths** | `gs://YOUR_GCP_PROJECT_ID-media/dev/...` | `gs://YOUR_GCP_PROJECT_ID-media/prod/...` |
| **Secret Manager Keys** | `tanksquare-google-maps-api-key`, `tanksquare-w3w-api-key`, `tanksquare-session-signing-secret`, `tanksquare-vendor-api-secret` | Same Secret Manager names (or `-prod` suffixed when rotating production keys) |
| **Demo Data Seeding** | `SEED_DEMO_DATA=true` (3 demo fuel dealers) | `SEED_DEMO_DATA=false` (strictly live B2B tenants) |

---

## 2. Google AI Pro Plan & Map Provider Comparison (2026)

### Does Google AI Pro Include GCP & Google Maps Credits?
- **GCP Compute / Storage / AI Credits:** **Yes.** Linking your **Google AI Pro** subscription to the [Google Developer Program](https://developers.google.com/program) provides **$10/month in Google Cloud credits** (which roll over for up to 12 months). Combined with the GCP Free Tier (2M Cloud Run requests/mo + 1 GiB Firestore + 50k reads/day + 5 GB Cloud Storage), your backend infrastructure cost for `DEV` + `PROD` in Stage 1 is **$0/month**.
- **Google Maps Platform Free Tier (Post-March 2025 Model):** While Google AI Pro's $10 credit is for GCP/AI Studio, Google Maps Platform automatically gives every billing account **10,000 free calls/month per Essentials SKU** (10,000 free Rooftop Geocodes/mo + 10,000 free Dynamic Map loads/mo + 10,000 free Static Map loads/mo).

### Head-to-Head Comparison: Google Maps vs. Esri/USGS vs. Mapbox vs. HERE vs. OpenStreetMap

| Provider | Rural US Rooftop Accuracy | Rural Aerial Clarity (Zoom 19–21) | Monthly Free Tier (2026) | Cost After Free Tier | Verdict for TankSquare |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Google Maps Platform** | **#1 (96–99%)** — Lands directly on rural house roofs (not the highway mailbox 600 ft away). | **#1 (15–30cm aerials)** — Sharpest leaf-off view of driveways, sheds & propane domes. | **10,000 free/mo per SKU** (10k Geocodes + 10k Dynamic Maps + 10k Static Maps). | $5.00/1k geocodes; $7.00/1k map loads. | **Best Primary Choice** — Highest rural rooftop & driveway accuracy; lives inside the same GCP project & Secret Manager. |
| **2. Esri ArcGIS + USGS NAIP** | **#2 (93–96%)** — Uses county GIS parcel & address points. | **#1 Tied (15–30cm)** — Blends US Gov **USGS NAIP** public-domain aerials + Nearmap (20cm). | **2,000,000 free basemap tiles/mo** + 20k non-stored geocodes/mo. | $0.15/1k tiles; $0.50/1k geocodes. | **Best Low-Cost Aerial Tile Backup** if tile volume exceeds 10k/mo. |
| **3. Mapbox** | **#3 (85–90%)** — Often falls back to street-interpolation on long rural driveways. | **#3 (30–50cm)** — Maxar satellite; can blur at Zoom 20+ in rural counties. | **50,000 free map loads/mo** + **100,000 free geocodes/mo**. | $5.00/1k map loads; $0.75–$5.00/1k geocodes. | Good developer SDK, but weaker rural US rooftop precision than Google. |
| **4. HERE Technologies** | **#3 (88–92%)** — Strong road network, weaker backyard/rooftop pin placement. | **#4** — Built for road navigation, not backyard tank inspection. | **30,000 free map loads/mo** + **250,000 free geocodes/mo**. | $1.00/1k geocodes after 250k. | Best saved for future **CDL Hazmat Truck Routing** (bridge weights/tunnels). |
| **5. OpenStreetMap (Nominatim)** | **Poor in Rural US (~60–75%)** — Missing rural house numbers; drops pin on road center. | **None built-in** (vector streets only; requires external aerial tiles). | **100% Free** | $0 | Too inaccurate for rural US residential addresses on its own. |

---

## 3. Step-by-Step Instructions: Adding Keys to Google Cloud Secret Manager

You can run these commands directly in **[Google Cloud Shell](https://shell.cloud.google.com/)** (top-right `>_` icon in your Google Cloud Console) or your Mac terminal. **You never need to paste your raw API keys into chat or commit them to Git.**

### Step 1: Set Your Single GCP Project ID & Enable APIs
Replace `YOUR_GCP_PROJECT_ID` with your actual Project ID from the Google Cloud Console:
```bash
export PROJECT_ID="YOUR_GCP_PROJECT_ID"
gcloud config set project $PROJECT_ID

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

### Step 2: Create Your Google Maps API Key (In GCP Console or CLI)
1. In the Google Cloud Console, go to **APIs & Services $\rightarrow$ Credentials** (or **Google Maps Platform $\rightarrow$ Keys & Credentials**).
2. Click **"+ Create Credentials" $\rightarrow$ "API key"** and copy the generated key.
3. *(Recommended Security)* Restrict the key to **Maps JavaScript API**, **Maps Static API**, and **Geocoding API**.

### Step 3: Store All 4 Secrets in Google Cloud Secret Manager
Run these 4 commands in Cloud Shell (replacing `PASTE_YOUR_GOOGLE_MAPS_KEY_HERE` and `PASTE_YOUR_W3W_KEY_HERE`—or leave `PLACEHOLDER` if you want to add the W3W key later):

```bash
# 1. Store Google Maps Platform API Key
printf "PASTE_YOUR_GOOGLE_MAPS_KEY_HERE" | \
  gcloud secrets create tanksquare-google-maps-api-key \
  --replication-policy="automatic" \
  --data-file=-

# 2. Store what3words API Key (or placeholder until ready)
printf "PASTE_YOUR_W3W_KEY_HERE" | \
  gcloud secrets create tanksquare-w3w-api-key \
  --replication-policy="automatic" \
  --data-file=-

# 3. Auto-generate & store 32-byte Resident Zero-Login Session Signing Secret
python3 -c "import secrets; print(secrets.token_urlsafe(32), end='')" | \
  gcloud secrets create tanksquare-session-signing-secret \
  --replication-policy="automatic" \
  --data-file=-

# 4. Auto-generate & store 32-byte B2B Vendor API Shared Secret
python3 -c "import secrets; print(secrets.token_urlsafe(32), end='')" | \
  gcloud secrets create tanksquare-vendor-api-secret \
  --replication-policy="automatic" \
  --data-file=-
```

*(Note: If you ever rotate or update a key later, just run:)*
```bash
printf "NEW_KEY_VALUE" | gcloud secrets versions add tanksquare-google-maps-api-key --data-file=-
```

### Step 4: Grant Cloud Run Permission to Read Your Secrets
Run this block so your Cloud Run service account can mount those secrets at runtime:
```bash
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### Step 5: Create Firestore Database & Media Bucket (One-Time per Project)
```bash
# Create Native Firestore Database (shared by dev_* and prod_* collections)
gcloud firestore databases create --location=nam5 --type=firestore-native

# Create GCS Bucket for Tank/Driveway Photos (shared by dev/ and prod/ folders)
gcloud storage buckets create gs://${PROJECT_ID}-media \
  --location=us-central1 \
  --uniform-bucket-level-access
```
