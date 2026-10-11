#!/usr/bin/env bash
# ============================================================================
# TankSquare — Google Cloud Shell Provisioning Script (`scripts/setup_gcp_cloudshell.sh`)
# ============================================================================
# Run this directly inside Google Cloud Shell (https://shell.cloud.google.com):
#   bash scripts/setup_gcp_cloudshell.sh
#
# Automatically resolves a numeric Project Number (if provided) into the string
# GCP Project ID required by Firestore and Artifact Registry.
# ============================================================================

set -euo pipefail

echo "======================================================================"
echo " TankSquare — Google Cloud Shell Setup (Single Project: DEV & PROD)"
echo "======================================================================"

CURRENT_PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
read -r -p "1. Confirm your GCP Project ID or Project Number [${CURRENT_PROJECT}]: " INPUT_PROJECT
RAW_PROJECT="${INPUT_PROJECT:-$CURRENT_PROJECT}"

if [[ -z "${RAW_PROJECT}" ]]; then
  echo "[!] Error: GCP Project ID or Number is required."
  exit 1
fi

# Always resolve to the string Project ID (in case a numeric Project Number was entered)
PROJECT_ID="$(gcloud projects describe "${RAW_PROJECT}" --format='value(projectId)')"
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
echo "[✓] Resolved String Project ID: '${PROJECT_ID}' (Project Number: ${PROJECT_NUMBER})"

read -r -p "2. Enter preferred GCP Region [us-central1]: " INPUT_REGION
REGION="${INPUT_REGION:-us-central1}"

echo ""
echo "--- Secret Manager Input (Hidden input — characters will not appear) ---"
read -r -s -p "3. Paste your Google Maps Platform API Key (or press Enter for PLACEHOLDER): " MAPS_KEY
echo ""
MAPS_KEY="${MAPS_KEY:-PLACEHOLDER_MAPS_KEY}"

read -r -s -p "4. Paste your what3words API Key (or press Enter for PLACEHOLDER): " W3W_KEY
echo ""
W3W_KEY="${W3W_KEY:-PLACEHOLDER_W3W_KEY}"

SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32), end="")')"
VENDOR_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32), end="")')"

echo ""
echo "[1/5] Setting active project to string ID '${PROJECT_ID}' and enabling GCP APIs..."
gcloud config set project "${PROJECT_ID}"
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  maps-backend.googleapis.com \
  geocoding-backend.googleapis.com \
  --project="${PROJECT_ID}"

upsert_secret() {
  local sec_name="$1"
  local sec_val="$2"
  if ! gcloud secrets describe "${sec_name}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    gcloud secrets create "${sec_name}" --replication-policy="automatic" --project="${PROJECT_ID}"
  fi
  printf "%s" "${sec_val}" | gcloud secrets versions add "${sec_name}" --data-file=- --project="${PROJECT_ID}"
}

echo "[2/5] Storing secrets in Google Cloud Secret Manager..."
upsert_secret "tanksquare-google-maps-api-key" "${MAPS_KEY}"
upsert_secret "tanksquare-w3w-api-key" "${W3W_KEY}"
upsert_secret "tanksquare-session-signing-secret" "${SESSION_SECRET}"
upsert_secret "tanksquare-vendor-api-secret" "${VENDOR_SECRET}"

echo "[3/5] Granting Cloud Run service account access to Secret Manager..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" >/dev/null

echo "[4/5] Provisioning Native Firestore Database, GCS Bucket & Artifact Registry..."
gcloud firestore databases create --location=nam5 --type=firestore-native --project="${PROJECT_ID}" 2>/dev/null || true
gcloud storage buckets create "gs://${PROJECT_ID}-media" --location="${REGION}" --uniform-bucket-level-access --project="${PROJECT_ID}" 2>/dev/null || true
gcloud artifacts repositories create tanksquare --repository-format=docker --location="${REGION}" --project="${PROJECT_ID}" 2>/dev/null || true

echo "[5/5] Setup Complete! Your secrets and GCP resources are ready in '${PROJECT_ID}'."
echo "To deploy DEV:  gcloud builds submit --config deploy/cloudbuild.dev.yaml --project=${PROJECT_ID}"
echo "To deploy PROD: gcloud builds submit --config deploy/cloudbuild.prod.yaml --project=${PROJECT_ID}"
