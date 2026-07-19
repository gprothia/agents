curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -H "X-Goog-User-Project: bold-kit-384717" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/851970768145/locations/global/collections/default_collection/engines/gemini-enterprise-17617673_1761767394641/servingConfigs/default_search:search" \
  -d '{
    "query": "show issues assigned to  me",
    "pageSize": 10,
    "dataStoreSpecs": [
      { "dataStore": "projects/bold-kit-384717/locations/global/collections/default_collection/dataStores/jira2_1773439103980_project" }
    ],
    "contentSearchSpec": {
      "snippetSpec": { "returnSnippet": true },
      "summarySpec": { "summaryResultCount": 5 }
    }
  }'
