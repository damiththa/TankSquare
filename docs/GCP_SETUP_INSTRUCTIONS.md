# TankSquare — Google Cloud Platform (GCP) Setup & Secret Manager Guide

> **Zero Hardcoded Secrets Policy:** TankSquare never stores API keys, signing secrets, or service account JSON files in Git. All sensitive values live in **Google Cloud Secret Manager** and are referenced dynamically at runtime.

---

## 1. What GCP Information We Need From You

To connect this repository directly to your Google Cloud account for **`DEV` (`dev` branch)** and **`PROD` (`main` branch)**, here is the only information needed:

1. **Your GCP Project ID(s):**
   - **Option A (Recommended — Two Isolated Projects):**
     - `GCP_PROJECT_ID_DEV` (e.g., `tanksquare-dev-12345`)
     - `GCP_PROJECT_ID_PROD` (e.g., `tanksquare-prod-12345`)
   - **Option B (Single GCP Project for Stage 1 Free Tier):**
     - One project ID (e.g., `tanksquare-cloud`) — TankSquare automatically isolates `DEV` and `PROD` inside the same project using `dev_*` vs `prod_*` Firestore collection prefixes and `tanksquare-api-dev` vs `tanksquare-api-prod` Cloud Run services!
2. **Your Preferred GCP Region:**
   - Default is `us-central1` (Iowa) or `us-east1` (South Carolina) — both qualify for the **GCP Cloud Run & Firestore Free Tier**.

---

## 2. Step-by-Step GCP Setup Commands (Run in Google Cloud Shell or Terminal)

### Step 1: Authenticate & Set Your Project
```bash
gcloud auth login
gcloud config set project YOUR_GCP_PROJECT_ID
```

### Step 2: Enable Required GCP APIs
```bash
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com
```

### Step 3: Create the Cloud Firestore Database (Native Mode)
```bash
gcloud firestore databases create \
  --location=nam5 \
  --type=firestore-native
```

### Step 4: Create the Google Cloud Storage Bucket for Tank/Driveway Photos
```bash
gcloud storage buckets create gs://YOUR_GCP_PROJECT_ID-media \
  --location=us-central1 \
  --uniform-bucket-level-access
```

### Step 5: Store Sensitive Keys in Google Cloud Secret Manager (Never in Git!)
Run these commands to store your secrets safely in **GCP Secret Manager** (you can put placeholder values initially in `DEV` and update them anytime):

```bash
# 1. Google Maps Platform API Key (Satellite Tiles & Rooftop Geocoding)
printf "YOUR_GOOGLE_MAPS_KEY" | gcloud secrets create tanksquare-google-maps-api-key --data-file=-

# 2. what3words v3 API Key (On-Demand 3m Square Resolution)
printf "YOUR_W3W_API_KEY" | gcloud secrets create tanksquare-w3w-api-key --data-file=-

# 3. Resident Zero-Login Session Signing Secret (Auto-generated 32-byte random secret)
python3 -c "import secrets; print(secrets.token_urlsafe(32), end='')" | \
  gcloud secrets create tanksquare-session-signing-secret --data-file=-

# 4. B2B Vendor API Shared Secret
python3 -c "import secrets; print(secrets.token_urlsafe(32), end='')" | \
  gcloud secrets create tanksquare-vendor-api-secret --data-file=-
```

### Step 6: Create Artifact Registry & Deploy to Cloud Run
```bash
# Create Docker repository in Artifact Registry
gcloud artifacts repositories create tanksquare \
  --repository-format=docker \
  --location=us-central1

# Deploy DEV (`dev` branch)
gcloud builds submit --config deploy/cloudbuild.dev.yaml

# Deploy PROD (`main` branch)
gcloud builds submit --config deploy/cloudbuild.prod.yaml
```
