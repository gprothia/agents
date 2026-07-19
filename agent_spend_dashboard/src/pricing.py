"""
Pricing configuration for Vertex AI Agent Engine and Gemini models.
All prices are in USD. Update from: https://cloud.google.com/vertex-ai/pricing
"""

# ── Agent Engine Compute Pricing ──────────────────────────────────────────────
COMPUTE_PRICING = {
    "vcpu_per_hour":   0.00994,   # USD per vCPU-hour
    "memory_per_hour": 0.01050,   # USD per GiB-hour
}

# ── Gemini Model Token Pricing (per 1M tokens) ────────────────────────────────
MODEL_PRICING = {
    "gemini-2.5-pro": {
        "input":    1.25,
        "output":  10.00,
        "thinking": 3.50,   # thinking tokens (billed as input for 2.5 Pro)
    },
    "gemini-2.5-flash": {
        "input":    0.15,
        "output":   0.60,
        "thinking": 3.50,
    },
    "gemini-2.0-flash": {
        "input":    0.10,
        "output":   0.40,
        "thinking": 0.00,   # no thinking mode
    },
    "gemini-2.0-flash-thinking": {
        "input":    3.50,
        "output":  10.00,
        "thinking":10.00,
    },
    "gemini-1.5-pro": {
        "input":    1.25,
        "output":   5.00,
        "thinking": 0.00,
    },
    "gemini-1.5-flash": {
        "input":    0.075,
        "output":   0.30,
        "thinking": 0.00,
    },
    "unknown": {
        "input":    0.10,   # default to flash pricing if model unknown
        "output":   0.40,
        "thinking": 0.00,
    },
}

# Helper: resolve a raw model string to a key in MODEL_PRICING
def resolve_model_key(model_str: str) -> str:
    model_str = (model_str or "").lower()
    for key in MODEL_PRICING:
        if key in model_str:
            return key
    return "unknown"


def calculate_costs(metrics: dict, token_data: dict, model: str = "gemini-2.0-flash") -> dict:
    """
    Given raw metric values and token counts, return a full cost breakdown dict.

    metrics keys expected:
        cpu_seconds         – total vCPU-seconds consumed
        memory_gb_seconds   – total GiB-seconds consumed

    token_data keys expected:
        input_tokens
        output_tokens
        thinking_tokens
        by_model            – {model_id: {input, output, thinking}}
    """
    # ── Compute costs ──────────────────────────────────────────────────────
    cpu_hours    = metrics.get("cpu_seconds", 0) / 3600
    memory_hours = metrics.get("memory_gb_seconds", 0) / 3600

    cpu_cost    = cpu_hours    * COMPUTE_PRICING["vcpu_per_hour"]
    memory_cost = memory_hours * COMPUTE_PRICING["memory_per_hour"]

    # ── Token costs per model ──────────────────────────────────────────────
    by_model_costs = {}
    total_input_cost    = 0.0
    total_output_cost   = 0.0
    total_thinking_cost = 0.0

    by_model = token_data.get("by_model", {})

    if by_model:
        for model_id, tok in by_model.items():
            key    = resolve_model_key(model_id)
            prices = MODEL_PRICING[key]

            inp_cost  = (tok.get("input", 0)    / 1_000_000) * prices["input"]
            out_cost  = (tok.get("output", 0)   / 1_000_000) * prices["output"]
            thnk_cost = (tok.get("thinking", 0) / 1_000_000) * prices["thinking"]

            by_model_costs[model_id] = {
                "input_tokens":    tok.get("input", 0),
                "output_tokens":   tok.get("output", 0),
                "thinking_tokens": tok.get("thinking", 0),
                "input_cost":      inp_cost,
                "output_cost":     out_cost,
                "thinking_cost":   thnk_cost,
                "model_total":     inp_cost + out_cost + thnk_cost,
                "prices":          prices,
            }
            total_input_cost    += inp_cost
            total_output_cost   += out_cost
            total_thinking_cost += thnk_cost
    else:
        # Fallback: aggregate totals with the selected default model
        key    = resolve_model_key(model)
        prices = MODEL_PRICING[key]
        total_input_cost    = (token_data.get("input_tokens", 0)    / 1_000_000) * prices["input"]
        total_output_cost   = (token_data.get("output_tokens", 0)   / 1_000_000) * prices["output"]
        total_thinking_cost = (token_data.get("thinking_tokens", 0) / 1_000_000) * prices["thinking"]

    token_cost = total_input_cost + total_output_cost + total_thinking_cost
    total_cost = cpu_cost + memory_cost + token_cost

    return {
        # compute
        "cpu_hours":    cpu_hours,
        "memory_hours": memory_hours,
        "cpu_cost":     cpu_cost,
        "memory_cost":  memory_cost,
        # tokens
        "input_token_cost":    total_input_cost,
        "output_token_cost":   total_output_cost,
        "thinking_token_cost": total_thinking_cost,
        "token_cost":          token_cost,
        # per-model detail
        "by_model_costs": by_model_costs,
        # totals
        "compute_cost": cpu_cost + memory_cost,
        "total":        total_cost,
    }
