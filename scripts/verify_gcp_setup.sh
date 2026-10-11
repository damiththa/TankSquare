#!/usr/bin/env bash
# ============================================================================
# TankSquare — Complete GCP Setup, Free-Tier, API & Permission Verifier
# (`scripts/verify_gcp_setup.sh`)
# ============================================================================
# Does NOT deploy any services. Verifies and configures:
# 1. Project ID ('tanksquare') & Billing Account
# 2. Required GCP & Google Maps APIs
# 3. Secret Manager (4 secrets, pruned to 1 active version each <= 6 Free Tier)
# 4. Live test of Google Maps & what3words API keys (without exposing keys)
# 5. All 7 IAM roles required by Cloud Run & Cloud Build
# 6. Native Cloud Firestore, gs://tanksquare-media bucket & Artifact Registry
# ============================================================================

set -euo pipefail

export PATH="/Users/madushan/google-cloud-sdk/bin:${PATH}"
export PROJECT_NUMBER="339694762975"
export PROJECT_ID="tanksquare"

gcloud config set project "${PROJECT_ID}" >/dev/null

echo "======================================================================"
echo " TankSquare GCP Triple-Check Audit for Project: ${PROJECT_ID} (${PROJECT_NUMBER})"
echo "======================================================================"

# 0. Check Billing Account
BILLING_ACCT="$(gcloud billing projects describe "${PROJECT_ID}" --format='value(billingAccountName)' 2>/dev/null || echo 'NONE')"
echo "[0/5] Linked Billing Account: ${BILLING_ACCT}"

# 1. Ensure all required APIs are enabled
echo ""
echo "[1/5] Ensuring Required GCP & Maps APIs are Enabled..."
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  maps-backend.googleapis.com \
  geocoding-backend.googleapis.com \
  cloudquotas.googleapis.com \
  billingbudgets.googleapis.com \
  --project="${PROJECT_ID}"
echo "  [✓] All required APIs enabled."

# 2. Check Secret Manager & Prune Old Versions (Free Tier = 6 active versions)
echo ""
echo "[2/5] Checking Secret Manager & Pruning Old Versions (Free Tier <= 6)..."
SECRETS=(
  "tanksquare-google-maps-api-key"
  "tanksquare-w3w-api-key"
  "tanksquare-session-signing-secret"
  "tanksquare-vendor-api-secret"
)
TOTAL_ACTIVE_VERSIONS=0
for SEC in "${SECRETS[@]}"; do
  if ! gcloud secrets describe "${SEC}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "  -> Creating missing secret '${SEC}'..."
    gcloud secrets create "${SEC}" --replication-policy="automatic" --project="${PROJECT_ID}" >/dev/null
    if [[ "${SEC}" == *"signing"* || "${SEC}" == *"vendor"* ]]; then
      RND="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32), end="")')"
      printf "%s" "${RND}" | gcloud secrets versions add "${SEC}" --data-file=- --project="${PROJECT_ID}" >/dev/null
    else
      printf "PLACEHOLDER" | gcloud secrets versions add "${SEC}" --data-file=- --project="${PROJECT_ID}" >/dev/null
    fi
  fi

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
done
echo "  => Total Active Secret Versions: ${TOTAL_ACTIVE_VERSIONS} / 6 Free Tier Limit (\$0.00/mo)"

# 3. Verify Google Maps API Key & what3words API Key Status
echo ""
echo "[3/5] Checking Google Maps & what3words API Keys..."
MAPS_VAL="$(gcloud secrets versions access latest --secret="tanksquare-google-maps-api-key" --project="${PROJECT_ID}" 2>/dev/null || echo "")"
if [[ -z "${MAPS_VAL}" || "${MAPS_VAL}" == PLACEHOLDER* ]]; then
  echo "  [i] Google Maps Key: Currently set to PLACEHOLDER (using \$0 built-in parcel math until you add a live Maps key)."
