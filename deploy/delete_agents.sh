
export MyProjectId="bold-kit-384717"
export MyProjectNumber="851970768145" # Used if you registered Auth with Project Number
export MyLocation="global" # Can also be 'us' or 'eu'
export MyAppId="gemini-enterprise-17617673_1761767394641" # Your Gemini Enterprise App / Engine ID
export MyAuthId="askhrauth_1" # The ID of the Authorization config to delete
export MyEndpoint="${MyLocation}-discoveryengine.googleapis.com"
export MyToken=$(gcloud auth print-access-token)


export MyAgentId="7382045066049473446"

curl -X DELETE \
  -H "Authorization: Bearer ${MyToken}" \
  "https://${MyEndpoint}/v1alpha/projects/${MyProjectId}/locations/${MyLocation}/collections/default_collection/engines/${MyAppId}/assistants/default_assistant/agents/${MyAgentId}"

