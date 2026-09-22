#!/usr/bin/env bash
set -e

PROJECT_ID="sunlit-segment-396117"
PROJECT_NUMBER="45360814210"
REGION="us-central1"
API_ID="agent-gateway-api"
CONFIG_ID="agent-gateway-config-$(date +%Y%m%d%H%M%S)"
GATEWAY_ID="agent-gateway"
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "=== 1. Deploying AskHR Agent to Vertex AI Agent Engine in ${PROJECT_ID} ==="
cd "$(dirname "$0")"

DEPLOY_OUTPUT=$(env -u GOOGLE_APPLICATION_CREDENTIALS ../.venv/bin/python3 deploy.py --display-name "NewAskHR" 2>&1 | tee /dev/tty)

AGENT_ENGINE_ID=$(echo "${DEPLOY_OUTPUT}" | grep -o 'reasoningEngines/[0-9]*' | tail -n1 | cut -d/ -f2)

if [ -z "${AGENT_ENGINE_ID}" ]; then
  echo "ERROR: Failed to extract AGENT_ENGINE_ID from deploy output."
  exit 1
fi

echo ""
echo "=== Successfully Deployed Agent Engine ID: ${AGENT_ENGINE_ID} ==="

echo "=== Generating agent-gateway-openapi.yaml for ${AGENT_ENGINE_ID} ==="
cat <<EOF > agent-gateway-openapi.yaml
swagger: "2.0"
info:
  title: AskHR Agent Gateway
  description: API Gateway specification for AskHR Vertex AI Agent Engine
  version: "1.0.0"
schemes:
  - https
produces:
  - application/json
paths:
  /v1/projects/${PROJECT_ID}/locations/${REGION}/reasoningEngines/${AGENT_ENGINE_ID}:query:
    post:
      summary: Query the AskHR Agent Engine
      operationId: queryAgentEngine
      x-google-backend:
        address: https://${REGION}-aiplatform.googleapis.com/v1/projects/${PROJECT_NUMBER}/locations/${REGION}/reasoningEngines/${AGENT_ENGINE_ID}:query
      parameters:
        - in: body
          name: body
          required: true
          schema:
            type: object
      responses:
        "200":
          description: Successful response
  /v1/projects/${PROJECT_ID}/locations/${REGION}/reasoningEngines/${AGENT_ENGINE_ID}:streamQuery:
    post:
      summary: Stream query responses from the AskHR Agent Engine
      operationId: streamQueryAgentEngine
      x-google-backend:
        address: https://${REGION}-aiplatform.googleapis.com/v1/projects/${PROJECT_NUMBER}/locations/${REGION}/reasoningEngines/${AGENT_ENGINE_ID}:streamQuery
      parameters:
        - in: body
          name: body
          required: true
          schema:
            type: object
      responses:
        "200":
          description: Successful stream response
EOF

echo "=== 2. Creating API Gateway API resource (${API_ID}) ==="
env -u GOOGLE_APPLICATION_CREDENTIALS gcloud api-gateway apis create "${API_ID}" \
  --project="${PROJECT_ID}" --quiet || echo "API ${API_ID} already exists."

echo "=== 3. Creating API Config (${CONFIG_ID}) from agent-gateway-openapi.yaml ==="
env -u GOOGLE_APPLICATION_CREDENTIALS gcloud api-gateway api-configs create "${CONFIG_ID}" \
  --api="${API_ID}" \
  --openapi-spec="agent-gateway-openapi.yaml" \
  --backend-auth-service-account="${SERVICE_ACCOUNT}" \
  --project="${PROJECT_ID}" --quiet

echo "=== 4. Deploying/Updating API Gateway (${GATEWAY_ID}) in ${REGION} ==="
if env -u GOOGLE_APPLICATION_CREDENTIALS gcloud api-gateway gateways describe "${GATEWAY_ID}" --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "Gateway ${GATEWAY_ID} already exists. Updating to config ${CONFIG_ID}..."
  env -u GOOGLE_APPLICATION_CREDENTIALS gcloud api-gateway gateways update "${GATEWAY_ID}" \
    --api="${API_ID}" \
    --api-config="${CONFIG_ID}" \
    --location="${REGION}" \
    --project="${PROJECT_ID}" --quiet
