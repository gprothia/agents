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


# Decision D-002: App: "Employee Assistant"
# Source: https://docs.cloud.google.com/gemini/enterprise/docs/quickstart-gemini-enterprise
resource "google_discovery_engine_search_engine" "employee_assistant" {
  engine_id         = "employee_assistant"
  collection_id     = "default_collection"
  location          = var.location
  display_name      = "Employee Assistant"
  industry_vertical = "GENERIC"
  data_store_ids    = var.data_store_ids  # attach your data stores

  search_engine_config {
    search_tier = "SEARCH_TIER_ENTERPRISE"
  }
  # app_type resolves to APP_TYPE_INTRANET for Gemini Enterprise
  common_config {
    company_name = "Employee Assistant"
  }
}

variable "location"       { type = string, default = "global" }
variable "data_store_ids" { type = list(string), default = [] }
