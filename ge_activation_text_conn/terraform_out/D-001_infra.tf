terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 7.7.0"
    }
  }
}

provider "google" {
  project               = var.project_id
  user_project_override = true
  billing_project       = var.project_id
}

variable "project_id" { type = string }


# Decision D-001: Region eu + CMEK
# Source: https://docs.cloud.google.com/gemini/enterprise/docs/cmek
# One-way: a registered CMEK key cannot be swapped; register BEFORE creating data connectors.
resource "google_discovery_engine_cmek_config" "default" {
  cmek_config_id = "default"
  location       = "eu"
  kms_key        = var.kms_key
  set_default    = true
}

variable "kms_key" {
  type        = string
  description = "Full Cloud KMS key resource name (multi-region symmetric key)."
  default     = "projects/PROJECT_ID/locations/europe/keyRings/ge/cryptoKeys/gemini-enterprise"
}
