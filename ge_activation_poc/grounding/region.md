# Playbook: Region and data residency

topic: region
source_url: https://docs.cloud.google.com/gemini/enterprise/docs/locations
terraform_resource: (location field on google_discovery_engine_data_store / _search_engine)

## What this decision is
The multi-region your data stores and app live in. This is effectively one-way once
data stores exist, so decide before creating them.

## Questions to ask
- residency: where must data live? [eu | us | none]

## Choices, pros and cons
### residency = eu  -> location "eu"
- pros: Meets EU data-residency requirements (GDPR).
- cons: Regional endpoint required; some global-only features may differ.
### residency = us  -> location "us"
- pros: Meets US residency; regional processing.
- cons: Not suitable if EU residency is required.
### residency = none -> location "global"
- pros: Simplest; broadest feature availability.
- cons: No residency guarantee; not acceptable under strict compliance.

## Implications (one-way)
- Region cannot be changed after data stores are created.
- The API endpoint is host `discoveryengine.googleapis.com` for global, and
  `{us|eu}-discoveryengine.googleapis.com` for regional locations.

## Terraform mapping
The chosen location is set as the `location` argument on the data store, connector,
and search engine resources (e.g. location = "eu").
