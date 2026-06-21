export GOOGLE_CLOUD_PROJECT="bold-kit-384717"
export AUTH_LOCATION="global"
export AUTH_ID="askhrauth_1"

curl -X DELETE \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "X-Goog-User-Project: ${GOOGLE_CLOUD_PROJECT}" \
  "https://global-discoveryengine.googleapis.com/v1alpha/projects/${GOOGLE_CLOUD_PROJECT}/locations/global/authorizations/${AUTH_ID}"