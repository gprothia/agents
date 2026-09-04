# Playbook: Encryption (CMEK vs Google-managed)

topic: encryption
source_url: https://docs.cloud.google.com/gemini/enterprise/docs/cmek
terraform_resource: google_discovery_engine_cmek_config

## What this decision is
Whether Gemini Enterprise data is encrypted with your own Cloud KMS keys (CMEK) or with
Google-managed keys (GMEK). This is a one-way door once a key is applied.

## Questions to ask
- encryption: how should data be encrypted? [cmek | gmek]

## Choices, pros and cons
### encryption = cmek (customer-managed)
- pros: You control the keys; meets strict key-control requirements; supports third-party connectors.
- cons (one-way / watch-outs):
  - A CMEK key applied to an app or data connector cannot be swapped.
  - All data connectors in an app must share the same CMEK configuration.
  - First-party connectors are NOT CMEK-compliant except import-once/periodic BigQuery & Cloud Storage.
  - Third-party connectors need single-region keys.
  - Cloud KMS is billed continuously once a key is registered.
### encryption = gmek (Google-managed)
- pros: Simplest; nothing to manage; reversible-friendly for pilots.
- cons: You do not hold the keys; cannot later move THIS project to CMEK without a rebuild.

## Prerequisites for CMEK
- Create a multi-region symmetric Cloud KMS key.
- Grant roles/cloudkms.cryptoKeyEncrypterDecrypter to the Cloud Storage service agent
  and the Discovery Engine service agent on the key.
- Register the key BEFORE creating any apps/data connectors you want it to protect.

## Registration API
UpdateCmekConfig (PATCH) on the project's cmekConfigs.
  PATCH https://{us|eu|}discoveryengine.googleapis.com/v1/projects/PROJECT/locations/LOCATION/cmekConfigs/default
Verify: cmekConfigs.get -> state == ACTIVE.

## Terraform mapping
resource: google_discovery_engine_cmek_config
key fields: cmek_config_id, location, kms_key (full KMS key resource name), set_default
