#!/usr/bin/env bash
# STEP 05 — Deploy the askHR ADK agent to Agent Runtime with Agent Identity,
# bound to the egress Agent Gateway from step 03.
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
export REGION="${REGION:-us-central1}"
GATEWAY_RES="projects/${PROJECT_ID}/locations/${REGION}/agentGateways/askhr-agent-gateway"

# --- Vertex AI service agents need to read/use the network attachment ---
# Deploying with psc_interface_config makes Google's service agents (not you)
# call compute.networkAttachments.get on your attachment. Grant them access.
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
gcloud beta services identity create --service=aiplatform.googleapis.com \
  --project "$PROJECT_ID" >/dev/null 2>&1 || true
for SA_SUFFIX in gcp-sa-aiplatform gcp-sa-aiplatform-re; do
  SA_MEMBER="serviceAccount:service-${PROJECT_NUMBER}@${SA_SUFFIX}.iam.gserviceaccount.com"
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member "$SA_MEMBER" --role roles/compute.networkViewer --condition=None >/dev/null
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member "$SA_MEMBER" --role roles/compute.networkUser --condition=None >/dev/null
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member "$SA_MEMBER" --role roles/compute.networkAdmin --condition=None >/dev/null
done
echo "Granted network viewer/user to Vertex AI service agents."

# PSC-Interface network attachment from step 01 — plugs the agent's egress
# into your VPC (note: attachments use /regions/, not /locations/)
NETATTACH_RES="projects/${PROJECT_ID}/regions/${REGION}/networkAttachments/askhr-psc-attachment"

# Runtime SA that invokes the Cloud Run MCP services (created here manually)
INVOKER_SA_NAME="askhr-mcp-invoker"
INVOKER_SA="${INVOKER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts describe "$INVOKER_SA" --project "$PROJECT_ID" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "$INVOKER_SA_NAME" \
    --project "$PROJECT_ID" --display-name "askHR MCP invoker"

# Allow it to invoke the three Cloud Run MCP services
for SVC in employee-directory benefits-payroll hr-actions; do
  gcloud run services add-iam-policy-binding "$SVC" \
    --project "$PROJECT_ID" --region "$REGION" \
    --member "serviceAccount:${INVOKER_SA}" \
    --role roles/run.invoker
done

cd "$(dirname "$0")/../agent"
uv sync
uv run python deploy_agent.py \
  --project "$PROJECT_ID" --region "$REGION" \
  --agent-gateway "$GATEWAY_RES" \
  --network-attachment "$NETATTACH_RES" \
  --mcp-invoker-sa "$INVOKER_SA"

echo
echo "Copy the numeric Agent ID printed above, then:"
echo "  export AGENT_ID=<id>"
echo "  bash scripts/06_grant_governance_policies.sh"