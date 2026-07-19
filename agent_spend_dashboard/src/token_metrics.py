"""
token_metrics.py
Retrieves LLM token usage for Agent Engine runs from Cloud Logging.

How token data gets into Cloud Logging:
  Option A – ADK OpenTelemetry (recommended):
      In your agent: agent_engines.AdkApp(agent=..., enable_tracing=True)
      Spans include attributes: gen_ai.usage.input_tokens / output_tokens
      These land in Cloud Logging under the ReasoningEngine resource.

  Option B – Vertex AI Data Access audit logs (if enabled in IAM > Audit Logs):
      Each GenerateContent call is logged with usageMetadata.

The code tries both structures and aggregates what it finds.
If no token data is found, data_available=False is returned so the UI
can prompt the user to enable tracing.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# Max log entries to scan (to avoid runaway costs on very busy agents)
_MAX_LOG_ENTRIES = 5_000


def get_token_metrics(
    project_id: str,
    location: str,
    engine_id: str,
    start: datetime,
    end: datetime,
) -> dict:
    """
    Scan Cloud Logging for LLM token usage linked to a specific Agent Engine.

    Returns:
        input_tokens    – int, total input/prompt tokens
        output_tokens   – int, total output/completion tokens
        thinking_tokens – int, total thinking tokens (Gemini 2.5 Flash / 2.0 Thinking)
        by_model        – { model_id: { input, output, thinking } }
        data_available  – bool, False means no token logs were found
        entries_scanned – int, number of log entries examined
    """
    from google.cloud import bigquery

    client = bigquery.Client(project=project_id)

    if isinstance(start, str):
        try:
            start = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except Exception:
            start = datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if isinstance(end, str):
        try:
            end = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except Exception:
            end = datetime.strptime(end, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    # Build parameterized query to safely and efficiently fetch token usage from traces
    query = f"""
    SELECT
      start_time,
      COALESCE(SAFE_CAST(JSON_VALUE(attributes, '$."gen_ai.usage.input_tokens"') AS INT64), 0) as input_tokens,
      COALESCE(SAFE_CAST(JSON_VALUE(attributes, '$."gen_ai.usage.output_tokens"') AS INT64), 0) AS output_tokens,
      COALESCE(SAFE_CAST(JSON_VALUE(attributes, '$."gen_ai.usage.thinking_tokens"') AS INT64), 0) AS thinking_tokens,
      JSON_VALUE(attributes, '$."gen_ai.request.model"') as model_id
    FROM
      `{project_id}`.`trace_dataset`.`_AllSpans`
    WHERE
      JSON_VALUE(attributes, '$."gen_ai.operation.name"') = 'generate_content'
      AND JSON_VALUE(attributes, '$."gen_ai.request.model"') IS NOT NULL
      AND ENDS_WITH(JSON_VALUE(resource.attributes, '$."cloud.resource_id"'), @engine_suffix)
      AND start_time >= @start_time
      AND start_time <= @end_time
    GROUP BY 1, 2, 3, 4, 5
    ORDER BY 1 DESC
    """

    engine_suffix = f"locations/{location}/reasoningEngines/{engine_id}"
    print(engine_suffix)
    print(start)
    print(end)

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("engine_suffix", "STRING", engine_suffix),
            bigquery.ScalarQueryParameter("start_time", "TIMESTAMP", start),
            bigquery.ScalarQueryParameter("end_time", "TIMESTAMP", end),
        ]
    )

    totals = {"input": 0, "output": 0, "thinking": 0}
    by_model: dict[str, dict] = {}
    data_available = False
    entries_scanned = 0
    print(query)
    

    try:
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()

        for row in results:
            entries_scanned += 1
            inp = row.get("input_tokens") or 0
            out = row.get("output_tokens") or 0
            thinking = row.get("thinking_tokens") or 0
            model = row.get("model_id") or "unknown"

            if inp > 0 or out > 0 or thinking > 0:
                data_available = True
                totals["input"]    += inp
                totals["output"]   += out
                totals["thinking"] += thinking

                if model not in by_model:
                    by_model[model] = {"input": 0, "output": 0, "thinking": 0}
                by_model[model]["input"]    += inp
                by_model[model]["output"]   += out
                by_model[model]["thinking"] += thinking

    except Exception as exc:
        print(exc)
        log.warning("BigQuery trace query failed for engine %s: %s", engine_id, exc)

    return {
        "input_tokens":    totals["input"],
        "output_tokens":   totals["output"],
        "thinking_tokens": totals["thinking"],
        "by_model":        by_model,
        "data_available":  data_available,
        "entries_scanned": entries_scanned,
    }


def _extract_tokens(payload: dict) -> tuple[int, int, int, str]:
    """
    Try every known payload structure and return (input, output, thinking, model).
    Returns (0, 0, 0, 'unknown') if nothing is found.
    """
    inp = out = thinking = 0
    model = "unknown"

    # ── Structure 1: OpenTelemetry GenAI semantic conventions ──────────────
    # These appear when ADK is configured with enable_tracing=True and the
    # OpenTelemetry Cloud Logging exporter is active.
    # jsonPayload.attributes: { "gen_ai.usage.input_tokens": 100, ... }
    attrs = payload.get("attributes", {})
    if isinstance(attrs, dict) and attrs:
        inp      = int(attrs.get("gen_ai.usage.input_tokens",  0))
        out      = int(attrs.get("gen_ai.usage.output_tokens", 0))
        thinking = int(attrs.get("gen_ai.usage.thinking_tokens", 0))
        model    = str(attrs.get("gen_ai.request.model", "unknown"))

    # ── Structure 2: Flat token fields ─────────────────────────────────────
    if inp == 0 and out == 0:
        inp      = int(payload.get("inputTokenCount",  payload.get("input_token_count", 0)))
        out      = int(payload.get("outputTokenCount", payload.get("output_token_count", 0)))
        thinking = int(payload.get("thinkingTokenCount", 0))
        model    = str(payload.get("model", payload.get("modelId", "unknown")))

    # ── Structure 3: usageMetadata (Vertex AI audit log response payload) ──
    if inp == 0 and out == 0:
        usage = payload.get("usageMetadata", payload.get("usage", {}))
        if isinstance(usage, dict):
            inp      = int(usage.get("promptTokenCount",     usage.get("inputTokenCount", 0)))
            out      = int(usage.get("candidatesTokenCount", usage.get("outputTokenCount", 0)))
            thinking = int(usage.get("cachedContentTokenCount", 0))  # closest proxy

    # ── Structure 4: Nested response.usageMetadata ─────────────────────────
    if inp == 0 and out == 0:
        resp  = payload.get("response", {})
        usage = resp.get("usageMetadata", {}) if isinstance(resp, dict) else {}
        if isinstance(usage, dict):
            inp      = int(usage.get("promptTokenCount",     0))
            out      = int(usage.get("candidatesTokenCount", 0))
            thinking = int(usage.get("thinkingTokenCount",   0))
            # model may be in the request part
            req   = payload.get("request", {})
            model = str(req.get("model", "unknown")) if isinstance(req, dict) else "unknown"

    return inp, out, thinking, model
