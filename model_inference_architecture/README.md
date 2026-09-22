# Centralized Multi-Backend Inference Platform

This repository contains both the **platform architecture** and the **installation
instructions** for standing it up as a shared model-serving platform for your company.

The platform gives every team in the organization a single, governed way to consume large
language models, regardless of how those models are hosted:

- **Gemini Enterprise Agent Platform (GEAP) / Vertex AI** is the primary home for models of
  different types — fully managed serverless models billed per token, and self-deployed
  open models running on dedicated GPU-backed endpoints.
- **GKE** hosts a custom Gemma model served with vLLM, for cases that need full control over
  the serving stack, the container image, or the inference runtime.

In front of all of them sits a **model gateway**, implemented with the **LiteLLM proxy**. It
exposes one OpenAI-compatible API, so a caller uses the same request shape no matter which
backend answers. **Consumer projects connect to the gateway** — not to the models — and run
their inference through it.

That indirection is what makes the platform shareable. The gateway issues per-application
**virtual keys**, enforces **budgets and rate limits**, records **spend for chargeback**, and
calls Vertex AI using **its own service account**. Consumer projects never hold a Google
credential, and onboarding a new team is a key, not a new deployment.

The sections below walk through the implementation step by step: enabling APIs, building the
network, standing up each of the three backends, installing and configuring the gateway,
connecting a consumer project, and tearing it all down again.


```mermaid
graph LR
    subgraph CONSUMER1["Consumer Project A"]
        A1["App VM<br/>vpc-a"]
    end
    subgraph CONSUMER2["Consumer Project B"]
        A2["App VM<br/>vpc-b"]
    end
    subgraph CONSUMER3["Consumer Project C"]
        A3["App VM<br/>vpc-c"]
    end

    subgraph CENTRAL["Central Platform Project"]
        subgraph GW["Gateway VM · litellm-gw · inference-vpc"]
            B["LiteLLM Gateway<br/>:4000"]
            F[("PostgreSQL")]
        end
        subgraph GEAP["GEAP / Vertex"]
            C["serverless-gemini<br/>Vertex AI managed"]
            D["self-deployed-gemma<br/>Model Garden endpoint"]
            E["gke-gemma<br/>vLLM route"]
        end
        subgraph SDVM["Self-Deployed VM"]
            V["Model server<br/>gemma-3-1b-it · 1× L4"]
        end
        subgraph GKEC["GKE Cluster · gke-inference"]
            K["vLLM Pod<br/>gemma-3-1b-it · 1× L4"]
        end
    end

    A1 -->|"VPC Peering<br/>+ firewall tcp:4000"| B
    A2 -->|"VPC Peering<br/>+ firewall tcp:4000"| B
    A3 -->|"VPC Peering<br/>+ firewall tcp:4000"| B
    B --> C
    B --> D
    B --> E
    D --> V
    E --> K




```


Reading the diagram: each consumer project keeps its own VPC and reaches the gateway over
VPC peering, with a firewall admitting only `tcp:4000`. The gateway resolves the requested
model name to one of three routes — managed Gemini, a self-deployed Model Garden endpoint,
or the vLLM pod on GKE — and holds the Postgres database that backs virtual keys, budgets,
and spend. Adding a fourth consumer means peering a VPC and issuing a key; adding a fourth
model means one entry in the gateway's model list.


---

## Repository Layout

```
inference_architecture/
├── README.md                      # this file
├── generate_gemini_traffic.py     # load generator (see "Traffic Generation")
├── gke-gemma.yaml                 # vLLM Deployment + internal LB Service
└── gke_vllm-podmonitoring.yaml    # Managed Prometheus scrape config
```

**`README.md`** — this file: the **inference architecture summary** followed by the
**step-by-step installation instructions** for implementing it in your own GCP environment.
The build produces a **centralized project that acts as the hub for all inference**, hosting
three models of deliberately different deployment types — managed serverless Gemini, a
self-deployed Gemma on a Vertex AI Model Garden endpoint, and Gemma self-hosted on GKE with
vLLM. A VM in that hub runs LiteLLM with all three registered as endpoints behind one
OpenAI-compatible API, so callers pick a backend by model name and never learn how it runs.
A **consumer project** then establishes private network connectivity to the gateway and calls
any registered model with a scoped virtual key rather than a Google credential. Sections are
numbered and must be run in order; every command is plain `gcloud` or `kubectl` parameterised
by `$CENTRAL_PROJECT` and `$CONSUMER_PROJECT`, so nothing is environment-specific.

**`generate_gemini_traffic.py`** — a load generator that fires randomized prompts at the
gateway, rotating across all three models, so Cloud Monitoring, the Admin UI, and billing
views have data. Supports a fixed volume (`--requests`) or sustained load (`--duration` with
`--qps`), and reports a per-model breakdown of latency percentiles and token counts. It
authenticates with a virtual key over the same path a real consumer uses, so it needs no
Google credentials and only the Python standard library.

