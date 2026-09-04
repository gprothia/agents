export GATEWAY=136-110-168-31.nip.io
export ADMIN_UI=https://34-120-181-249.nip.io
export API_KEY=Ajgecy11ZvrX9N6qGK9uzsN7VAfMkkOP1XzYsUEQSwpekG7B

curl -s https://$GATEWAY/v1/health

# 2.1 Google Gemini 2.5 Flash (Vertex AI)
curl -sk -X POST https://$GATEWAY/v1/chat/completions \
  -H "x-api-key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"gemini-3.6-flash","messages":[{"role":"user","content":"In one sentence: what is FNV-1a hash?"}],"max_tokens":8000}' | jq

# 2.2 Anthropic Claude Sonnet 4.6 — strong reasoning, allowed in demo
curl -sk -X POST https://$GATEWAY/v1/chat/completions \
  -H "x-api-key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":"In one sentence: what is FNV-1a hash?"}],"max_tokens":800}' | jq

# 2.3 Premium model is BLOCKED — shows the allowlist guardrail in action
curl -sk -X POST https://$GATEWAY/v1/chat/completions \
  -H "x-api-key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"grok-4.20-reasoning","messages":[{"role":"user","content":"hi"}],"max_tokens":800}' | jq .
# → {"error":{"code":"model_not_allowed","source":"gateway",...}}

# 2.4 ZhipuAI GLM-4.7 (MaaS partner)
curl -sk -X POST https://$GATEWAY/v1/chat/completions \
  -H "x-api-key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"glm-4.7","messages":[{"role":"user","content":"In one sentence: what is FNV-1a hash?"}],"max_tokens":800}' | jq '.choices[0].message.content'

# 2.5 OpenCode Zen — totally free, no GCP cost, no token quota
curl -sk -X POST https://$GATEWAY/v1/chat/completions \
  -H "x-api-key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"opencode/big-pickle","messages":[{"role":"user","content":"In one sentence: what is FNV-1a hash?"}],"max_tokens":800}' | jq '.choices[0].message.content'

curl -sk -X POST https://$GATEWAY/v1/chat/completions \
  -H "x-api-key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-v4-flash",
    "messages": [
      {"role": "user", "content": "Explain what is Raft consensus algorithm in one sentence."}
    ],
    "max_tokens": 5000
  }' | jq