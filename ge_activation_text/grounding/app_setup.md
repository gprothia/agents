# Playbook: App setup (Gemini Enterprise "engine")

topic: app_setup
source_url: https://docs.cloud.google.com/gemini/enterprise/docs/quickstart-gemini-enterprise
terraform_resource: google_discovery_engine_search_engine

## What this decision is
A Gemini Enterprise "app" is an engine (`app_type = APP_TYPE_INTRANET`) that a defined
group of users interacts with, backed by one or more data stores. You decide who the app
is for and what it does before creating it.

## Questions to ask
- audience: who will use this first app? [all_employees | specific_team]
- capability: what should it do? [search_summarize | actions]
- app_name: a display name (default: "Employee Assistant")

## Choices, pros and cons
### Audience = all_employees
- pros: Fastest path to broad value; one simple permission scope.
- cons: You can't scope actions narrowly; everyone shares the same access.
### Audience = specific_team
- pros: Tight, least-privilege scope; safe for apps that take actions.
- cons: Narrower value; you'll create more apps as you expand.

### Capability = search_summarize
- pros: Read-only; lowest risk; no per-user OAuth needed.
- cons: Cannot create tickets, send mail, etc.
### Capability = actions
- pros: The app can act in connected systems (e.g. create a Jira issue).
- cons: Requires connector actions + per-user OAuth; not recommended for an all-employee app.

## Recommended default
One app, "Employee Assistant", for all_employees, search_summarize, actions off.
Add action-enabled apps per team later. This is the fastest safe path to first value.

## Implications
- An app is an engine with `app_type = APP_TYPE_INTRANET`.
- Enabling actions later means adding a separate app or a per-team scope, not flipping a switch.

## Terraform mapping
resource: google_discovery_engine_search_engine
key fields: engine_id, collection_id (default_collection), display_name,
  data_store_ids, search_engine_config, app_type=APP_TYPE_INTRANET
