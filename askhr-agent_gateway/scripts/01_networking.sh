#!/usr/bin/env bash
# STEP 01 — Networking for governed egress (VPC, subnet, Cloud NAT,
# PSC-Interface network attachment that Agent Runtime uses to reach the VPC).
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
export REGION="${REGION:-us-central1}"
VPC="askhr-vpc"
SUBNET="askhr-subnet"
NETATTACH="askhr-psc-attachment"

# 1. VPC + subnet
gcloud compute networks create "$VPC" \
  --project "$PROJECT_ID" --subnet-mode=custom || true

gcloud compute networks subnets create "$SUBNET" \
  --project "$PROJECT_ID" --network "$VPC" --region "$REGION" \
  --range 10.10.0.0/24 --enable-private-ip-google-access || true

# 2. Cloud Router + NAT (lets the agent reach public *.run.app MCP endpoints
#    in the default/public-ingress variant)
gcloud compute routers create askhr-router \
  --project "$PROJECT_ID" --network "$VPC" --region "$REGION" || true

gcloud compute routers nats create askhr-nat \
  --project "$PROJECT_ID" --router askhr-router --region "$REGION" \
  --nat-all-subnet-ip-ranges --auto-allocate-nat-external-ips || true

# 3. PSC-Interface network attachment — this is what binds Agent Runtime's
#    egress into your VPC so the Agent Gateway can govern it.
gcloud compute network-attachments create "$NETATTACH" \
  --project "$PROJECT_ID" --region "$REGION" \
  --subnets "$SUBNET" \
  --connection-preference ACCEPT_AUTOMATIC || true

# 4. Baseline firewall: allow egress within VPC + to Google APIs; tighten later.
gcloud compute firewall-rules create askhr-allow-internal \
  --project "$PROJECT_ID" --network "$VPC" \
  --direction INGRESS --action ALLOW --rules tcp,udp,icmp \
  --source-ranges 10.10.0.0/24 || true

echo
echo "Network attachment (save this — used when deploying the agent runtime):"
gcloud compute network-attachments describe "$NETATTACH" \
  --project "$PROJECT_ID" --region "$REGION" --format='value(selfLink)'
