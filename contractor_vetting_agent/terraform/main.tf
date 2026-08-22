# ==============================================================================
# Terraform Infrastructure as Code for Contractor Vetting Enterprise Agent
# GCP Project: bold-kit-384717 | Region: us-central1
# ==============================================================================

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ------------------------------------------------------------------------------
# 1. Enable Required Google Cloud APIs
# ------------------------------------------------------------------------------
resource "google_project_service" "required_apis" {
  for_each = toset([
    "aiplatform.googleapis.com",       # Vertex AI & Agent Engine
    "secretmanager.googleapis.com",    # Secret Manager
    "storage.googleapis.com",          # Cloud Storage Staging
    "cloudtrace.googleapis.com",       # Cloud Trace (OpenTelemetry)
    "logging.googleapis.com",          # Structured Cloud Logging
    "dlp.googleapis.com",              # Sensitive Data Protection (DLP)
  ])

  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

# ------------------------------------------------------------------------------
# 2. Cloud Storage Staging Bucket for ADK Agent Deployments
# ------------------------------------------------------------------------------
resource "google_storage_bucket" "adk_staging" {
  name                        = "${var.project_id}-adk-contractor-vetting-staging"
  location                    = var.region
  force_destroy               = false
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.required_apis]
}

# ------------------------------------------------------------------------------
# 3. Google Cloud Secret Manager for External Integration Keys
# ------------------------------------------------------------------------------
resource "google_secret_manager_secret" "sam_gov_api_key" {
  secret_id = "sam-gov-api-key"
  project   = var.project_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.required_apis]
}

resource "google_secret_manager_secret" "dnb_direct_credentials" {
  secret_id = "dnb-direct-credentials"
  project   = var.project_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.required_apis]
}

# ------------------------------------------------------------------------------
# 4. Service Account & IAM Roles for Contractor Vetting Agent Engine
# ------------------------------------------------------------------------------
resource "google_service_account" "agent_service_account" {
  account_id   = "contractor-vetting-agent-sa"
  display_name = "Contractor Vetting ADK Agent Service Account"
  project      = var.project_id
}

resource "google_project_iam_member" "vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agent_service_account.email}"
}

resource "google_project_iam_member" "secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.agent_service_account.email}"
}

resource "google_project_iam_member" "trace_agent" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.agent_service_account.email}"
}

resource "google_project_iam_member" "log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.agent_service_account.email}"
}

resource "google_storage_bucket_iam_member" "staging_bucket_admin" {
  bucket = google_storage_bucket.adk_staging.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.agent_service_account.email}"
}
