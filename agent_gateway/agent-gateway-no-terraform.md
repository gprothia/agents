# Agent Gateway codelab — no-Terraform runbook

This is the [Google codelab](https://codelabs.developers.google.com/cloudnet-agent-gateway) translated into direct `gcloud` / `curl` commands. You'll provision the same ~40 resources Terraform does, but step by step.

Scope: **default path only** (Cloud Run with public ingress, `ingress=all`). The private-networking path adds an internal Application Load Balancer, Certificate Manager, DNS peering and a public DNS zone — roughly doubles the command count and needs a domain you control. If you want that path later, the codelab's section 5–6 spell it out.

---

## ⚠️ Read before you start

1. **Agent Gateway is in Private Preview.** Submit the [access request form](https://docs.google.com/forms/d/e/1FAIpQLSd5QmS3wgXzdTnXpksNERDOU7Xed7x0Y9jWajrJaa1ugf51BQ/viewform) and confirm allowlisting **before** doing anything else. Without it, every `gcloud alpha network-services agent-gateways` and `gcloud alpha agent-registry` command will fail with PERMISSION_DENIED or 404.
2. **You lose Terraform's safety net.** If step 23 fails halfway, you'll have orphaned resources from steps 1–22 sitting around. Either clean up manually or destroy the project and restart. There is no `terraform destroy`.
3. **Org-level permissions required.** A few IAM bindings are org-scoped. You need Owner on the project AND `roles/resourcemanager.organizationAdmin` (or equivalent) on the org.
4. **Quotas.** This burns through Cloud Run, VPC, Network Attachments, and Vertex AI quotas. Fresh projects are usually fine.
5. **APIs propagate slowly.** After enabling APIs, give them 60s before the next command. A few of the `alpha` services especially.

You still need the GitHub repo for the MCP server source code and the `mortgage-agent` ADK code — Terraform doesn't generate those. We just won't run `terraform apply`.

---

## 0. Tools you need locally

```bash
# uv (Python package manager) — needed for the ADK agent deploy
curl -LsSf https://astral.sh/uv/install.sh | sh

# skaffold — only used as a convenience to build+deploy the 3 MCP services in one go
curl -Lo skaffold https://storage.googleapis.com/skaffold/releases/latest/skaffold-linux-amd64 && \
  sudo install skaffold /usr/local/bin/

# envsubst — to render the Cloud Run yaml templates
sudo apt-get install -y gettext-base

# gcloud SDK — must be current enough to have alpha network-services agent-gateways
gcloud components update
gcloud components install alpha beta
```

You also need **Python 3.12+**.

---

## 1. Project, auth, env vars

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project <your-project-id>

export PROJECT_ID=$(gcloud config get-value project)
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
export ORG_ID=$(gcloud projects get-ancestors $PROJECT_ID | awk '$2 == "organization" {print $1}')
export REGION="us-central1"

# Sanity check — all three must print a value
echo $PROJECT_ID $PROJECT_NUMBER $ORG_ID
```

If `ORG_ID` is empty: `gcloud organizations list` and `export ORG_ID=<id>` manually.

---

## 2. Enable APIs

Terraform's foundation module enables ~30 APIs. Here are the ones you actually need for the default path:

```bash
gcloud services enable \
  compute.googleapis.com \
  serviceusage.googleapis.com \
  cloudresourcemanager.googleapis.com \
  iam.googleapis.com \
  storage.googleapis.com \
  dns.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  aiplatform.googleapis.com \
  discoveryengine.googleapis.com \
  iap.googleapis.com \
  modelarmor.googleapis.com \
  networkservices.googleapis.com \
  networksecurity.googleapis.com \
  agentregistry.googleapis.com \
  dlp.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  cloudtrace.googleapis.com
```

Wait ~60 seconds for propagation.

---

## 3. Clone the source repo

We still need the MCP server source code, the ADK agent, the Cloud Run yaml templates, and `scripts/grant_agent_mcp_egress.sh`. We just won't touch the `terraform/` directory.

```bash
git clone https://github.com/GoogleCloudPlatform/cloud-networking-solutions.git
cd cloud-networking-solutions/demos/agent-gateway
```

Directory contents that matter to us:

```
src/                # MCP servers + mortgage-agent source
cloudrun/           # Cloud Run service .yaml.tmpl files
scripts/            # grant_agent_mcp_egress.sh
skaffold.yaml.tmpl  # MCP build+deploy pipeline
```

---

## 4. Networking: VPC, subnets, NAT, firewall

The Agent Gateway egresses through a customer-owned PSC Interface, which needs a Network Attachment in your VPC. We need: a VPC, a primary subnet for Cloud NAT'd workloads, a PSC subnet for service connections, and a PSC-Interface subnet that the Network Attachment lives in.

> **CIDR note:** The codelab reserves `10.0.0.0/24`, `10.0.1.0/24`, `10.0.2.0/24` for Agent Gateway's internal use. Your PSC-I subnet must NOT overlap those. The values below avoid the conflict.

```bash
export VPC_NAME="gateway-vpc"
export PRIMARY_SUBNET="primary-subnet"
export PSC_SUBNET="psc-subnet"
export PSCI_SUBNET="psc-interface-subnet"
export PRIMARY_CIDR="10.10.0.0/24"
export PSC_CIDR="10.20.0.0/24"
export PSCI_CIDR="10.30.0.0/28"   # must be /28 minimum

# VPC
gcloud compute networks create $VPC_NAME \
  --subnet-mode=custom \
  --bgp-routing-mode=regional

# Primary subnet (for any future workloads / NAT)
gcloud compute networks subnets create $PRIMARY_SUBNET \
  --network=$VPC_NAME \
  --range=$PRIMARY_CIDR \
  --region=$REGION \
  --enable-private-ip-google-access

# PSC subnet (for Private Service Connect endpoints if needed)
gcloud compute networks subnets create $PSC_SUBNET \
  --network=$VPC_NAME \
  --range=$PSC_CIDR \
  --region=$REGION \
  --purpose=PRIVATE_SERVICE_CONNECT

# PSC-Interface subnet (the Agent Gateway egresses through here)
gcloud compute networks subnets create $PSCI_SUBNET \
  --network=$VPC_NAME \
  --range=$PSCI_CIDR \
  --region=$REGION
```

Cloud NAT so anything in the primary subnet can reach the public Cloud Run URLs:

```bash
gcloud compute routers create $VPC_NAME-router \
  --network=$VPC_NAME --region=$REGION

gcloud compute routers nats create $VPC_NAME-nat \
  --router=$VPC_NAME-router --region=$REGION \
  --nat-all-subnet-ip-ranges --auto-allocate-nat-external-ips
```

Firewall: allow Agent Gateway PSC-I traffic into your VPC. Agent Gateway publishes its source ranges; the codelab uses a permissive intra-VPC rule plus a rule to allow Google's health-check + tenant ranges.

```bash
# Allow Agent Gateway's reserved ranges to reach anything in the VPC
gcloud compute firewall-rules create allow-agent-gateway-ingress \
  --network=$VPC_NAME \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp \
  --source-ranges=10.0.0.0/24,10.0.1.0/24,10.0.2.0/24,$PSCI_CIDR
```

---

## 5. Network Attachment for Agent Gateway

The Agent Gateway egresses through a **PSC Interface Network Attachment** that lives in your VPC. This is what makes private MCP servers reachable (and on the default path, gives the gateway a stable network identity).

```bash
gcloud compute network-attachments create agent-gateway-na \
  --region=$REGION \
  --subnets=$PSCI_SUBNET \
  --connection-preference=ACCEPT_AUTOMATIC
```

> `ACCEPT_AUTOMATIC` accepts from any producer and cannot be combined with `--producer-accept-list` / `--producer-reject-list`. If you want explicit allowlisting, switch to `--connection-preference=ACCEPT_MANUAL` and pass the producer list — but for the codelab the automatic mode is correct, since the Agent Gateway tenant project ID isn't something you can predict in advance.

---

## 6. Artifact Registry

For the MCP container images.

```bash
gcloud artifacts repositories create agent-gateway-repo \
  --repository-format=docker \
  --location=$REGION \
  --description="MCP server images for Agent Gateway codelab"
```

---

## 7. Service accounts

Each Cloud Run MCP service runs as its own SA. The agent uses a separate "invoker" SA when calling MCP servers through the gateway.

```bash
# Per-MCP runtime SAs (these run the Cloud Run services)
for svc in legacy-dms corporate-email income-verification; do
  gcloud iam service-accounts create mcp-${svc} \
    --display-name="MCP runtime SA for ${svc}"
done

# Agent MCP invoker SA — the principal that IAP REQUEST_AUTHZ will check
gcloud iam service-accounts create agent-mcp-invoker \
  --display-name="Agent MCP invoker SA"

export AGENT_INVOKER_SA="agent-mcp-invoker@${PROJECT_ID}.iam.gserviceaccount.com"
```

Grant yourself `serviceAccountUser` so you can deploy Cloud Run services as those SAs:

```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="user:$(gcloud config get-value account)" \
  --role="roles/iam.serviceAccountUser"
```

Give the agent invoker SA the baseline roles it needs:

```bash
# AI Platform user — so the agent can call Gemini
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${AGENT_INVOKER_SA}" \
  --role="roles/aiplatform.user"

# Logging + tracing
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${AGENT_INVOKER_SA}" \
  --role="roles/logging.logWriter"
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${AGENT_INVOKER_SA}" \
  --role="roles/cloudtrace.agent"
```

> The per-MCP-server `roles/iap.egressor` binding comes later (step 14), AFTER you know the agent's reasoning engine ID.

---

## 8. Build and deploy the 3 MCP servers

The codelab's `skaffold.yaml.tmpl` and `cloudrun/*.yaml.tmpl` already do this — they just need env vars substituted in. You're at the repo root (`demos/agent-gateway/`).

```bash
export MCP_INGRESS=all   # default path; use internal-and-cloud-load-balancing for private

envsubst '${PROJECT_ID} ${REGION} ${MCP_INGRESS}' < skaffold.yaml.tmpl > skaffold.yaml
for f in cloudrun/*.yaml.tmpl; do
  envsubst '${PROJECT_ID} ${REGION} ${MCP_INGRESS}' < "$f" > "${f%.tmpl}"
done

# Builds 3 images with Cloud Build, deploys 3 Cloud Run services
skaffold run
```

If you'd rather skip skaffold, you can do it manually per service:

```bash
# Example for one service
gcloud builds submit src/legacy-dms \
  --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/agent-gateway-repo/legacy-dms:latest

gcloud run deploy legacy-dms \
  --image=${REGION}-docker.pkg.dev/${PROJECT_ID}/agent-gateway-repo/legacy-dms:latest \
  --region=$REGION \
  --service-account="mcp-legacy-dms@${PROJECT_ID}.iam.gserviceaccount.com" \
  --ingress=all \
  --no-allow-unauthenticated
```

Repeat for `corporate-email` and `income-verification` (the source dir is `src/income-verification-api`).

Verify all three are healthy:

```bash
gcloud run services list --region=$REGION
```

Capture the URLs — you'll need them when registering MCP servers:

```bash
export DMS_URL=$(gcloud run services describe legacy-dms --region=$REGION --format='value(status.url)')
export EMAIL_URL=$(gcloud run services describe corporate-email --region=$REGION --format='value(status.url)')
export INCOME_URL=$(gcloud run services describe income-verification --region=$REGION --format='value(status.url)')
```

---

## 9. Allow the agent invoker SA to call each Cloud Run service

Each Cloud Run service is deployed `--no-allow-unauthenticated`. The agent calls them through the gateway, but the SA still needs `roles/run.invoker` on each service:

```bash
for svc in legacy-dms corporate-email income-verification; do
  gcloud run services add-iam-policy-binding $svc \
    --region=$REGION \
    --member="serviceAccount:${AGENT_INVOKER_SA}" \
    --role="roles/run.invoker"
done
```

---

## 10. Register Agent Registry endpoints

The Agent Registry catalogs everything the agent can call. Two flavors:

- **Services** = Google APIs (Vertex AI, IAP, Discovery Engine, etc.) the agent might hit
- **MCP servers** = your three Cloud Run services

### Google API services

For each API, the codelab registers four variants (global, mTLS global, regional, regional REP). The full list is in `terraform/modules/agent-registry-endpoints/scripts/register_endpoints.sh.tpl`. Minimum viable set for this demo:

```bash
# Vertex AI — global
gcloud alpha agent-registry services create aiplatform \
  --project=$PROJECT_ID --location=$REGION \
  --display-name="Vertex AI Platform" \
  --endpoint-spec-type=no-spec \
  --interfaces="url=https://aiplatform.googleapis.com,protocolBinding=JSONRPC"

# Vertex AI — regional
gcloud alpha agent-registry services create ${REGION}-aiplatform \
  --project=$PROJECT_ID --location=$REGION \
  --display-name="Vertex AI Platform Locational" \
  --endpoint-spec-type=no-spec \
  --interfaces="url=https://${REGION}-aiplatform.googleapis.com,protocolBinding=JSONRPC"

# IAP — note: minimum service ID length is 4 chars, so 'iap-service' (not 'iap')
gcloud alpha agent-registry services create iap-service \
  --project=$PROJECT_ID --location=$REGION \
  --display-name="Identity-Aware Proxy" \
  --endpoint-spec-type=no-spec \
  --interfaces="url=https://iap.googleapis.com,protocolBinding=JSONRPC"

# Discovery Engine
gcloud alpha agent-registry services create discoveryengine \
  --project=$PROJECT_ID --location=$REGION \
  --display-name="Discovery Engine" \
  --endpoint-spec-type=no-spec \
  --interfaces="url=https://discoveryengine.googleapis.com,protocolBinding=JSONRPC"
```

### MCP servers

Each MCP server's tool spec lives in `src/<svc>/toolspec.json`. Register them pointing at the public Cloud Run URLs:

```bash
gcloud alpha agent-registry services create legacy-dms \
  --project=$PROJECT_ID --location=$REGION \
  --display-name="Legacy DMS" \
  --mcp-server-spec-type=tool-spec \
  --mcp-server-spec-content=src/legacy-dms/toolspec.json \
  --interfaces="url=${DMS_URL}/mcp,protocolBinding=JSONRPC"

gcloud alpha agent-registry services create corporate-email \
  --project=$PROJECT_ID --location=$REGION \
  --display-name="Corporate Email" \
  --mcp-server-spec-type=tool-spec \
  --mcp-server-spec-content=src/corporate-email/toolspec.json \
  --interfaces="url=${EMAIL_URL}/mcp,protocolBinding=JSONRPC"

gcloud alpha agent-registry services create income-verification \
  --project=$PROJECT_ID --location=$REGION \
  --display-name="Income Verification" \
  --mcp-server-spec-type=tool-spec \
  --mcp-server-spec-content=src/income-verification-api/toolspec.json \
  --interfaces="url=${INCOME_URL}/mcp,protocolBinding=JSONRPC"
```

Verify:

```bash
gcloud alpha agent-registry services list \
  --project=$PROJECT_ID --location=$REGION \
  --format="table(displayName,name)"

gcloud alpha agent-registry mcp-servers list \
  --project=$PROJECT_ID --location=$REGION \
  --format="table(displayName,name)"
```

You should see 3 MCP servers and 4+ services.

---

## 11. Model Armor: templates

Model Armor screens prompts and responses for prompt injection, jailbreaks, RAI violations, and (optionally) PII.

```bash
# Request template — screens user prompts going INTO the agent
curl -fsS -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -H "x-goog-user-project: ${PROJECT_ID}" \
  "https://modelarmor.${REGION}.rep.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/templates?template_id=agw-request-template" \
  -d '{
    "filterConfig": {
      "raiSettings": {
        "raiFilters": [
          {"filterType": "HATE_SPEECH", "confidenceLevel": "MEDIUM_AND_ABOVE"},
          {"filterType": "SEXUALLY_EXPLICIT", "confidenceLevel": "MEDIUM_AND_ABOVE"},
          {"filterType": "HARASSMENT", "confidenceLevel": "MEDIUM_AND_ABOVE"},
          {"filterType": "DANGEROUS", "confidenceLevel": "MEDIUM_AND_ABOVE"}
        ]
      },
      "piAndJailbreakFilterSettings": {
        "filterEnforcement": "ENABLED",
        "confidenceLevel": "MEDIUM_AND_ABOVE"
      }
    }
  }'

# Response template — screens tool responses coming back, with SDP/DLP redaction
curl -fsS -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -H "x-goog-user-project: ${PROJECT_ID}" \
  "https://modelarmor.${REGION}.rep.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/templates?template_id=agw-response-template" \
  -d '{
    "filterConfig": {
      "raiSettings": {
        "raiFilters": [
          {"filterType": "HATE_SPEECH", "confidenceLevel": "MEDIUM_AND_ABOVE"},
          {"filterType": "SEXUALLY_EXPLICIT", "confidenceLevel": "MEDIUM_AND_ABOVE"}
        ]
      },
      "sdpSettings": {
        "basicConfig": {
          "filterEnforcement": "ENABLED"
        }
      }
    }
  }'
```

The Model Armor service agent needs DLP roles to call SDP:

```bash
# Force the service agent to exist
gcloud beta services identity create --service=modelarmor.googleapis.com --project=$PROJECT_ID

export MA_SA="service-${PROJECT_NUMBER}@gcp-sa-modelarmor.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${MA_SA}" --role="roles/dlp.user"
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${MA_SA}" --role="roles/dlp.reader"
```

---

## 12. Create the Agent Gateway

This is the central pivot of the whole stack.

```bash
cat > /tmp/agent-gateway.yaml <<EOF
name: agent-gateway
protocols: [MCP]
googleManaged:
  governedAccessPath: AGENT_TO_ANYWHERE
registries:
  - "//agentregistry.googleapis.com/projects/${PROJECT_ID}/locations/${REGION}"
networkConfig:
  egress:
    networkAttachment: projects/${PROJECT_ID}/regions/${REGION}/networkAttachments/agent-gateway-na
EOF

gcloud alpha network-services agent-gateways import agent-gateway \
  --source=/tmp/agent-gateway.yaml \
  --location=$REGION
```

Wait ~30 seconds (the gateway's tenant project takes a moment to settle — this is the `time_sleep.wait_for_gateway` Terraform handles for you), then verify:

```bash
sleep 30
gcloud alpha network-services agent-gateways describe agent-gateway --location=$REGION
```

---

## 13. Attach the two service extensions (IAP + Model Armor)

The gateway delegates authorization to two service extensions. **REQUEST_AUTHZ** runs once per request (used for IAP IAM checks). **CONTENT_AUTHZ** streams body events (used for Model Armor).

### IAP REQUEST_AUTHZ extension

```bash
cat > /tmp/iap-authz-extension.yaml <<EOF
name: agent-gateway-iap-authz
service: iap.googleapis.com
failOpen: true
timeout: 1s
EOF

gcloud beta service-extensions authz-extensions import agent-gateway-iap-authz \
  --source=/tmp/iap-authz-extension.yaml \
  --location=$REGION \
  --project=$PROJECT_ID
```

Bind it to the gateway as a REQUEST_AUTHZ policy:

```bash
curl -fsS -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -X POST "https://networksecurity.googleapis.com/v1alpha1/projects/${PROJECT_ID}/locations/${REGION}/authzPolicies?authz_policy_id=agent-gateway-iap-policy" \
  -d "{
    \"name\": \"agent-gateway-iap-policy\",
    \"policyProfile\": \"REQUEST_AUTHZ\",
    \"action\": \"CUSTOM\",
    \"target\": {
      \"resources\": [
        \"projects/${PROJECT_ID}/locations/${REGION}/agentGateways/agent-gateway\"
      ]
    },
    \"customProvider\": {
      \"authzExtension\": {
        \"resources\": [
          \"projects/${PROJECT_ID}/locations/${REGION}/authzExtensions/agent-gateway-iap-authz\"
        ]
      }
    }
  }"
```

> **IMPORTANT:** The codelab starts in **DRY_RUN mode** (audit-only) by setting an enforcement-mode flag on the IAP authz. The gateway-level enforcement mode is set via a separate property on the gateway/policy. To replicate Terraform's `agent_gateway_iap_iam_enforcement_mode = "DRY_RUN"`, you'll patch the policy after the agent is deployed and validated. For now, the policy exists but isn't being strictly enforced until you grant the egressor IAM later. We'll flip to enforce mode in step 17.

### Model Armor CONTENT_AUTHZ extension

```bash
cat > /tmp/ma-extension.yaml <<EOF
name: agent-gateway-ma-authz
service: modelarmor.${REGION}.rep.googleapis.com
failOpen: true
timeout: 1s
metadata:
  model_armor_settings: '[
    {
      "request_template_id":  "projects/${PROJECT_ID}/locations/${REGION}/templates/agw-request-template",
      "response_template_id": "projects/${PROJECT_ID}/locations/${REGION}/templates/agw-response-template"
    }
  ]'
EOF

gcloud beta service-extensions authz-extensions import agent-gateway-ma-authz \
  --source=/tmp/ma-extension.yaml \
  --location=$REGION \
  --project=$PROJECT_ID
```

Bind as CONTENT_AUTHZ:

```bash
curl -fsS -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -X POST "https://networksecurity.googleapis.com/v1alpha1/projects/${PROJECT_ID}/locations/${REGION}/authzPolicies?authz_policy_id=agent-gateway-ma-policy" \
  -d "{
    \"name\": \"agent-gateway-ma-policy\",
    \"policyProfile\": \"CONTENT_AUTHZ\",
    \"action\": \"CUSTOM\",
    \"target\": {
      \"resources\": [
        \"projects/${PROJECT_ID}/locations/${REGION}/agentGateways/agent-gateway\"
      ]
    },
    \"customProvider\": {
      \"authzExtension\": {
        \"resources\": [
          \"projects/${PROJECT_ID}/locations/${REGION}/authzExtensions/agent-gateway-ma-authz\"
        ]
      }
    }
  }"
```

---

## 14. Deploy the ADK agent (mortgage-agent) to Agent Runtime

This is the only step that runs Python. The agent will auto-discover MCP tools from the registry at startup.

```bash
cd src/mortgage-agent
uv sync

uv run python deploy_agent.py \
  --project=$PROJECT_ID \
  --region=$REGION \
  --enable-agent-identity \
  --agent-name=mortgage-agent \
  --agent-gateway=projects/${PROJECT_ID}/locations/${REGION}/agentGateways/agent-gateway \
  --mcp-invoker-sa=$AGENT_INVOKER_SA \
  --model-endpoint-location=global
```

When this finishes, it prints something like `reasoningEngines/4262292559201566720`. Capture that numeric ID:

```bash
export AGENT_ID=<numeric-id-from-output>
cd ../..   # back to demos/agent-gateway/
```

---

## 15. Grant per-MCP-server IAP egressor IAM

This is the policy enforcement step. The IAP REQUEST_AUTHZ extension authorizes each tool call by checking the agent's `roles/iap.egressor` on the *specific MCP server* being called.

Use the codelab's helper script — it iterates the registered MCP servers and adds the binding:

```bash
./scripts/grant_agent_mcp_egress.sh \
  --mcp \
  --agent-id ${AGENT_ID}
```

That grants unconditional egress to all three MCP servers. To replicate the codelab's **conditional** grant (read-only tools on `corporate-email`), also run:

```bash
./scripts/grant_agent_mcp_egress.sh \
  --mcp \
  --agent-id ${AGENT_ID} \
  --mcp-filter "corporate-email" \
  --condition-expression "api.getAttribute('iap.googleapis.com/mcp.tool.isReadOnly', false) == true" \
  --condition-title "ReadOnlyToolsOnly" \
  --condition-description "Restrict ${AGENT_ID} to read-only tools on corporate-email"
```

This means writes to `corporate-email` (i.e. `send_email`) will be denied once IAP is in enforce mode — reads stay allowed.

Also grant egress on the Google API endpoints (otherwise the agent can't call Vertex AI through the gateway):

```bash
./scripts/grant_agent_mcp_egress.sh \
  --agent-id ${AGENT_ID} \
  --endpoints
```

Verify in the console: **[Agent Platform → Policies](https://console.cloud.google.com/agent-platform/policies/iam)**. You should see policies attached to each MCP server and to the registered endpoints.

---

## 16. Smoke test in the Playground

While IAP is still in audit-only / dry-run, the agent should be able to call **everything** including the write tool.

1. Go to **[Agent Platform Deployments](https://console.cloud.google.com/agent-platform/runtimes)**.
2. Click your `mortgage-agent` runtime.
3. Open the **Playground** tab.
4. First prompt:

   > I am reviewing the Sterling family's current application. Can you summarize their 2024 and 2025 tax returns and verify if their total household income meets our 2026 debt-to-income requirements?

   You should see tool calls to `legacy-dms` (tax returns) and `income-verification` (income check). SSNs in the response should come back redacted (Model Armor).

5. Second prompt:

   > Can you send a summary of this to my email jane@example.com

   In dry-run mode the email tool call **succeeds** even though the conditional policy on `corporate-email` would normally block it. The Trace side panel will show the IAP REQUEST_AUTHZ span logged it as a *would-deny*.

---

## 17. Flip IAP to enforce mode

You'll need to patch the IAP authorization policy to actually enforce, not audit. The exact knob depends on the gateway's current state; the simplest path is to update the policy via the REST API:

```bash
# Read current policy
curl -fsS -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://networksecurity.googleapis.com/v1alpha1/projects/${PROJECT_ID}/locations/${REGION}/authzPolicies/agent-gateway-iap-policy" \
  > /tmp/iap-policy.json

# In Terraform's case, the enforcement_mode flag flips from DRY_RUN -> null (i.e. enforce).
# For the API, you patch the gateway's IAP integration setting. The exact field path
# depends on the current alpha API shape; use:
gcloud alpha network-services agent-gateways update agent-gateway \
  --location=$REGION \
  --iap-iam-enforcement-mode=ENFORCED 2>/dev/null || true

# Alternative if the flag above isn't surfaced in your gcloud version, patch via REST:
curl -fsS -X PATCH \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  "https://networkservices.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/${REGION}/agentGateways/agent-gateway?updateMask=iapSettings.iamEnforcementMode" \
  -d '{"iapSettings": {"iamEnforcementMode": "ENFORCED"}}'
```

> If both commands above 404 in your environment, look at `terraform/modules/agent-gateway/main.tf` for the literal field name your current alpha API expects — the Private Preview surface has been moving. The Terraform module is the source of truth.

Now re-run the same two prompts in the Playground:

- Prompt 1 (tax returns / income) — still works.
- Prompt 2 (send email) — agent should reply that it **cannot send the email due to the authorization policy.** That's IAP REQUEST_AUTHZ enforcing the read-only CEL condition on `corporate-email`.

---

## 18. (Optional) Register with Gemini Enterprise

Follow [these steps](https://docs.cloud.google.com/gemini/enterprise/docs/register-and-manage-an-adk-agent#register-an-adk-agent). Summary:

1. Enable Gemini Enterprise in your project ([quickstart](https://docs.cloud.google.com/gemini/enterprise/docs/quickstart-gemini-enterprise)).
2. Open the Gemini Enterprise app, navigate to **Agents → Register**.
3. Point it at your reasoning engine: `projects/${PROJECT_ID}/locations/${REGION}/reasoningEngines/${AGENT_ID}`.
4. The Agent Gallery should now show **Mortgage Assistant Agent**.
5. Run the same prompts there. In Cloud Trace, you'll see spans now originating from the Gemini Enterprise frontend instead of the runtime Playground.

---

## 19. Cleanup

In reverse order, more or less:

```bash
# Reasoning engine first (not deletable while resources reference it)
gcloud beta ai reasoning-engines delete $AGENT_ID --region=$REGION --project=$PROJECT_ID

# Authz policies + extensions
gcloud beta service-extensions authz-extensions delete agent-gateway-iap-authz --location=$REGION
gcloud beta service-extensions authz-extensions delete agent-gateway-ma-authz  --location=$REGION

curl -fsS -X DELETE -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://networksecurity.googleapis.com/v1alpha1/projects/${PROJECT_ID}/locations/${REGION}/authzPolicies/agent-gateway-iap-policy"
curl -fsS -X DELETE -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://networksecurity.googleapis.com/v1alpha1/projects/${PROJECT_ID}/locations/${REGION}/authzPolicies/agent-gateway-ma-policy"

# Agent Gateway
gcloud alpha network-services agent-gateways delete agent-gateway --location=$REGION

# Network Attachment
gcloud compute network-attachments delete agent-gateway-na --region=$REGION

# Agent Registry — list and delete each
gcloud alpha agent-registry mcp-servers list --location=$REGION --format='value(name)' \
  | xargs -I{} gcloud alpha agent-registry mcp-servers delete {} --location=$REGION --quiet
gcloud alpha agent-registry services list --location=$REGION --format='value(name)' \
  | xargs -I{} gcloud alpha agent-registry services delete {} --location=$REGION --quiet

# Model Armor templates
curl -fsS -X DELETE -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://modelarmor.${REGION}.rep.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/templates/agw-request-template"
curl -fsS -X DELETE -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://modelarmor.${REGION}.rep.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/templates/agw-response-template"

# Cloud Run + Artifact Registry
for svc in legacy-dms corporate-email income-verification; do
  gcloud run services delete $svc --region=$REGION --quiet
done
gcloud artifacts repositories delete agent-gateway-repo --location=$REGION --quiet

# Service accounts
for svc in legacy-dms corporate-email income-verification; do
  gcloud iam service-accounts delete mcp-${svc}@${PROJECT_ID}.iam.gserviceaccount.com --quiet
done
gcloud iam service-accounts delete $AGENT_INVOKER_SA --quiet

# Networking
gcloud compute firewall-rules delete allow-agent-gateway-ingress --quiet
gcloud compute routers nats delete $VPC_NAME-nat --router=$VPC_NAME-router --region=$REGION --quiet
gcloud compute routers delete $VPC_NAME-router --region=$REGION --quiet
gcloud compute networks subnets delete $PSCI_SUBNET --region=$REGION --quiet
gcloud compute networks subnets delete $PSC_SUBNET --region=$REGION --quiet
gcloud compute networks subnets delete $PRIMARY_SUBNET --region=$REGION --quiet
gcloud compute networks delete $VPC_NAME --quiet
```

---

## Troubleshooting

**`PERMISSION_DENIED` on any `alpha agent-registry` or `network-services agent-gateways` command**
→ You're not allowlisted for the Private Preview. Submit the form linked at the top. Nothing else in this runbook will work until that clears.

**Agent boots with "no MCP servers found"**
→ Re-list the registry: `gcloud alpha agent-registry mcp-servers list --location=$REGION`. If empty, your URLs in step 10 were wrong. Re-register.

**Tool calls return `403 PermissionDenied` even on a fresh deploy**
→ Re-run `scripts/grant_agent_mcp_egress.sh --mcp --agent-id $AGENT_ID`. The `reasoningEngines/` ID changes on every redeploy, so old bindings are stale.

**`skaffold run` fails with "permission denied on service account"**
→ You skipped the `roles/iam.serviceAccountUser` self-grant in step 7.

**Agent Gateway create returns "resource is being created and therefore can not be updated"**
→ Wait 30s and retry. The tenant project takes a moment to settle. Terraform handles this with a `time_sleep` resource.

**Model Armor extension returns 5xx**
→ Confirm the Model Armor service agent has `dlp.user` + `dlp.reader` (step 11). Also confirm templates exist: `gcloud alpha model-armor templates list --location=$REGION`.

**You can't find a setting Terraform applies (e.g. DNS peering, IAP enforcement mode)**
→ The alpha API surface is moving. The Terraform module under `terraform/modules/agent-gateway/main.tf` is the canonical source for current field names. When in doubt, read what Terraform does and translate it to a `curl` PATCH on `networkservices.googleapis.com/v1beta1`.

---

## What you're trading off vs Terraform

| Terraform gives you | Hand-rolling costs |
|---|---|
| Idempotent re-runs | Manual cleanup of half-created resources on any failure |
| Single source of truth for ~40 resource configs | Have to keep env vars + scripts in sync yourself |
| Implicit dependency ordering | You re-discover ordering bugs the codelab papered over (e.g. `time_sleep.wait_for_gateway`) |
| `lifecycle.ignore_changes` for Cloud Run images | Easy to accidentally regress to the placeholder image |
| Conditional logic (`enable_cloud_run_private_networking`) | Branching by hand if you switch paths |
| Free destroy | Cleanup script above is your only undo |

If you're doing this to *learn the moving parts*, the hand-rolled path is genuinely educational. If you're doing it because Terraform is failing for some specific reason, fix the Terraform — it's strictly less work.
