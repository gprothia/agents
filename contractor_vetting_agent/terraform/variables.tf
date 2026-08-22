variable "project_id" {
  type        = string
  description = "The Google Cloud Project ID to provision resources in."
  default     = "bold-kit-384717"
}

variable "region" {
  type        = string
  description = "The Google Cloud region for Vertex AI and regional resources."
  default     = "us-central1"
}

variable "agent_display_name" {
  type        = string
  description = "Display name for the deployed Vertex AI Reasoning Engine / Agent Engine instance."
  default     = "Contractor Vetting Enterprise Agent"
}