else
  echo "Creating new Gateway ${GATEWAY_ID} with config ${CONFIG_ID}..."
  env -u GOOGLE_APPLICATION_CREDENTIALS gcloud api-gateway gateways create "${GATEWAY_ID}" \
    --api="${API_ID}" \
    --api-config="${CONFIG_ID}" \
    --location="${REGION}" \
    --project="${PROJECT_ID}" --quiet
fi

HOSTNAME=$(env -u GOOGLE_APPLICATION_CREDENTIALS gcloud api-gateway gateways describe "${GATEWAY_ID}" \
  --location="${REGION}" \
  --project="${PROJECT_ID}" \
  --format="value(defaultHostname)")

echo "=== 5. Registering Agent and Gateway in Agent Registry (${REGION}) ==="
TOKEN=$(gcloud auth print-access-token)

EXISTING_AGENT=$(curl -s -H "Authorization: Bearer ${TOKEN}" \
  -H "x-goog-user-project: ${PROJECT_ID}" \
  "https://agentregistry.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/agents" | grep -o 'agentregistry-[0-9a-f-]*' | grep -v 'agentregistry.googleapis.com' | head -1)

if [ -z "${EXISTING_AGENT}" ]; then
  echo "Registering new agent entry in Agent Registry..."
  curl -s -f -X POST \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -H "x-goog-user-project: ${PROJECT_ID}" \
    -d "{
      \"displayName\": \"NewAskHR\",
      \"description\": \"AskHR Agent deployed on Agent Engine and exposed via ${GATEWAY_ID} (${HOSTNAME})\",
      \"protocols\": [
        {
          \"type\": \"CUSTOM\",
          \"interfaces\": [
            {
              \"url\": \"https://${HOSTNAME}/v1/projects/${PROJECT_ID}/locations/${REGION}/reasoningEngines/${AGENT_ENGINE_ID}:query\",
              \"protocolBinding\": \"HTTP_JSON\"
            },
            {
              \"url\": \"https://${HOSTNAME}/v1/projects/${PROJECT_ID}/locations/${REGION}/reasoningEngines/${AGENT_ENGINE_ID}:streamQuery\",
              \"protocolBinding\": \"HTTP_JSON\"
            }
          ]
        }
      ]
    }" \
    "https://agentregistry.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/agents" || echo "Note: Registry POST returned non-zero (non-fatal)."
else
  echo "Updating existing agent entry ${EXISTING_AGENT} in Agent Registry..."
  curl -s -f -X PATCH \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -H "x-goog-user-project: ${PROJECT_ID}" \
    -d "{
      \"displayName\": \"NewAskHR\",
      \"description\": \"AskHR Agent deployed on Agent Engine and exposed via ${GATEWAY_ID} (${HOSTNAME})\",
      \"protocols\": [
        {
          \"type\": \"CUSTOM\",
          \"interfaces\": [
            {
              \"url\": \"https://${HOSTNAME}/v1/projects/${PROJECT_ID}/locations/${REGION}/reasoningEngines/${AGENT_ENGINE_ID}:query\",
              \"protocolBinding\": \"HTTP_JSON\"
            },
            {
              \"url\": \"https://${HOSTNAME}/v1/projects/${PROJECT_ID}/locations/${REGION}/reasoningEngines/${AGENT_ENGINE_ID}:streamQuery\",
              \"protocolBinding\": \"HTTP_JSON\"
            }
          ]
        }
      ]
    }" \
    "https://agentregistry.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/agents/${EXISTING_AGENT}?updateMask=displayName,description,protocols" || echo "Note: Registry PATCH returned non-zero (non-fatal)."
fi

echo ""
echo "=========================================================="
echo "AGENT & AGENT GATEWAY DEPLOYMENT COMPLETE"
echo "PROJECT:      ${PROJECT_ID} (${PROJECT_NUMBER})"
echo "AGENT ENGINE: ${AGENT_ENGINE_ID}"
echo "GATEWAY NAME: ${GATEWAY_ID} (${REGION})"
echo "GATEWAY URL:  https://${HOSTNAME}"
echo "REGISTRY:     //agentregistry.googleapis.com/projects/${PROJECT_ID}/locations/${REGION}"
echo "=========================================================="
