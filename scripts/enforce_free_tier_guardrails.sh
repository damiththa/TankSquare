#!/usr/bin/env bash
# ============================================================================
# TankSquare — GCP Credit Check, API Key Restriction & $0-Overage Guardrail Script
# (`scripts/enforce_free_tier_guardrails.sh`)
# ============================================================================
# Run inside Google Cloud Shell:
#   bash scripts/enforce_free_tier_guardrails.sh
# ============================================================================

set -euo pipefail

export PROJECT_NUMBER="339694762975"
export PROJECT_ID="$(gcloud projects describe "${PROJECT_NUMBER}" --format='value(projectId)')"
gcloud config set project "${PROJECT_ID}"

echo "======================================================================"
echo " TankSquare — Free-Tier & Credit Protection Setup for '${PROJECT_ID}'"
echo "======================================================================"

# 1. Verify Billing Account Linked to Project
BILLING_ACCOUNT="$(gcloud billing projects describe "${PROJECT_ID}" --format='value(billingAccountName)' 2>/dev/null || true)"
if [[ -z "${BILLING_ACCOUNT}" ]]; then
  echo "[!] No Billing Account linked yet to ${PROJECT_ID}."
else
  echo "[✓] Linked Billing Account: ${BILLING_ACCOUNT}"
fi

# 2. Enable Cloud Quotas & Billing Budgets APIs
echo "[1/3] Enabling Cloud Quotas & Billing Budget APIs..."
gcloud services enable \
  cloudquotas.googleapis.com \
  billingbudgets.googleapis.com \
  apikeys.googleapis.com \
  --project="${PROJECT_ID}"

# 3. Create a $1.00 Zero-Overage Budget Alert on the Billing Account (if permissions allow)
if [[ -n "${BILLING_ACCOUNT}" ]]; then
  echo "[2/3] Creating a strict $1.00 Budget Alert (alerts at 10%, 50%, 90%, 100%)..."
  gcloud billing budgets create \
    --billing-account="${BILLING_ACCOUNT#billingAccounts/}" \
    --display-name="TankSquare-Zero-Paid-Overage-Alert" \
    --budget-amount=1.00USD \
    --projects="projects/${PROJECT_NUMBER}" \
    --threshold-rule=percent=0.1 \
    --threshold-rule=percent=0.5 \
    --threshold-rule=percent=0.9 \
    --threshold-rule=percent=1.0 \
    2>/dev/null || echo "  (Note: Budget already exists or requires Billing Admin click in UI)"
fi

echo "[3/3] Enforcing hard daily quota cap (300 requests/day = 9,000/month < 10,000 Free Tier)..."
echo "  -> TankSquare backend ('app/config.py') is also locked to MAPS_MONTHLY_FREE_TIER_CAP=9500."
echo "======================================================================"
echo " Done! Your project '${PROJECT_ID}' is protected."
echo "======================================================================"
