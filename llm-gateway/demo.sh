export GATEWAY=35-244-196-238.nip.io
export ADMIN_UI=https://demo-1741.1987984870407.demo.altostrat.com
export API_KEY=hE6vndiH7fy6mU6ntJpO9VeanvN8AhYGOQMQtbQzfCfIuPld

curl -sk https://$GATEWAY/v1/health

# 2.1 Google Gemini 2.5 Flash (Vertex AI)
curl -sk -X POST https://$GATEWAY/v1/chat/completions \
  -H "x-api-key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"gemini-2.5-flash-lite","messages":[{"role":"user","content":"In one sentence: what is FNV-1a hash?"}],"max_tokens":80}' | jq '.choices[0].message.content'

# 2.2 Anthropic Claude Sonnet 4.6 — strong reasoning, allowed in demo
curl -sk -X POST https://$GATEWAY/v1/chat/completions \
  -H "x-api-key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":"In one sentence: what is FNV-1a hash?"}],"max_tokens":80}' | jq '.choices[0].message.content'

# 2.3 Premium model is BLOCKED — shows the allowlist guardrail in action
curl -sk -X POST https://$GATEWAY/v1/chat/completions \
  -H "x-api-key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"grok-4.20-reasoning","messages":[{"role":"user","content":"hi"}],"max_tokens":10}' | jq .
# → {"error":{"code":"model_not_allowed","source":"gateway",...}}

# 2.4 ZhipuAI GLM-4.7 (MaaS partner)
curl -sk -X POST https://$GATEWAY/v1/chat/completions \
  -H "x-api-key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"glm-4.7","messages":[{"role":"user","content":"In one sentence: what is FNV-1a hash?"}],"max_tokens":80}' | jq '.choices[0].message.content'

# 2.5 OpenCode Zen — totally free, no GCP cost, no token quota
curl -sk -X POST https://$GATEWAY/v1/chat/completions \
  -H "x-api-key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"opencode/big-pickle","messages":[{"role":"user","content":"In one sentence: what is FNV-1a hash?"}],"max_tokens":80}' | jq '.choices[0].message.content'


# 3.1 First call — MISS expected
curl -sk -D - -X POST https://$GATEWAY/v1/chat/completions \
  -H "x-api-key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"gemini-2.5-flash-lite","messages":[{"role":"user","content":"What is the capital of Switzerland?"}],"max_tokens":50}' \
  2>/dev/null | grep -E "x-cache|x-cache-score" | head -2

# Wait 60s for Vector Search stream update
echo "Waiting 65s for cache to be populated..."; sleep 65

# 3.2 Same question — HIT (similarity = 1.0)
curl -sk -D - -X POST https://$GATEWAY/v1/chat/completions \
  -H "x-api-key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"gemini-2.5-flash-lite","messages":[{"role":"user","content":"What is the capital of Switzerland?"}],"max_tokens":50}' \
  2>/dev/null | grep -E "x-cache|x-cache-score" | head -2

# 3.3 Paraphrased — also HIT (similarity ~0.99) — this is the "semantic" part
curl -sk -D - -X POST https://$GATEWAY/v1/chat/completions \
  -H "x-api-key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"gemini-2.5-flash-lite","messages":[{"role":"user","content":"Which city is the Swiss capital?"}],"max_tokens":50}' \
  2>/dev/null | grep -E "x-cache|x-cache-score" | head -2
