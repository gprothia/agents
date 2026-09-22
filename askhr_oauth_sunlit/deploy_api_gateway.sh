#!/usr/bin/env bash
set -e

PROJECT_ID="sunlit-segment-396117"
PROJECT_NUMBER="45360814210"
REGION="us-central1"
API_ID="employee-api"
CONFIG_ID="employee-api-config-v1"
GATEWAY_ID="employee-gateway"
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "=== 1. Enabling API Gateway services in project ${PROJECT_ID} ==="
env -u GOOGLE_APPLICATION_CREDENTIALS gcloud services enable \
  apigateway.googleapis.com \
  servicemanagement.googleapis.com \
  servicecontrol.googleapis.com \
  --project="${PROJECT_ID}"

echo "=== 2. Granting Cloud Run Invoker role to ${SERVICE_ACCOUNT} ==="
env -u GOOGLE_APPLICATION_CREDENTIALS gcloud run services add-iam-policy-binding employee-api \
  --region="${REGION}" \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/run.invoker" \
  --project="${PROJECT_ID}" || true

echo "=== 3. Creating API Gateway API resource (${API_ID}) ==="
env -u GOOGLE_APPLICATION_CREDENTIALS gcloud api-gateway apis create "${API_ID}" \
  --project="${PROJECT_ID}" || echo "API ${API_ID} already exists."

echo "=== 4. Creating API Config (${CONFIG_ID}) from openapi-spec.yaml ==="
env -u GOOGLE_APPLICATION_CREDENTIALS gcloud api-gateway api-configs create "${CONFIG_ID}" \
  --api="${API_ID}" \
  --openapi-spec="openapi-spec.yaml" \
  --backend-auth-service-account="${SERVICE_ACCOUNT}" \
  --project="${PROJECT_ID}" || echo "API Config ${CONFIG_ID} already exists."

echo "=== 5. Deploying API Gateway (${GATEWAY_ID}) in ${REGION} ==="
env -u GOOGLE_APPLICATION_CREDENTIALS gcloud api-gateway gateways create "${GATEWAY_ID}" \
  --api="${API_ID}" \
  --api-config="${CONFIG_ID}" \
  --location="${REGION}" \
  --project="${PROJECT_ID}" || echo "Gateway ${GATEWAY_ID} already exists."

echo "=== 6. Fetching API Gateway Hostname ==="
HOSTNAME=$(env -u GOOGLE_APPLICATION_CREDENTIALS gcloud api-gateway gateways describe "${GATEWAY_ID}" \
  --location="${REGION}" \
  --project="${PROJECT_ID}" \
  --format="value(defaultHostname)")

echo "=========================================================="
echo "API GATEWAY DEPLOYED SUCCESSFULLY"
echo "GATEWAY URL: https://${HOSTNAME}"
echo "=========================================================="
