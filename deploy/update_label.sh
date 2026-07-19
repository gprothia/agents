PROJECT_ID=bold-kit-384717
LOCATION=us-central1
RESOURCE_ID=6709543758863532032          # the numeric ID from the Agent Engine page

cat > labels.json <<'EOF'
{ "labels": { "agent": "askhr" } }
EOF

curl -X PATCH \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -d @labels.json \
  "https://${LOCATION}-aiplatform.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION}/reasoningEngines/${RESOURCE_ID}?update_mask=labels"