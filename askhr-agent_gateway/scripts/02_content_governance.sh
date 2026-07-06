#!/usr/bin/env bash
# STEP 02 — CONTENT GOVERNANCE (pure shell, no Terraform).
#
# Creates:
#   1. DLP inspect template  (find SSNs / routing / account numbers)
#   2. DLP de-identify template (replace with [REDACTED-BY-MODEL-ARMOR])
#   3. Model Armor template "askhr-guardrails" wiring both in via SDP
#      advanced config + prompt-injection/jailbreak + RAI filters
#   4. IAM for the Agent Gateway service agent to call Model Armor
#
# DLP templates have no gcloud surface, so they are created via the DLP REST
# API with curl. Model Armor uses native gcloud commands.
set -euo pipefail

export CLOUDSDK_CONTEXT_AWARE_USE_CLIENT_CERTIFICATE=false
export CLOUDSDK_CONTEXT_AWARE_USE_ECP_HTTP_PROXY=false

: "${PROJECT_ID:?set PROJECT_ID}"
export REGION="${REGION:-us-central1}"
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')

# The DLP API requires an explicit quota project when using user credentials.
# Set it on ADC (harmless if already set) AND send x-goog-user-project on
# every request so the script works regardless of local credential state.
gcloud auth application-default set-quota-project "$PROJECT_ID" >/dev/null 2>&1 || true

TOKEN=$(gcloud auth print-access-token)
DLP_PARENT="projects/${PROJECT_ID}/locations/${REGION}"

# ---------------------------------------------------------------------------
# 1. DLP INSPECT template — what counts as payroll PII
# ---------------------------------------------------------------------------
# curl -sS -X POST \
#   -H "Authorization: Bearer ${TOKEN}" \
#   -H "x-goog-user-project: ${PROJECT_ID}" \
#   -H "Content-Type: application/json" \
#   "https://dlp.googleapis.com/v2/${DLP_PARENT}/inspectTemplates" \
#   -d @- <<'EOF'
# {
#   "templateId": "askhr-payroll-pii-inspect",
#   "inspectTemplate": {
#     "displayName": "askHR payroll PII inspect",
#     "inspectConfig": {
#       "infoTypes": [
#         { "name": "US_SOCIAL_SECURITY_NUMBER" },
#         { "name": "US_BANK_ROUTING_MICR" },
#         { "name": "FINANCIAL_ACCOUNT_NUMBER" }
#       ],
#       "minLikelihood": "POSSIBLE"
#     }
#   }
# }
# EOF
# echo

# ---------------------------------------------------------------------------
# 2. DLP DE-IDENTIFY template — how to redact it in-flight
# ---------------------------------------------------------------------------
# curl -sS -X POST \
#   -H "Authorization: Bearer ${TOKEN}" \
#   -H "x-goog-user-project: ${PROJECT_ID}" \
#   -H "Content-Type: application/json" \
#   "https://dlp.googleapis.com/v2/${DLP_PARENT}/deidentifyTemplates" \
#   -d @- <<'EOF'
# {
#   "templateId": "askhr-payroll-pii-deid",
#   "deidentifyTemplate": {
#     "displayName": "askHR payroll PII de-identify",
#     "deidentifyConfig": {
#       "infoTypeTransformations": {
#         "transformations": [
#           {
#             "primitiveTransformation": {
#               "replaceConfig": {
#                 "newValue": { "stringValue": "[REDACTED-BY-MODEL-ARMOR]" }
#               }
#             }
#           }
#         ]
#       }
#     }
#   }
# }
# EOF
# echo

INSPECT_TPL="${DLP_PARENT}/inspectTemplates/askhr-payroll-pii-inspect"
DEID_TPL="${DLP_PARENT}/deidentifyTemplates/askhr-payroll-pii-deid"

# ---------------------------------------------------------------------------
# 3. Model Armor template (same region as the gateway — cross-region calls
#    to Model Armor are not supported)
# ---------------------------------------------------------------------------
gcloud model-armor templates create askhr-guardrails \
  --project "$PROJECT_ID" \
  --location "$REGION" \
  --pi-and-jailbreak-filter-settings-enforcement=enabled \
  --pi-and-jailbreak-filter-settings-confidence-level=medium-and-above \
  --rai-settings-filters='[{"filterType":"HARASSMENT","confidenceLevel":"MEDIUM_AND_ABOVE"},{"filterType":"HATE_SPEECH","confidenceLevel":"MEDIUM_AND_ABOVE"}]' \
  --advanced-config-inspect-template="$INSPECT_TPL" \
  --advanced-config-deidentify-template="$DEID_TPL"

gcloud model-armor templates describe askhr-guardrails \
  --project "$PROJECT_ID" --location "$REGION"

# ---------------------------------------------------------------------------
# 4. Let the Agent Gateway's service agent call Model Armor.
#    Gateway service agent: service-<PROJECT_NUMBER>@gcp-sa-dep.iam.gserviceaccount.com
# ---------------------------------------------------------------------------
GW_SA="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-dep.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="$GW_SA" --role=roles/modelarmor.calloutUser --condition=None
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="$GW_SA" --role=roles/serviceusage.serviceUsageConsumer --condition=None
# modelarmor.user must be granted in the project that HOSTS the templates
# (same project here):
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="$GW_SA" --role=roles/modelarmor.user --condition=None

echo
echo "Content governance ready:"
echo "  Model Armor template : projects/${PROJECT_ID}/locations/${REGION}/templates/askhr-guardrails"
echo "  DLP inspect          : ${INSPECT_TPL}"
echo "  DLP de-identify      : ${DEID_TPL}"
echo "Next: scripts/03_agent_gateway.sh attaches this template to the gateway"
echo "via a CONTENT_AUTHZ authorization extension + policy."