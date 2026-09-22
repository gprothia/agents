# Playbook: Connector — Gmail (first-party Google Workspace)

topic: connector_gmail
source_url: https://docs.cloud.google.com/gemini/enterprise/docs/connectors/gmail/set-up-data-store
terraform_resource: google_discovery_engine_data_connector

## What this decision is
Connect Gmail as a first-party data source so Gemini Enterprise can search and summarize
mail — and, with actions enabled, draft/send/reply on the user's behalf. Gmail is a
Google Workspace connector, not a generic third-party one.

## Prerequisites (the agent must guide the admin through these BEFORE setup)
- Google Workspace only. GE connects Gmail via your Workspace customer ID.
  Personal @gmail.com accounts have no customer ID and are NOT supported.
- Turn ON "Smart features in Google Workspace" AND "Smart features in other Google products".
- Allowlist the Google-managed OAuth app the Gmail data store uses (Workspace admin), if
  your org restricts OAuth app access.
- Configure your identity provider (Google Identity / GSUITE) so ACLs are enforced.
- For actions (send/reply/download): a Google Cloud + Workspace admin completes the OAuth
  2.0 consent once; after authentication the configured actions work in the agent UI.

## Questions to ask
- scope: whose mail? (this POC: all_users, domain-wide via Workspace customer ID)
- index_what: messages only, or messages + attachments?
- actions: read-only, or enable actions (send / reply / draft / download attachment)?
- sync: how often should mail sync? [continuous | daily]

## Choices, pros and cons
### actions = read_only
- pros: Lowest risk; search & summarize mail; no per-user write consent.
- cons: The assistant cannot send, reply, or draft.
### actions = with_actions  (send / reply / draft / download)
- pros: The assistant can act on email end-to-end inside GE.
- cons (watch-outs):
  - Requires a one-time admin OAuth 2.0 consent for the connector.
  - Write actions act as the user — review the enabled action list carefully.
  - Broaden scopes only as needed.

### index_what = messages + attachments
- pros: Attachment content becomes searchable.
- cons: Larger index; attachment size limits apply.

## Key implications (state these plainly)
- ACL-aware: users only see mail they already have access to; access is enforced through
  your identity provider. For an all-users setup this is the main safeguard.
- Encryption is only configurable when the connector location is "us" or "eu" (choose
  Google-managed or Cloud KMS). This DEPENDS on the infrastructure decision — do region +
  encryption first. First-party Gmail data uses Google-managed keys unless a supported
  CMEK path is configured.
- Sync keeps the data store updated; a full sync replaces the store's contents.

## Terraform mapping (verified)
Use google_discovery_engine_data_connector (the data_store resource's workspace_config
block is not yet in the HCL provider). The connector manages first-party sources like
google_mail. Actions become live after the admin completes the OAuth consent.
key fields: location (from infra decision), data_source = "google_mail",
  entities (messages [, attachments]), refresh_interval, action config for send/reply/draft.
Identity: google_discovery_engine_acl_config with idp_config { idp_type = "GSUITE" }.
