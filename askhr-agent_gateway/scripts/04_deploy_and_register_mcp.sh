#!/usr/bin/env bash
# Deploy the three askHR MCP servers to Cloud Run and register them in Agent Registry.
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
: "${REGION:=us-central1}"
REPO="askhr"
SERVERS=(employee-directory benefits-payroll hr-actions)

gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com agentregistry.googleapis.com --project "$PROJECT_ID"

# Artifact Registry repo (idempotent)
gcloud artifacts repositories describe "$REPO" --location "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$REPO" --repository-format=docker \
    --location "$REGION" --project "$PROJECT_ID"

for SVC in "${SERVERS[@]}"; do
  IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${SVC}:latest"
  SA="askhr-${SVC}@${PROJECT_ID}.iam.gserviceaccount.com"

  # Per-service identity (least privilege)
  gcloud iam service-accounts describe "$SA" --project "$PROJECT_ID" >/dev/null 2>&1 || \
    gcloud iam service-accounts create "askhr-${SVC}" --project "$PROJECT_ID" \
      --display-name "askHR MCP: ${SVC}"

  echo "== Building & deploying ${SVC} =="
  gcloud builds submit "mcp-servers/${SVC}" --tag "$IMAGE" --project "$PROJECT_ID"

  gcloud run deploy "$SVC" \
    --image "$IMAGE" \
    --region "$REGION" --project "$PROJECT_ID" \
    --service-account "$SA" \
    --no-allow-unauthenticated \
    --ingress all   # switch to internal-and-cloud-load-balancing for the private variant

  URL=$(gcloud run services describe "$SVC" --region "$REGION" --project "$PROJECT_ID" --format 'value(status.url)')

  echo "== Registering ${SVC} in Agent Registry =="
  gcloud alpha agent-registry services create "$SVC" \
    --project "$PROJECT_ID" --location "$REGION" \
    --display-name "askHR ${SVC}" \
    --mcp-server-spec-type=tool-spec \
    --mcp-server-spec-content="mcp-servers/${SVC}/toolspec.json" \
    --interfaces="url=${URL}/mcp,protocolBinding=JSONRPC" \
    || echo "(already registered — skipping)"
done

echo
echo "Registered MCP servers:"
gcloud alpha agent-registry mcp-servers list --project "$PROJECT_ID" --location "$REGION"
