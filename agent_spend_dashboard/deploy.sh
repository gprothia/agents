#!/usr/bin/env bash
# deploy.sh — Deploy the Agent Engine Spend Dashboard to Cloud Run (source deploy)
# Usage:  export GCP_PROJECT_ID=my-project && bash deploy.sh
# No Docker required — Cloud Build compiles the source on GCP.

set -euo pipefail

# ── EDIT THESE ─────────────────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-your-project-id}"
REGION="us-central1"
SERVICE_NAME="agent-spend-dashboard"
SA_NAME="${SERVICE_NAME}-sa"
# ───────────────────────────────────────────────────────────────────────────────

SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "============================================================"
echo " ADK Agent Engine Spend Dashboard — Cloud Run Source Deploy"
echo " Project : ${PROJECT_ID}"
echo " Region  : ${REGION}"
echo "============================================================"

# ── 1. Enable required APIs ────────────────────────────────────────────────────
echo ""
echo "▶  Enabling GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com \
  aiplatform.googleapis.com \
  artifactregistry.googleapis.com \
  --project="${PROJECT_ID}"

# ── 2. Create service account (idempotent) ─────────────────────────────────────
echo ""
echo "▶  Service account: ${SA_EMAIL}"

if gcloud iam service-accounts describe "${SA_EMAIL}" \
     --project="${PROJECT_ID}" &>/dev/null; then
  echo "   Already exists — skipping creation."
else
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="Agent Spend Dashboard SA" \
    --project="${PROJECT_ID}"
  echo "   Waiting 15 s for IAM propagation..."
  sleep 15
fi

# ── 3. Grant IAM roles to the dashboard service account ───────────────────────
echo ""
echo "▶  Granting IAM roles..."
for ROLE in \
  "roles/monitoring.viewer" \
  "roles/logging.viewer" \
  "roles/aiplatform.viewer" \
  "roles/bigquery.user" \
  "roles/bigquery.dataViewer"; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${ROLE}" \
    --condition=None \
    --quiet
  echo "   Granted: ${ROLE}"
done

# ── 4. Allow Cloud Build to assign the SA to the Cloud Run service ─────────────
echo ""
echo "▶  Granting Cloud Build permission to use the service account..."
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" \
  --format="value(projectNumber)")
CLOUDBUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
  --member="serviceAccount:${CLOUDBUILD_SA}" \
  --role="roles/iam.serviceAccountUser" \
  --project="${PROJECT_ID}" \
  --quiet
echo "   Done."

# ── 5. Deploy from source ──────────────────────────────────────────────────────
echo ""
echo "▶  Deploying from source (Cloud Build will build the image)..."
echo "   First run takes ~3-5 min. Subsequent deploys are faster."
echo ""

# Capture output so we can show the build log URL on failure
if ! gcloud run deploy "${SERVICE_NAME}" \
      --source=. \
      --platform=managed \
      --region="${REGION}" \
      --allow-unauthenticated \
      --service-account="${SA_EMAIL}" \
      --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID}" \
      --memory=1Gi \
      --cpu=1 \
      --min-instances=0 \
      --max-instances=3 \
      --timeout=300 \
      --project="${PROJECT_ID}"; then

  echo ""
  echo "❌  Deploy failed. Fetching the most recent Cloud Build log URL..."
  BUILD_ID=$(gcloud builds list \
    --project="${PROJECT_ID}" \
    --limit=1 \
    --format="value(id)")
  echo ""
  echo "   Build ID : ${BUILD_ID}"
  echo "   Full logs: https://console.cloud.google.com/cloud-build/builds/${BUILD_ID}?project=${PROJECT_ID}"
  echo ""
  echo "   Or stream logs now with:"
  echo "   gcloud builds log ${BUILD_ID} --project=${PROJECT_ID}"
  exit 1
fi

# ── 6. Print the service URL ───────────────────────────────────────────────────
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --format="value(status.url)")

echo ""
echo "============================================================"
echo " ✅  Deployment complete!"
echo ""
echo " 🔗  Dashboard URL:"
echo "     ${SERVICE_URL}"
echo ""
echo " No login required — the service is publicly accessible."
echo "============================================================"