#!/usr/bin/env bash
# STEP 03 — Create the Agent Gateway (Agent-to-Anywhere / egress mode) and
# delegate authorization: IAP for identity (REQUEST_AUTHZ) and Model Armor
# for content (CONTENT_AUTHZ). Everything declaratively via gcloud YAML
# imports — no Terraform.
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
export REGION="${REGION:-us-central1}"
GATEWAY="askhr-agent-gateway"
MA_TEMPLATE="projects/${PROJECT_ID}/locations/${REGION}/templates/askhr-guardrails"
WORKDIR="$(mktemp -d)"

# ---------------------------------------------------------------------------
# 1. The Agent Gateway resource (egress mode, bound to the regional
#    Agent Registry — anything NOT in this registry is blocked by default)
# ---------------------------------------------------------------------------
cat > "${WORKDIR}/agent-gateway-egress.yaml" <<EOF
name: ${GATEWAY}
protocols:
- MCP
googleManaged:
  governedAccessPath: AGENT_TO_ANYWHERE
  registries:
  - //agentregistry.googleapis.com/projects/${PROJECT_ID}/locations/${REGION}
EOF

gcloud network-services agent-gateways import "$GATEWAY" \
  --source="${WORKDIR}/agent-gateway-egress.yaml" \
  --location="$REGION" --project "$PROJECT_ID"

# ---------------------------------------------------------------------------
# 2. REQUEST_AUTHZ — delegate identity/per-tool authorization to IAP.
#    IAP evaluates roles/iap.egressor + your CEL conditions
#    (mcp.toolName, mcp.tool.isReadOnly) per request.
# ---------------------------------------------------------------------------
cat > "${WORKDIR}/iap-request-authz-ext.yaml" <<EOF
name: askhr-iap-request-authz-ext
authority: iap.googleapis.com
service: https://iap.googleapis.com
failOpen: false
timeout: 1s
wireFormat: EXT_PROC_GRPC
EOF

gcloud beta network-security authz-extensions import askhr-iap-request-authz-ext \
  --source="${WORKDIR}/iap-request-authz-ext.yaml" \
  --location="$REGION" --project "$PROJECT_ID"

cat > "${WORKDIR}/iap-request-authz-policy.yaml" <<EOF
name: askhr-iap-request-authz-policy
target:
  resources:
  - "projects/${PROJECT_ID}/locations/${REGION}/gateways/${GATEWAY}"
policyProfile: REQUEST_AUTHZ
action: CUSTOM
customProvider:
  authzExtension:
    resources:
    - "projects/${PROJECT_ID}/locations/${REGION}/authzExtensions/askhr-iap-request-authz-ext"
EOF

gcloud beta network-security authz-policies import askhr-iap-request-authz-policy \
  --source="${WORKDIR}/iap-request-authz-policy.yaml" \
  --location="$REGION" --project "$PROJECT_ID"

# ---------------------------------------------------------------------------
# 3. CONTENT_AUTHZ — delegate content inspection to Model Armor
#    (prompt-injection screen + SSN/bank redaction from step 02).
#    Scoped via cel rules to MCP traffic only, per Google's recommendation.
# ---------------------------------------------------------------------------
cat > "${WORKDIR}/ma-content-authz-ext.yaml" <<EOF
name: askhr-ma-content-authz-ext
authority: modelarmor.${REGION}.rep.googleapis.com
service: https://modelarmor.${REGION}.rep.googleapis.com
failOpen: false
timeout: 10s
wireFormat: EXT_PROC_GRPC
metadata:
  model_armor_settings: '[{"model_armor_template": "${MA_TEMPLATE}", "user_prompt_inspection_setting": "INSPECT_AND_BLOCK", "model_response_inspection_setting": "INSPECT_AND_DEIDENTIFY"}]'
EOF

gcloud beta network-security authz-extensions import askhr-ma-content-authz-ext \
  --source="${WORKDIR}/ma-content-authz-ext.yaml" \
  --location="$REGION" --project "$PROJECT_ID"

cat > "${WORKDIR}/ma-content-authz-policy.yaml" <<EOF
name: askhr-ma-content-authz-policy
target:
  resources:
  - "projects/${PROJECT_ID}/locations/${REGION}/gateways/${GATEWAY}"
policyProfile: CONTENT_AUTHZ
action: CUSTOM
customProvider:
  authzExtension:
    resources:
    - "projects/${PROJECT_ID}/locations/${REGION}/authzExtensions/askhr-ma-content-authz-ext"
EOF

gcloud beta network-security authz-policies import askhr-ma-content-authz-policy \
  --source="${WORKDIR}/ma-content-authz-policy.yaml" \
  --location="$REGION" --project "$PROJECT_ID"

# ---------------------------------------------------------------------------
# 4. Verify
# ---------------------------------------------------------------------------
echo
gcloud network-services agent-gateways describe "$GATEWAY" \
  --location="$REGION" --project "$PROJECT_ID"
gcloud beta network-security authz-policies list \
  --location="$REGION" --project "$PROJECT_ID"

echo
echo "Gateway resource (needed for agent deploy in step 05):"
echo "  projects/${PROJECT_ID}/locations/${REGION}/agentGateways/${GATEWAY}"
echo
echo "NOTE (preview): exact extension YAML fields (authority/service/metadata)"
echo "can differ per allowlisted preview build — if import rejects a field,"
echo "diff against the 'Delegate authorization with Service Extensions' doc:"
echo "https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/delegate-authorization"