**`gke-gemma.yaml`** — the GKE workload for the self-hosted backend: a `gemma-vllm` Deployment
plus an internal-only `gemma-vllm-svc` Service. It serves `google/gemma-3-1b-it` on one L4,
pulling the Hugging Face token from the `hf-secret` Secret, and publishes a private IP inside
`inference-vpc`. Note it declares **no readiness probe**, so the pod reports `1/1 Running`
minutes before vLLM can actually serve.

**`gke_vllm-podmonitoring.yaml`** — an optional `PodMonitoring` resource that scrapes vLLM's
`/metrics` every 30 seconds via Managed Prometheus. It surfaces serving metrics under
`prometheus.googleapis.com/vllm:*` — latency, time-to-first-token, tokens/sec, queue depth,
KV-cache use — which is the only way to tell whether a slow request was queueing, cache
pressure, or compute.

Everything is provisioned with `gcloud` and `kubectl`. There is no infrastructure-as-code
state to manage, which also means **nothing tracks what you created** — teardown is manual
and is your responsibility (see [Teardown](#teardown)).

---

## The Three Backends

| LiteLLM model name | Backend | GPU | Cost when idle |
| :--- | :--- | :--- | :--- |
| `serverless-gemini` | Vertex AI managed Gemini | none | **$0** — pay per token |
| `selfhosted-gemma` | Model Garden → Vertex endpoint | 1× L4 | billed hourly |
| `gke-gemma` | vLLM pod on GKE Autopilot | 1× L4 | billed hourly |

> [!IMPORTANT]
> The two L4 GPUs dominate the bill and run 24/7 once deployed. You need **L4 quota ≥ 2**
> in your region. Deploy only sections 1–3 and 6–7 for a gateway + serverless demo at
> near-zero standing cost.

Identify which backend actually served a request from the response metadata, not from the
model's own answer:

| Marker in response | Backend |
| :--- | :--- |
| `vertex_ai_safety_results`, `vertex_ai_grounding_metadata` | Vertex managed Gemini |
| `stop_reason: 106`, `chatcmpl-<uuid>` | Model Garden endpoint |
| `system_fingerprint: "vllm-..."` | GKE vLLM |

---

## Prerequisites

```bash
gcloud version

# Two independent credential stores — you need BOTH
gcloud auth login                        # the gcloud CLI
gcloud auth application-default login    # everything else (kubectl, client libraries)

gcloud auth list                         # confirm '*' is your user, not a service account
```

> [!WARNING]
> `gcloud auth login` does **not** refresh Application Default Credentials. If you later
> see `invalid_grant / reauth related error (invalid_rapt)`, re-run the
> `application-default` variant. If your active gcloud configuration is bound to a service
> account, IAP SSH will fail with an account-mismatch error — pass `--account=<your-user>`
> or activate a different configuration.

Set the project IDs used throughout this guide:

```bash
export CENTRAL_PROJECT="<project hosting the gateway, GKE, and Model Garden endpoint>"
export CONSUMER_PROJECT="<project whose workloads call the gateway>"
export REGION="us-central1"
export ZONE="us-central1-a"
```

---

## 1. Enable APIs

**Central project:**

```bash
gcloud services enable \
  aiplatform.googleapis.com compute.googleapis.com container.googleapis.com \
  secretmanager.googleapis.com iap.googleapis.com artifactregistry.googleapis.com \
  monitoring.googleapis.com logging.googleapis.com iamcredentials.googleapis.com \
  cloudresourcemanager.googleapis.com cloudquotas.googleapis.com \
  --project $CENTRAL_PROJECT
```

| API | Purpose |
| :--- | :--- |
| `aiplatform` | Serverless Gemini + Model Garden endpoint |
| `compute` | VPC, subnet, firewall, gateway VM |
| `container` | GKE cluster |
| `secretmanager` | HF token, master key, DB password |
| `iap` | Private SSH |
| `artifactregistry` | Pulling serving/vLLM images |
| `monitoring` / `logging` | Metrics and logs |
| `iamcredentials` | Cross-project SA tokens |
| `cloudresourcemanager` | IAM bindings |
| `cloudquotas` | **Required by the Model Garden deploy preflight** |

**Consumer project:**

```bash
gcloud services enable compute.googleapis.com iamcredentials.googleapis.com \
  cloudresourcemanager.googleapis.com monitoring.googleapis.com \
  --project $CONSUMER_PROJECT
```

Note there is no `aiplatform` here. Nothing in the consumer project talks to Vertex AI — all
inference goes through the gateway, which calls Vertex as its own service account. A consumer
needs no Vertex AI permissions whatsoever.

**Quota check** — you need `NVIDIA_L4_GPUS` ≥ 2 in your region:

```bash
gcloud compute regions describe $REGION --project $CENTRAL_PROJECT \
  --format="table[no-heading](quotas:format='value(metric,limit,usage)')" \
  | grep NVIDIA_L4_GPUS
```

Output is `metric  limit  usage`. A brand-new project may report `0` — request an increase
before continuing, or the two GPU backends will fail to deploy.

---

## 2. Networking foundation

### 2.1 VPC and subnet

```bash
gcloud compute networks create inference-vpc --subnet-mode=custom \
  --project $CENTRAL_PROJECT

gcloud compute networks subnets create gw-subnet \
  --network=inference-vpc --region=$REGION \
  --range=10.10.0.0/24 --enable-private-ip-google-access \
  --project $CENTRAL_PROJECT
```

Private Google Access lets in-VPC resources reach Google APIs over the internal path.

### 2.2 Firewall rules

```bash
# Your public IPv4 — note the -4; without it you may get an IPv6 address,
# which is not a valid source range for these rules.
export ADMIN_IP=$(curl -4 -s ifconfig.me)

gcloud compute firewall-rules create allow-iap-ssh \
  --network=inference-vpc --direction=INGRESS --action=ALLOW \
  --rules=tcp:22 --source-ranges=35.235.240.0/20 \
  --project $CENTRAL_PROJECT

gcloud compute firewall-rules create allow-litellm \
  --network=inference-vpc --direction=INGRESS --action=ALLOW \
  --rules=tcp:4000 --source-ranges=10.10.0.0/24,$ADMIN_IP/32 \
  --target-tags=litellm-gw \
  --project $CENTRAL_PROJECT
```

> **Security note:** exposing `:4000` publicly is for convenient Admin-UI access. Keep the
> source range tight. The private-path design (internal LB, no public IP) is the production
> posture; the external IP here is a deliberate demo trade-off.

### 2.3 Cloud NAT

```bash
gcloud compute routers create inference-router \
  --network=inference-vpc --region=$REGION --project $CENTRAL_PROJECT

gcloud compute routers nats create inference-nat \
  --router=inference-router --region=$REGION \
  --auto-allocate-nat-external-ips --nat-all-subnet-ip-ranges \
  --project $CENTRAL_PROJECT
```

---

## 3. Backend 1 — Serverless (MaaS)

Nothing to deploy. Verify in **Vertex AI → Model Garden → Gemini Flash-Lite → Try it**.

LiteLLM route: `vertex_ai/gemini-2.5-flash-lite`

---

## 4. Backend 2 — Self-deployed Gemma on a Vertex endpoint

### 4.1 Grant the Vertex AI service agent deploy permissions

`gcloud ai model-garden models deploy` does **not** create the endpoint as you — it delegates
to the project's Vertex AI service agent. That agent is auto-created holding
`roles/aiplatform.serviceAgent`, which does **not** include `aiplatform.endpoints.create` or
`aiplatform.models.upload`. On a brand-new project the deploy therefore fails. Grant it
`roles/aiplatform.user` once:

```bash
export CENTRAL_PROJECT_NUMBER=$(gcloud projects describe $CENTRAL_PROJECT \
  --format="value(projectNumber)")

gcloud projects add-iam-policy-binding $CENTRAL_PROJECT \
  --member="serviceAccount:service-${CENTRAL_PROJECT_NUMBER}@gcp-sa-aiplatform.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user" \
  --condition=None
```

> [!WARNING]
> Skip this and the deploy fails after ~5 seconds with a bare `ERROR: INTERNAL` and no
> further detail. Being project Owner yourself does not help — the denied principal is the
> service agent, not you. The real cause is visible only in Cloud Logging:
>
> ```bash
> gcloud logging read 'severity>=WARNING' --project=$CENTRAL_PROJECT --limit=5 \
>   --format="value(protoPayload.methodName,protoPayload.status.message)"
> ```
>
> which shows `Permission 'aiplatform.endpoints.create' denied`. Allow ~30 seconds for the
> binding to propagate before retrying.

### 4.2 Deploy from Model Garden

```bash
gcloud ai model-garden models deploy \
  --model="google/gemma3@gemma-3-1b-it" \
  --machine-type=g2-standard-12 \
  --accelerator-type=NVIDIA_L4 --accelerator-count=1 \
  --region=$REGION --project $CENTRAL_PROJECT \
  --billing-project=$CENTRAL_PROJECT \
  --accept-eula \
  --use-dedicated-endpoint \
  --endpoint-display-name=selfhosted-gemma \
  --container-image-uri=us-docker.pkg.dev/vertex-ai/vertex-vision-model-garden-dockers/pytorch-vllm-serve:20260320_0916_RC01 \
  --container-ports=8080 \
  --container-health-route=/ping \
  --container-predict-route=/generate \
  --container-env-vars='^|^MODEL_ID=google/gemma-3-1b-it|DEPLOY_SOURCE=UI_NATIVE_MODEL' \
  --container-args='^|^python|-m|vllm.entrypoints.api_server|--host=0.0.0.0|--port=8080|--model=gs://vertex-model-garden-restricted-us/gemma3/gemma-3-1b-it|--tensor-parallel-size=1|--gpu-memory-utilization=0.8|--trust-remote-code'
```

Takes 10–20 minutes. Run it unpiped — the quota preflight asks an interactive `(y/N)`
question, and piping through `tail` or `head` buffers the prompt so the command appears to
hang indefinitely. Redirect to a file if you need the log.

> [!WARNING]
> **The container overrides are not optional.** Model Garden's own published deployment
> config for this model passes `--swap-space=16`, but the container image it pins
> (`pytorch-vllm-serve:20260320_0916_RC01`, vLLM 0.29) has **removed** that flag. The stock
> command therefore always fails — after burning ~13 minutes of GPU time — with:
>
> ```
> ERROR: Model server exited unexpectedly. Please use recommended machine spec.
> ```
>
> That message is misleading: the machine spec is fine and is one Google itself lists via
> `gcloud ai model-garden models list-deployment-config --model=...`. The real error appears
> only in the endpoint's container logs:
>
> ```
> api_server.py: error: unrecognized arguments: --swap-space=16
> ```
>
> The `--container-args` above are Google's defaults with `--swap-space=16` removed. If the
> deploy still fails, re-run `list-deployment-config --format=yaml` and diff its
> `containerSpec.args` against the list above — the pinned image may have moved again.
>
> Vertex deletes the endpoint when the deploy fails, so a failed attempt leaves nothing to
> clean up.

> [!IMPORTANT]
> `--use-dedicated-endpoint` is also required. Without it the endpoint is created with an
> empty `dedicatedEndpointDns`, and the `selfhosted-gemma` entry in section 7.4 cannot be
> built at all.

> [!IMPORTANT]
> `--billing-project=$CENTRAL_PROJECT` is required. Without it the quota preflight attributes
> its Cloud Quotas call to an unrelated Google-internal project and aborts with
> `PERMISSION_DENIED: Permission denied to enable service [cloudquotas.googleapis.com]`
> naming a project number you have never seen and cannot access. Having
> `cloudquotas.googleapis.com` enabled on the central project (section 1) is necessary but
> **not** sufficient — the flag is what points the preflight at the right project.

### 4.3 Get the endpoint ID and its dedicated DNS

```bash
gcloud ai endpoints list --region=$REGION --project $CENTRAL_PROJECT \
  --format="table(name.basename():label=ENDPOINT_ID, displayName, dedicatedEndpointDns)"
```

You need three values for the LiteLLM config: the **endpoint ID**, the
**`dedicatedEndpointDns`**, and your **project number**:

```bash
gcloud projects describe $CENTRAL_PROJECT --format="value(projectNumber)"
```

LiteLLM route: `vertex_ai/gemma/<ENDPOINT_ID>`

---

## 5. Backend 3 — Gemma on GKE with vLLM

### 5.1 Autopilot cluster

```bash
gcloud container clusters create-auto gke-inference \
  --region=$REGION --network=inference-vpc --subnetwork=gw-subnet \
  --enable-private-nodes \
  --project $CENTRAL_PROJECT

gcloud container clusters get-credentials gke-inference \
  --region=$REGION --project $CENTRAL_PROJECT
```

> [!IMPORTANT]
> `--enable-private-nodes` is required if your org enforces
> `constraints/compute.vmExternalIpAccess`. Without it, Autopilot tries to give each node an
> external IP and the cluster fails **after** provisioning starts, leaving a cluster in
> `ERROR` state that you must delete before retrying:
>
> ```
> Instance 'gk3-gke-inference-default-pool-...' creation failed:
> Constraint constraints/compute.vmExternalIpAccess violated for project <number>.
> ```
>
> Private nodes reach the internet for image pulls through the Cloud NAT built in
> section 2.3, so no other change is needed.

### 5.2 Hugging Face token

Accept the Gemma license on Hugging Face first, then:

```bash
kubectl create secret generic hf-secret --from-literal=hf_token=hf_XXXXXXXX
```

### 5.3 Deploy vLLM behind an internal load balancer

```bash
kubectl apply -f gke-gemma.yaml
kubectl get svc gemma-vllm-svc -w      # wait for EXTERNAL-IP (an internal 10.x address)
```

The Service is annotated `networking.gke.io/load-balancer-type: "Internal"`, so the address
it reports is a **private** IP inside `inference-vpc`, reachable only from that VPC or a
peered one. Port 80 maps to the container's 8000.

> [!IMPORTANT]
> The load-balancer IP is assigned within ~60 seconds, but vLLM is **not** serving yet. On a
> cold start it must pull a multi-GB image, download the model from Hugging Face, then run
> engine init and CUDA-graph capture — together about 5–10 minutes on an L4. Because
> `gke-gemma.yaml` declares no readiness probe, the pod reports `1/1 Running` almost
> immediately and the Service starts advertising an endpoint, so requests during this window
> fail with a bare `Connection error` that looks like a firewall or routing problem.
>
> Wait for the server to report startup before testing:
>
> ```bash
> kubectl logs deploy/gemma-vllm -f | grep -m1 "Application startup complete"
> ```
>
> Then confirm it answers:
>
> ```bash
> kubectl run curl-test --rm -it --restart=Never --image=curlimages/curl -- \
>   curl -s http://gemma-vllm-svc/v1/models
> ```
>
> Adding a `readinessProbe` on `/health` would make the Service withhold traffic until vLLM
> is genuinely up; it is omitted here to keep the manifest minimal.

LiteLLM route: `openai/google/gemma-3-1b-it` @ `http://<INTERNAL_LB_IP>/v1`

### 5.4 (Optional) vLLM metrics to Cloud Monitoring

```bash
kubectl apply -f gke_vllm-podmonitoring.yaml
```

Metrics appear as `prometheus.googleapis.com/vllm:...`.

---

## 6. PostgreSQL for the gateway

LiteLLM needs a database to persist virtual keys, teams, budgets, and spend, and to power
the Admin UI. This guide installs Postgres on the gateway VM. For production use Cloud SQL.

### 6.1 Create secrets

```bash
printf 'CHANGE_ME_db_pw'    | gcloud secrets create litellm-db-password --data-file=- --project $CENTRAL_PROJECT
printf 'sk-master-CHANGE_ME'| gcloud secrets create litellm-master-key  --data-file=- --project $CENTRAL_PROJECT
printf 'CHANGE_ME_ui_pw'    | gcloud secrets create litellm-ui-password --data-file=- --project $CENTRAL_PROJECT
```

> [!WARNING]
> Replace these placeholders with real generated values, e.g.
> `openssl rand -base64 24`. A deployment left on `sk-master-CHANGE_ME` is fully open to
> anyone who can reach port 4000.

### 6.2 Install Postgres *(run on the VM, after section 7.2)*

```bash
sudo apt-get update && sudo apt-get install -y postgresql postgresql-contrib
DB_PW=$(gcloud secrets versions access latest --secret=litellm-db-password)
sudo -u postgres psql -c "CREATE DATABASE litellm;"
sudo -u postgres psql -c "CREATE USER litellm WITH PASSWORD '${DB_PW}';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE litellm TO litellm;"
sudo -u postgres psql -c "ALTER DATABASE litellm OWNER TO litellm;"
sudo systemctl restart postgresql
```

### 6.3 Production alternative — Cloud SQL

```bash
gcloud sql instances create litellm-pg --database-version=POSTGRES_15 \
  --tier=db-custom-1-3840 --region=$REGION --network=inference-vpc \
  --no-assign-ip --project $CENTRAL_PROJECT
gcloud sql databases create litellm --instance=litellm-pg --project $CENTRAL_PROJECT
```

---

## 7. The LiteLLM gateway VM

### 7.1 Service account and IAM

```bash
gcloud iam service-accounts create litellm-gw-sa --project $CENTRAL_PROJECT

export SA=litellm-gw-sa@$CENTRAL_PROJECT.iam.gserviceaccount.com

for R in roles/aiplatform.user roles/secretmanager.secretAccessor \
         roles/monitoring.metricWriter roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding $CENTRAL_PROJECT \
    --member="serviceAccount:$SA" --role="$R"
done
```

### 7.2 Create the VM

```bash
gcloud compute addresses create litellm-ip --region=$REGION --project $CENTRAL_PROJECT

gcloud compute instances create litellm-gw \
  --zone=$ZONE --machine-type=e2-standard-4 \
  --network=inference-vpc --subnet=gw-subnet \
  --address=litellm-ip \
  --tags=litellm-gw \
  --service-account=$SA --scopes=cloud-platform \
  --image-family=debian-12 --image-project=debian-cloud \
  --project $CENTRAL_PROJECT
```

> [!NOTE]
> If your organization enforces `constraints/compute.requireShieldedVm`, add
> `--shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring`. If it enforces
> `constraints/compute.vmExternalIpAccess`, drop `--address` and add `--no-address`, then
> reach the UI over an IAP tunnel (section 7.6).

### 7.3 Install LiteLLM

```bash
gcloud compute ssh litellm-gw --project $CENTRAL_PROJECT --zone=$ZONE --tunnel-through-iap
```

Then on the VM:

```bash
sudo apt-get update
sudo apt-get install -y python3-pip nodejs npm
sudo pip3 install --break-system-packages \
  'litellm[proxy]' prisma google-auth google-cloud-aiplatform
sudo -H prisma generate \
  --schema /usr/local/lib/python3.11/dist-packages/litellm/proxy/schema.prisma
```

> [!CAUTION]
> **All four of those extra packages are required and none are pulled in by
> `litellm[proxy]`.** Without `prisma`, LiteLLM dies at startup with
> `ModuleNotFoundError: No module named 'prisma'`. Without `google-auth` and
> `google-cloud-aiplatform`, every Vertex call fails. `prisma generate` shells out to
> `npm`, so Node must be installed *first*. Debian 12 enforces PEP 668, hence
> `--break-system-packages`.
>
> Because the service uses `Restart=always`, a missing dependency shows up as a service
> that reports **`active`** while silently crash-looping and never binding `:4000`.

### 7.4 Configuration — `/etc/litellm/config.yaml`

```yaml
model_list:
  - model_name: serverless-gemini
    litellm_params:
      model: vertex_ai/gemini-2.5-flash-lite
      vertex_project: "<CENTRAL_PROJECT_NUMBER>"
      vertex_location: "us-central1"

  - model_name: selfhosted-gemma
    litellm_params:
      model: vertex_ai/gemma/<ENDPOINT_ID>
      api_base: "https://<DEDICATED_ENDPOINT_DNS>/v1/projects/<CENTRAL_PROJECT_NUMBER>/locations/<REGION>/endpoints/<ENDPOINT_ID>"
      vertex_project: "<CENTRAL_PROJECT_NUMBER>"
      vertex_location: "<REGION>"

  - model_name: gke-gemma
    litellm_params:
      model: openai/google/gemma-3-1b-it
      api_base: "http://<INTERNAL_LB_IP>/v1"
      api_key: "none"

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: os.environ/DATABASE_URL
  store_model_in_db: true
```

> [!IMPORTANT]
> The `selfhosted-gemma` `api_base` is the part most likely to be wrong. Three rules:
> 1. Use the **`dedicatedEndpointDns`** from section 4.3 verbatim. It embeds a Google
>    tenant project number that will not match yours — never construct this by hand.
> 2. Use the project **number**, not the project ID, in both the path and `vertex_project`.
> 3. **Do not append `:predict`.** LiteLLM adds the suffix itself.

### 7.5 Run as a systemd service

Write the secrets to a root-only environment file rather than inlining them in the unit:

```bash
MASTER=$(gcloud secrets versions access latest --secret=litellm-master-key)
DBPW=$(gcloud secrets versions access latest --secret=litellm-db-password)
UIPW=$(gcloud secrets versions access latest --secret=litellm-ui-password)

sudo install -m 0600 /dev/null /etc/litellm/env
sudo tee /etc/litellm/env >/dev/null <<EOF
LITELLM_MASTER_KEY=$MASTER
DATABASE_URL=postgresql://litellm:$DBPW@localhost:5432/litellm
UI_USERNAME=admin
UI_PASSWORD=$UIPW
EOF
```

`/etc/systemd/system/litellm.service`:

```ini
[Unit]
Description=LiteLLM Gateway
After=network.target postgresql.service

[Service]
EnvironmentFile=/etc/litellm/env
ExecStart=/usr/local/bin/litellm --config /etc/litellm/config.yaml --port 4000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now litellm

# Verify it is genuinely serving, not just "active"
sudo ss -lntp | grep 4000 || sudo journalctl -u litellm -n 50 --no-pager
```

### 7.6 Admin UI

Browse to `http://<VM_EXTERNAL_IP>:4000/ui` and log in as `admin`.

If the VM has no external IP, tunnel from your laptop:

```bash
gcloud compute ssh litellm-gw --project $CENTRAL_PROJECT --zone=$ZONE \
  --tunnel-through-iap -- -L 4000:localhost:4000
# then browse to http://localhost:4000/ui
```

### 7.7 Smoke-test all three backends

```bash
GW=http://<VM_EXTERNAL_IP>:4000

for M in serverless-gemini selfhosted-gemma gke-gemma; do
  echo "== $M =="
  curl -s $GW/v1/chat/completions \
    -H "Authorization: Bearer $MASTER" -H "Content-Type: application/json" \
    -d "{\"model\":\"$M\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}"
  echo
done
```

---

## 8. Cross-project consumer access

### 8.1 Issue a scoped virtual key

```bash
curl -s http://<VM_EXTERNAL_IP>:4000/key/generate \
  -H "Authorization: Bearer $MASTER" -H "Content-Type: application/json" \
  -d '{"models":["serverless-gemini","selfhosted-gemma","gke-gemma"],"max_budget":50,"key_alias":"my-app"}'
```

The response's `key` field is shown **once** — LiteLLM only stores a hash. Save it.

> [!NOTE]
> The `models` array is an **authorization allowlist**, not a registration. A model name
> that isn't in it will be rejected at call time even if the gateway serves it. Conversely,
> `/v1/models` echoes this allowlist, so it can list models the gateway can't actually
> route — use `/model/info` to see what is genuinely registered.

### 8.2 Call from the consumer project

```bash
curl -s http://<VM_EXTERNAL_IP>:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-<VIRTUAL_KEY>" -H "Content-Type: application/json" \
  -d '{"model":"serverless-gemini","messages":[{"role":"user","content":"Which backend am I hitting?"}]}'
```

### 8.3 Private path via VPC peering

Preferred over the external IP.

**First, make sure the consumer project actually has a VPC.** Organizations commonly enforce
`constraints/compute.skipDefaultNetworkCreation`, in which case a new project has *no*
network at all and there is no `default` to peer with:

```bash
gcloud compute networks list --project $CONSUMER_PROJECT     # empty? create one below
```

```bash
gcloud compute networks create app-vpc --subnet-mode=custom \
  --project $CONSUMER_PROJECT

gcloud compute networks subnets create app-subnet \
  --network=app-vpc --region=$REGION \
  --range=10.20.0.0/24 --enable-private-ip-google-access \
  --project $CONSUMER_PROJECT
```

> [!IMPORTANT]
> `10.20.0.0/24` must not overlap the central `10.10.0.0/24`. Peering across overlapping
> CIDRs is rejected outright, and this is the most common reason a consumer cannot reach
> the gateway privately.

Peering is not one-sided — create it in both directions:

```bash
gcloud compute networks peerings create to-consumer \
  --network=inference-vpc --peer-project=$CONSUMER_PROJECT --peer-network=app-vpc \
  --project=$CENTRAL_PROJECT

gcloud compute networks peerings create to-central \
  --network=app-vpc --peer-project=$CENTRAL_PROJECT --peer-network=inference-vpc \
  --project=$CONSUMER_PROJECT

gcloud compute networks peerings list --project=$CENTRAL_PROJECT \
  --format="value(peerings[].name,peerings[].state)"     # expect ACTIVE
```

Then widen the gateway firewall to admit the consumer's subnet:

```bash
gcloud compute firewall-rules update allow-litellm \
  --project=$CENTRAL_PROJECT \
  --source-ranges=10.10.0.0/24,10.20.0.0/24,$ADMIN_IP/32
```

---

## Traffic Generation

[`generate_gemini_traffic.py`](./generate_gemini_traffic.py) fires randomized prompts at the
**gateway**, rotating across all three registered models, so Cloud Monitoring, the Admin UI,
quota dashboards, and billing views have data spanning every backend. It uses the same path a
real consumer uses — one endpoint, a virtual key, a model name — so no Google credentials are
needed. Only the Python standard library is required.

```bash
export LITELLM_API_KEY=sk-...        # a virtual key from section 8.1

# 60 requests split evenly across the three models
python generate_gemini_traffic.py --gateway http://<GATEWAY_IP>:4000 \
  --requests 60 --concurrency 5

# Sustained load for 10 minutes at ~2 req/s
python generate_gemini_traffic.py --gateway http://<GATEWAY_IP>:4000 \
  --duration 600 --qps 2 --concurrency 8

# One backend only
python generate_gemini_traffic.py --models gke-gemma --requests 20
```

| Flag | Purpose |
| :--- | :--- |
| `--gateway URL` | Gateway base URL (default `http://localhost:4000`) |
| `--api-key KEY` | Virtual key, or set `LITELLM_API_KEY` |
| `--models A B C` | Models to rotate across (default: all three) |
| `--requests N` | Fixed number of calls |
| `--duration S` / `--qps R` | Sustained load for S seconds at R req/s |
| `--concurrency N` | Parallel in-flight requests |
| `--max-tokens N` | Response cap per request |

Requests are assigned round-robin so each backend gets an equal share, and the summary prints
a per-model breakdown of successes, failures, p50/p95 latency, and token counts — a direct
comparison of the three deployment types under identical prompts:

```
  Per-model breakdown:
    model                  ok  fail      p50      p95       in      out
    -------------------------------------------------------------------
    gke-gemma               3     0    0.82s    2.60s      110      374
    selfhosted-gemma        3     0    0.97s    2.72s      108      356
    serverless-gemini       3     0    1.03s    1.43s       78      438
```

If the gateway has no external IP, run this from a peered consumer VM, or open an IAP tunnel
and leave `--gateway` at its default:

```bash
gcloud compute ssh litellm-gw --project $CENTRAL_PROJECT --zone $ZONE \
  --tunnel-through-iap -- -N -L 4000:localhost:4000
```

---

## Security Model

How a consumer request stays safe without the consumer holding a Google credential:

1. Consumer app holds only a LiteLLM **virtual key** (`sk-...`), scoped to named models.
2. Request reaches `:4000` over VPC peering; the firewall admits only known ranges.
3. LiteLLM validates the key hash against Postgres and enforces budget and rate limits.
4. The gateway calls Vertex AI as **its own service account**, via metadata-server tokens.
5. Identity never crosses the project boundary; the consumer cannot call Vertex directly.
6. Spend is attributed per key and persisted for chargeback.

### Known gaps in this build

| Gap | Impact | Fix |
| :--- | :--- | :--- |
| Consumer → gateway is plain HTTP | Keys sent in cleartext | Internal HTTPS LB or nginx/TLS |
| Admin UI on a public IP | Exposed if firewall widens | IAP tunnel only; drop the external IP |
| GKE vLLM Service is unauthenticated | Anything in-VPC bypasses LiteLLM entirely | NetworkPolicy, or require an auth header |
| `hugging_face.token` stored in plaintext | Credential leak | Move to Secret Manager; gitignore and rotate |
| Placeholder secrets | Total compromise | Generate real values before exposing :4000 |

---

## Monitoring

Add the consumer project to the central project's **metrics scope** so both appear in one
view:

```bash
gcloud beta monitoring metrics-scopes create \
  projects/$CONSUMER_PROJECT --project=$CENTRAL_PROJECT
```

| Backend | Metric source | Key metrics |
| :--- | :--- | :--- |
| Serverless | `aiplatform.googleapis.com/publisher/online_serving/*` | requests, latency, tokens, errors |
| Self-deployed | `aiplatform.googleapis.com/prediction/online/*` | latency, replicas, `accelerator/duty_cycle` |
| GKE vLLM | `prometheus.googleapis.com/vllm:*` | e2e latency, TTFT, tokens/sec, queue, KV-cache |

The gateway is the only place that sees **every** request in a uniform shape with per-key
attribution. Beyond the Admin UI's Usage & Logs view:

- `GET /spend/logs` and `GET /global/spend/report` — per-request and aggregated spend
- `/metrics` — Prometheus endpoint, scrapeable by Managed Prometheus
- `journalctl -u litellm -f` — live request and error logs

---

## Troubleshooting

| Symptom | Cause |
| :--- | :--- |
| `invalid_grant` / `invalid_rapt` | ADC expired — `gcloud auth application-default login` |
| `does not have permission to access users instance` | Active gcloud account ≠ ADC account; pass `--account` |
| `The resource 'projects/.../litellm-gw' was not found` | Missing `--project` on the gcloud command |
| Service `active` but nothing on `:4000` | Crash loop masked by `Restart=always` — check `journalctl` |
| `ModuleNotFoundError: No module named 'prisma'` | Missing pip packages (section 7.3) |
| `Target 'bin' directory does not exist` | `prisma generate` ran without Node installed |
| `No module named 'google'` | Missing `google-auth` / `google-cloud-aiplatform` |
| `PERMISSION_DENIED: Cloud Quotas API` | Enable `cloudquotas.googleapis.com` |
| Model listed by `/v1/models` but 400s on call | That endpoint echoes the key allowlist — check `/model/info` |
| `404` on the self-deployed endpoint | `api_base` rebuilt by hand, or `:predict` appended |
| `403` calling a cross-project endpoint | Gateway SA needs `roles/aiplatform.user` on that project |
| Consumer can't reach the gateway privately | Peering absent, or overlapping CIDRs |
| Vertex endpoint 404 on Gemini 3.x | Use `location="global"` |

---

## Teardown

> [!CAUTION]
> The two L4 GPUs bill continuously. Nothing tracks what you created, so work through this
> list deliberately — an orphaned endpoint or Autopilot cluster is easy to forget.

```bash
# 1. Self-deployed endpoint (undeploy the model first, then delete the endpoint)
gcloud ai endpoints list --region=$REGION --project=$CENTRAL_PROJECT
gcloud ai endpoints undeploy-model <EP_ID> --deployed-model-id=<DM_ID> \
  --region=$REGION --project=$CENTRAL_PROJECT
gcloud ai endpoints delete <EP_ID> --region=$REGION --project=$CENTRAL_PROJECT

# 2. GKE
gcloud container clusters delete gke-inference --region=$REGION --project=$CENTRAL_PROJECT

# 3. Gateway VM and its static IP
gcloud compute instances delete litellm-gw --zone=$ZONE --project=$CENTRAL_PROJECT
gcloud compute addresses delete litellm-ip --region=$REGION --project=$CENTRAL_PROJECT

# 4. Peering (both sides)
gcloud compute networks peerings delete to-central \
  --network=default --project=$CONSUMER_PROJECT
gcloud compute networks peerings delete to-consumer \
  --network=inference-vpc --project=$CENTRAL_PROJECT

# 5. Networking
gcloud compute routers nats delete inference-nat --router=inference-router \
  --region=$REGION --project=$CENTRAL_PROJECT
gcloud compute routers delete inference-router --region=$REGION --project=$CENTRAL_PROJECT
gcloud compute firewall-rules delete allow-litellm allow-iap-ssh --project=$CENTRAL_PROJECT
gcloud compute networks subnets delete gw-subnet --region=$REGION --project=$CENTRAL_PROJECT
gcloud compute networks delete inference-vpc --project=$CENTRAL_PROJECT

# 6. Secrets
gcloud secrets delete litellm-master-key  --project=$CENTRAL_PROJECT
gcloud secrets delete litellm-db-password --project=$CENTRAL_PROJECT
gcloud secrets delete litellm-ui-password --project=$CENTRAL_PROJECT
```

Verify nothing GPU-backed survives:

```bash
gcloud ai endpoints list --region=$REGION --project=$CENTRAL_PROJECT
gcloud container clusters list --project=$CENTRAL_PROJECT
```

---

## Design Decisions

| Decision | Rationale |
| :--- | :--- |
| LiteLLM over direct Vertex calls | One OpenAI-compatible surface; per-app keys, budgets, and spend that Vertex alone doesn't give you |
| Postgres required | Virtual keys, budgets, spend, and the Admin UI all persist here — without it the UI has nowhere to write |
| `store_model_in_db: true` | Models can be added from the UI at runtime without redeploying the VM |
| Three backends, one gateway | Lets you compare cost and latency of managed vs. self-deployed vs. self-operated serving behind an unchanged client |
| Gateway calls Vertex as its own SA | Consumers never hold Google credentials; identity stops at the project boundary |
| External IP on the gateway | Demo convenience for the Admin UI. Production posture is an internal LB with no public IP |
