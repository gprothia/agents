unset GOOGLE_APPLICATION_CREDENTIALS
adk run ./askhr_oauth --state "{\"askhrauth_1\": \"$(gcloud auth print-access-token)\"}"
