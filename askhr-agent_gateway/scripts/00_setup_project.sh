#!/usr/bin/env bash
# STEP 00 — Project setup & API enablement (run once).
set -euo pipefail

: "${PROJECT_ID:?export PROJECT_ID=<your-project> first}"
export REGION="${REGION:-us-central1}"

gcloud config set project "$PROJECT_ID"
export PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')

gcloud services enable \
  compute.googleapis.com \
  iam.googleapis.com \
  iap.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  aiplatform.googleapis.com \
  agentregistry.googleapis.com \
  networkservices.googleapis.com \
  networksecurity.googleapis.com \
  modelarmor.googleapis.com \
  dlp.googleapis.com \
  telemetry.googleapis.com \
  cloudtrace.googleapis.com \
  storage.googleapis.com \
  --project "$PROJECT_ID"

# Staging bucket for Agent Runtime deployment
gcloud storage buckets describe "gs://${PROJECT_ID}-askhr-staging" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${PROJECT_ID}-askhr-staging" \
    --location="$REGION" --uniform-bucket-level-access

echo "Project: $PROJECT_ID ($PROJECT_NUMBER)  Region: $REGION"
echo "REMINDER: Agent Gateway + Agent Runtime is private preview — your project"
echo "must be allowlisted before steps 03 and 05 will work."
