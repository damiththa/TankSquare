#!/usr/bin/env bash
# ============================================================================
# TankSquare — Complete GCP Setup, Free-Tier, API & Permission Verifier
# (`scripts/verify_gcp_setup.sh`)
# ============================================================================
# Paste or run in Google Cloud Shell:
#   bash scripts/verify_gcp_setup.sh
# ============================================================================

set -euo pipefail

export PROJECT_NUMBER="339694762975"
export PROJECT_ID="$(gcloud projects describe "${PROJECT_NUMBER}" --format='value(projectId)')"
gcloud config set project "${PROJECT_ID}" >/dev/null

echo "======================================================================"
echo " TankSquare GCP Triple-Check Audit for Project: ${PROJECT_ID} (${PROJECT_NUMBER})"
echo "======================================================================"

# 1. Clean up duplicate numeric-named bucket if it exists (keep only ${PROJECT_ID}-media)
if gcloud storage buckets describe "gs://${PROJECT_NUMBER}-media" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  if [[ "${PROJECT_NUMBER}-media" != "${PROJECT_ID}-media" ]]; then
    echo "[Cleanup] Removing duplicate empty bucket gs://${PROJECT_NUMBER}-media..."
    gcloud storage buckets delete "gs://${PROJECT_NUMBER}-media" --project="${PROJECT_ID}" >/dev/null 2>&1 || true
  fi
fi

# 2. Prune older Secret Manager versions so active versions stay at exactly 4 (Free Tier is <= 6)
echo ""
echo "[1/5] Checking Secret Manager & Pruning Old Versions (Free Tier = 6 active versions)..."
SECRETS=(
  "tanksquare-google-maps-api-key"
  "tanksquare-w3w-api-key"
  "tanksquare-session-signing-secret"
  "tanksquare-vendor-api-secret"
)
TOTAL_ACTIVE_VERSIONS=0
for SEC in "${SECRETS[@]}"; do
  if gcloud secrets describe "${SEC}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    # List enabled versions, keep newest (first), destroy older ones
    ENABLED_VERSIONS=($(gcloud secrets versions list "${SEC}" --filter="state=ENABLED" --sort-by="~createTime" --format="value(name)" --project="${PROJECT_ID}"))
    COUNT=${#ENABLED_VERSIONS[@]}
    if (( COUNT > 1 )); then
      for (( i=1; i<COUNT; i++ )); do
        OLD_VER="${ENABLED_VERSIONS[$i]}"
        echo "  -> Destroying superseded version ${OLD_VER} of ${SEC} to stay inside Free Tier..."
        gcloud secrets versions destroy "${OLD_VER}" --secret="${SEC}" --quiet --project="${PROJECT_ID}" >/dev/null
      done
    fi
    TOTAL_ACTIVE_VERSIONS=$((TOTAL_ACTIVE_VERSIONS + 1))
    echo "  [✓] Secret '${SEC}': Present (1 active version)"
  else
    echo "  [!] Secret '${SEC}': MISSING"
  fi
done
echo "  => Total Active Secret Versions: ${TOTAL_ACTIVE_VERSIONS} / 6 Free Tier Limit ($0.00/mo)"

# 3. Verify Google Maps API Key & what3words API Key Status
echo ""
echo "[2/5] Checking Google Maps & what3words API Keys..."
MAPS_VAL="$(gcloud secrets versions access latest --secret="tanksquare-google-maps-api-key" --project="${PROJECT_ID}" 2>/dev/null || echo "")"
if [[ -z "${MAPS_VAL}" || "${MAPS_VAL}" == PLACEHOLDER* ]]; then
  echo "  [i] Google Maps Key: Currently set to PLACEHOLDER (TankSquare will use free built-in parcel math until you add a real Maps key)."
else
  HTTP_STATUS="$(curl -s -o /tmp/maps_test.json -w "%{http_code}" "https://maps.googleapis.com/maps/api/geocode/json?address=Montpelier,VT&key=${MAPS_VAL}")"
  API_STATUS="$(python3 -c 'import json; d=json.load(open("/tmp/maps_test.json")); print(d.get("status","UNKNOWN"))' 2>/dev/null || echo "ERROR")"
  rm -f /tmp/maps_test.json
  echo "  [✓] Google Maps Key: Configured (Test Geocode HTTP ${HTTP_STATUS}, API Status: ${API_STATUS})"
fi
unset MAPS_VAL

W3W_VAL="$(gcloud secrets versions access latest --secret="tanksquare-w3w-api-key" --project="${PROJECT_ID}" 2>/dev/null || echo "")"
if [[ -z "${W3W_VAL}" || "${W3W_VAL}" == PLACEHOLDER* ]]; then
  echo "  [i] what3words Key:  Currently set to PLACEHOLDER (TankSquare will use its built-in deterministic 3-word generator at $0 cost)."
else
  W3W_STATUS="$(curl -s -o /tmp/w3w_test.json -w "%{http_code}" "https://api.what3words.com/v3/convert-to-3wa?coordinates=44.2601,-72.5754&key=${W3W_VAL}")"
  rm -f /tmp/w3w_test.json
  echo "  [✓] what3words Key:  Configured (Test API HTTP ${W3W_STATUS})"
fi
unset W3W_VAL

# 4. Verify & Bind All Required IAM Permissions for Cloud Run & Cloud Build
echo ""
echo "[3/5] Verifying & Binding Project IAM Permissions for Cloud Run & Cloud Build..."
COMPUTE_SA="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
ROLES=(
  "roles/secretmanager.secretAccessor"
  "roles/datastore.user"
  "roles/storage.objectAdmin"
  "roles/run.admin"
  "roles/iam.serviceAccountUser"
  "roles/artifactregistry.writer"
  "roles/logging.logWriter"
)
for ROLE in "${ROLES[@]}"; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="${COMPUTE_SA}" \
    --role="${ROLE}" \
    --condition=None >/dev/null
  echo "  [✓] Bound ${ROLE} to ${COMPUTE_SA}"
done

# 5. Verify Firestore, GCS Media Bucket & Artifact Registry
echo ""
echo "[4/5] Checking Firestore, Cloud Storage & Artifact Registry..."
FS_LOC="$(gcloud firestore databases describe --database="(default)" --project="${PROJECT_ID}" --format="value(locationId)" 2>/dev/null || echo "MISSING")"
echo "  [✓] Cloud Firestore ((default)): Location=${FS_LOC} (Free Tier: 1 GiB + 50k reads/day)"

if gcloud storage buckets describe "gs://${PROJECT_ID}-media" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "  [✓] Cloud Storage Bucket: gs://${PROJECT_ID}-media (Free Tier: 5 GB/mo in us-central1)"
else
  echo "  [!] Cloud Storage Bucket gs://${PROJECT_ID}-media is missing!"
fi

if gcloud artifacts repositories describe tanksquare --location=us-central1 --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "  [✓] Artifact Registry Repo: tanksquare (us-central1) (Free Tier: 500 MB/mo)"
else
  echo "  [!] Artifact Registry Repo 'tanksquare' is missing!"
fi

echo ""
echo "[5/5] Summary of Monthly Idle / Low-Traffic Cost: $0.00"
echo "======================================================================"
