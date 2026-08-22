output "project_id" {
  description = "The target Google Cloud Project ID."
  value       = var.project_id
}

output "staging_bucket_url" {
  description = "GCS Staging Bucket URL for ADK deployments."
  value       = "gs://${google_storage_bucket.adk_staging.name}"
}

output "service_account_email" {
  description = "Dedicated Service Account email for Contractor Vetting Agent."
  value       = google_service_account.agent_service_account.email
}

output "sam_gov_secret_id" {
  description = "Secret Manager secret ID for SAM.gov API."
  value       = google_secret_manager_secret.sam_gov_api_key.secret_id
}