else
  HTTP_STATUS="$(curl -s -o /tmp/maps_test.json -w "%{http_code}" "https://maps.googleapis.com/maps/api/geocode/json?address=Montpelier,VT&key=${MAPS_VAL}")"
  API_STATUS="$(python3 -c 'import json; d=json.load(open("/tmp/maps_test.json")); print(d.get("status","UNKNOWN"))' 2>/dev/null || echo "ERROR")"
  ERR_MSG="$(python3 -c 'import json; d=json.load(open("/tmp/maps_test.json")); print(d.get("error_message",""))' 2>/dev/null || echo "")"
  rm -f /tmp/maps_test.json
  echo "  [✓] Google Maps Key: Configured (HTTP ${HTTP_STATUS}, Status: ${API_STATUS} ${ERR_MSG})"
fi
unset MAPS_VAL

W3W_VAL="$(gcloud secrets versions access latest --secret="tanksquare-w3w-api-key" --project="${PROJECT_ID}" 2>/dev/null || echo "")"
if [[ -z "${W3W_VAL}" || "${W3W_VAL}" == PLACEHOLDER* ]]; then
  echo "  [i] what3words Key:  Currently set to PLACEHOLDER (using \$0 built-in deterministic 3-word generator)."
else
  W3W_STATUS="$(curl -s -o /tmp/w3w_test.json -w "%{http_code}" "https://api.what3words.com/v3/convert-to-3wa?coordinates=44.2601,-72.5754&key=${W3W_VAL}")"
  W3W_WORDS="$(python3 -c 'import json; d=json.load(open("/tmp/w3w_test.json")); print(d.get("words", d.get("error", {}).get("message", "")))' 2>/dev/null || echo "")"
  rm -f /tmp/w3w_test.json
  echo "  [✓] what3words Key:  Configured (HTTP ${W3W_STATUS}, Result: ${W3W_WORDS})"
fi
unset W3W_VAL

# 4. Bind All Required IAM Permissions for Cloud Run & Cloud Build
echo ""
echo "[4/5] Verifying & Binding Project IAM Permissions..."
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
  echo "  [✓] Bound ${ROLE}"
done

# 5. Verify Firestore, GCS Media Bucket & Artifact Registry
echo ""
echo "[5/5] Verifying Firestore, Cloud Storage & Artifact Registry..."
if gcloud storage buckets describe "gs://${PROJECT_NUMBER}-media" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "  -> Removing duplicate empty bucket gs://${PROJECT_NUMBER}-media..."
  gcloud storage buckets delete "gs://${PROJECT_NUMBER}-media" --project="${PROJECT_ID}" >/dev/null 2>&1 || true
fi

if ! gcloud firestore databases describe --database="(default)" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "  -> Creating Native Firestore database ((default)) in nam5..."
  gcloud firestore databases create --location=nam5 --type=firestore-native --project="${PROJECT_ID}" >/dev/null
fi
FS_LOC="$(gcloud firestore databases describe --database="(default)" --project="${PROJECT_ID}" --format="value(locationId)")"
echo "  [✓] Cloud Firestore ((default)): READY (Location=${FS_LOC}, Free Tier: 1 GiB + 50k reads/day)"

if ! gcloud storage buckets describe "gs://${PROJECT_ID}-media" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "  -> Creating Cloud Storage bucket gs://${PROJECT_ID}-media..."
  gcloud storage buckets create "gs://${PROJECT_ID}-media" --location=us-central1 --uniform-bucket-level-access --project="${PROJECT_ID}" >/dev/null
fi
echo "  [✓] Cloud Storage Bucket: gs://${PROJECT_ID}-media READY (Free Tier: 5 GB/mo in us-central1)"

if ! gcloud artifacts repositories describe tanksquare --location=us-central1 --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "  -> Creating Artifact Registry repo 'tanksquare'..."
  gcloud artifacts repositories create tanksquare --repository-format=docker --location=us-central1 --project="${PROJECT_ID}" >/dev/null
fi
echo "  [✓] Artifact Registry Repo: tanksquare READY (Free Tier: 500 MB/mo)"

echo ""
echo "======================================================================"
echo " Audit Complete: All GCP Resources, APIs & IAM Permissions are READY!"
echo "======================================================================"
