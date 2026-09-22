#!/usr/bin/env bash
set -e

PROJECT_ID="bold-kit-384717"
PROJECT_NUMBER="851970768145"
REGION="us-central1"
AGENT_ENGINE_ID="9119506121181102080"
API_ID="agent-gateway-api"
CONFIG_ID="agent-gateway-config-v1"
GATEWAY_ID="agent-gaeway"
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "=== 1. Deploying AskHR Agent to Vertex AI Agent Engine (${AGENT_ENGINE_ID}) ==="
env -u GOOGLE_APPLICATION_CREDENTIALS ../.venv/bin/python3 deploy.py --agent-id "${AGENT_ENGINE_ID}" --display-name "NewAskHR"

echo "=== 2. Creating API Gateway API resource (${API_ID}) ==="
env -u GOOGLE_APPLICATION_CREDENTIALS gcloud api-gateway apis create "${API_ID}" \
  --project="${PROJECT_ID}" || echo "API ${API_ID} already exists."

echo "=== 3. Creating API Config (${CONFIG_ID}) from agent-gateway-openapi.yaml ==="
env -u GOOGLE_APPLICATION_CREDENTIALS gcloud api-gateway api-configs create "${CONFIG_ID}" \
  --api="${API_ID}" \
  --openapi-spec="agent-gateway-openapi.yaml" \
  --backend-auth-service-account="${SERVICE_ACCOUNT}" \
  --project="${PROJECT_ID}" || echo "API Config ${CONFIG_ID} already exists."

echo "=== 4. Deploying API Gateway (${GATEWAY_ID}) in ${REGION} ==="
env -u GOOGLE_APPLICATION_CREDENTIALS gcloud api-gateway gateways create "${GATEWAY_ID}" \
  --api="${API_ID}" \
  --api-config="${CONFIG_ID}" \
  --location="${REGION}" \
  --project="${PROJECT_ID}" || echo "Gateway ${GATEWAY_ID} already exists."

HOSTNAME=$(env -u GOOGLE_APPLICATION_CREDENTIALS gcloud api-gateway gateways describe "${GATEWAY_ID}" \
  --location="${REGION}" \
  --project="${PROJECT_ID}" \
  --format="value(defaultHostname)")

echo "=== 5. Registering Agent and Gateway in Agent Registry (${REGION}) ==="
TOKEN=$(gcloud auth print-access-token)
curl -s -X PATCH \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -H "x-goog-user-project: ${PROJECT_ID}" \
  -d "{
    \"displayName\": \"NewAskHR\",
    \"description\": \"AskHR Agent deployed on Agent Engine and exposed via agent-gaeway (${HOSTNAME})\",
    \"protocols\": [
      {
        \"type\": \"CUSTOM\",
        \"interfaces\": [
          {
            \"url\": \"https://${HOSTNAME}/v1/projects/bold-kit-384717/locations/us-central1/reasoningEngines/${AGENT_ENGINE_ID}:query\",
            \"protocolBinding\": \"HTTP_JSON\"
          },
          {
            \"url\": \"https://${HOSTNAME}/v1/projects/bold-kit-384717/locations/us-central1/reasoningEngines/${AGENT_ENGINE_ID}:streamQuery\",
            \"protocolBinding\": \"HTTP_JSON\"
          }
        ]
      }
    ]
  }" \
  "https://agentregistry.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/agents/agentregistry-00000000-0000-0000-4aee-a389ab707e21?updateMask=displayName,description,protocols"

echo ""
echo "=========================================================="
echo "AGENT & AGENT GATEWAY DEPLOYMENT COMPLETE"
echo "GATEWAY NAME: ${GATEWAY_ID} (${REGION})"
echo "GATEWAY URL:  https://${HOSTNAME}"
echo "REGISTRY:     //agentregistry.googleapis.com/projects/${PROJECT_ID}/locations/${REGION}"
echo "=========================================================="
