#!/usr/bin/env bash
# ============================================================================
# TankSquare — Provision GitHub Actions Deployer Service Account in GCP
# (`scripts/setup_github_actions_sa.sh`)
# ============================================================================
# Creates `github-actions@tanksquare.iam.gserviceaccount.com` and grants the
# exact IAM roles needed for `.github/workflows/deploy-gcp.yml` to deploy
# `dev` -> `tanksquare-api-dev` and `main` -> `tanksquare-api-prod`.
# ============================================================================

set -euo pipefail

export PATH="/Users/madushan/google-cloud-sdk/bin:${PATH}"
export PROJECT_ID="tanksquare"
export SA_NAME="github-actions"
export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project "${PROJECT_ID}" >/dev/null

echo "=== Provisioning GitHub Actions Deployer Service Account (${SA_EMAIL}) ==="

if ! gcloud iam service-accounts describe "${SA_EMAIL}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="GitHub Actions Cloud Run Deployer" \
    --project="${PROJECT_ID}"
  echo "  [✓] Created service account: ${SA_EMAIL}"
else
  echo "  [✓] Service account already exists: ${SA_EMAIL}"
fi

ROLES=(
  "roles/run.admin"
  "roles/iam.serviceAccountUser"
  "roles/cloudbuild.builds.editor"
  "roles/storage.admin"
  "roles/artifactregistry.admin"
  "roles/serviceusage.serviceUsageConsumer"
  "roles/secretmanager.secretAccessor"
  "roles/viewer"
)

for ROLE in "${ROLES[@]}"; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${ROLE}" \
    --condition=None >/dev/null
  echo "  [✓] Bound ${ROLE}"
done

echo "=== GitHub Actions Service Account Ready ==="
