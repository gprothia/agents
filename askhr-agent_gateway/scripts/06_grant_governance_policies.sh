#!/usr/bin/env bash
# Grant the askHR agent identity governed egress via Agent Gateway (IAP iap.egressor).
#
# Policy intent:
#   employee-directory  -> ALLOW (all tools; all are read-only anyway)
#   benefits-payroll    -> ALLOW (read-only; PII handled by Model Armor)
#   hr-actions          -> ALLOW ONLY READ-ONLY TOOLS via CEL condition.
#                          Since every tool there is a WRITE, the effect is a
#                          demonstrable DENY: submit_pto_request /
#                          update_bank_details / file_hr_case all 403 at the
#                          gateway while the other two servers keep working.
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
: "${REGION:=us-central1}"
: "${AGENT_ID:?set AGENT_ID (numeric ID printed by deploy_agent.py)}"
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
ORG_ID=$(gcloud projects describe "$PROJECT_ID" --format="value(parent.id)")

# Agent Identity principal for an Agent Runtime-deployed agent.
AGENT_PRINCIPAL="principal://agents.global.org-${ORG_ID}.system.id.goog/resources/aiplatform/projects/${PROJECT_NUMBER}/locations/${REGION}/reasoningEngines/${AGENT_ID}"

allow_full() {
  local SVC="$1"
  gcloud beta iap web add-iam-policy-binding \
    --project "$PROJECT_ID" --region "$REGION" \
    --resource-type=cloud-run --service "$SVC" \
    --member "$AGENT_PRINCIPAL" \
    --role roles/iap.egressor
  echo "ALLOW  ${SVC}  (all tools)"
}

allow_readonly_only() {
  local SVC="$1"
  gcloud beta iap web add-iam-policy-binding \
    --project "$PROJECT_ID" --region "$REGION" \
    --resource-type=cloud-run --service "$SVC" \
    --member "$AGENT_PRINCIPAL" \
    --role roles/iap.egressor \
    --condition-from-file=<(cat <<'EOF'
{
  "title": "ReadOnlyToolsOnly",
  "description": "Deny write MCP tools through Agent Gateway",
  "expression": "api.getAttribute('iap.googleapis.com/mcp.tool.isReadOnly', false) == true"
}
EOF
)
  echo "ALLOW  ${SVC}  (read-only tools only)"
}

allow_full          employee-directory
allow_full          benefits-payroll
allow_readonly_only hr-actions

cat <<'EON'

Done. Other useful CEL attributes published by Agent Gateway for per-tool policy:
  api.getAttribute('iap.googleapis.com/mcp.toolName', '')          # allow-list specific tools
  api.getAttribute('iap.googleapis.com/mcp.tool.isReadOnly', false)

Example — allow ONLY submit_pto_request on hr-actions instead of blanket read-only:
  --condition="expression=api.getAttribute('iap.googleapis.com/mcp.toolName'\,'') == 'submit_pto_request',title=PtoOnly"

Reminder: run first with the gateway's IAP extension in DRY_RUN, inspect the
audit logs, then flip to enforcement.
EON
