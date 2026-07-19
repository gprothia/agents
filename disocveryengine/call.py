from google.cloud import discoveryengine_v1 as de

PROJECT_ID = "bold-kit-384717"
LOCATION = "global"          # or "us" / "eu"
APP_ID = "gemini-enterprise-17617673_1761767394641"            # the Gemini Enterprise app jira2 is attached to
DATA_STORE_ID = "jira2_1773439103980_project"      # exact ID attached to the engine

client = de.SearchServiceClient()

serving_config = (
    f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/"
    f"default_collection/engines/{APP_ID}/servingConfigs/default_serving_config"
)

request = de.SearchRequest(
    serving_config=serving_config,
    query="show everything assigned to me",
    page_size=10,
    data_store_specs=[
        de.SearchRequest.DataStoreSpec(
            data_store=(
                f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/"
                f"default_collection/dataStores/{DATA_STORE_ID}"
            )
        )
    ],
    content_search_spec=de.SearchRequest.ContentSearchSpec(
        snippet_spec=de.SearchRequest.ContentSearchSpec.SnippetSpec(return_snippet=True),
    ),
)
result = client.search(request)
print(result)
for result in client.search(request):
    print(result.document.name)
    print(result.document.derived_struct_data)
