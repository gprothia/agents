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


# Decision D-003: Gmail connector → data store “gmail”
# Source: https://docs.cloud.google.com/gemini/enterprise/docs/connectors/gmail/set-up-data-store
# Prereqs (admin, one-time): Workspace customer ID; Smart features ON; OAuth app allowlisted;
#   identity provider = Google Identity; for actions, complete the OAuth consent.
resource "google_discovery_engine_data_connector" "gmail" {
  location     = "eu"
  collection_id            = "gmail-collection"
  collection_display_name  = "Gmail"
  data_source  = "google_mail"

  # First-party Workspace connector. entities: "messages", "attachments"
  params = jsonencode({
    instance_uri = "workspace"      # domain-wide via Workspace customer ID
    entities     = ["messages", "attachments"]
  })

  refresh_interval = "86400s"
  
  # Actions become active after an admin completes the one-time OAuth consent.
  action_config {
    action_params = jsonencode({ enabled_actions = ["send", "reply", "draft", "download_attachment"] })
    is_action_configured = true
  }
}

# Enforce ACLs through Google Identity so users only see mail they can access.
resource "google_discovery_engine_acl_config" "gsuite" {
  location = "eu"
  idp_config {
    idp_type = "GSUITE"
  }
}
