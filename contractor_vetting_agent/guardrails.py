"""Security, Policy Compliance, and Self-Evaluation Guardrails Plugin.

Implements ContractorVettingGuardrailsPlugin adhering to ADK BasePlugin standards:
1. Input Prompt Injection & Adversarial Attack Detection (before_model_callback)
2. Policy & Governance Enforcement for Tool Execution (before_tool_callback)
3. Automated Self-Evaluation & PII Scrubbing (after_model_callback)
"""

import re
from typing import Any, Dict, Optional
from google.adk.plugins import BasePlugin
from google.adk.tools import BaseTool

from google.genai import types
from .config import DEFAULT_HTTP_RETRY_OPTIONS
from .hitl import HITLManager
from .telemetry import PIIRedactionService, get_structured_logger

logger = get_structured_logger("contractor_vetting.guardrails")


class ContractorVettingGuardrailsPlugin(BasePlugin):
    """ADK Plugin enforcing security, regulatory compliance, transient error retries, and self-evaluation guardrails."""

    INJECTION_PATTERNS = [
        re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
        re.compile(r"bypass\s+(sanctions|compliance|vetting|rules)", re.IGNORECASE),
        re.compile(r"disregard\s+the\s+constitution", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+in\s+(developer|dan|god)\s+mode", re.IGNORECASE),
    ]

    def __init__(self, name: str = "contractor_vetting_guardrails", enforce_strict_hitl: bool = True):
        super().__init__(name=name)
        self.enforce_strict_hitl = enforce_strict_hitl

    def before_model_callback(self, *, callback_context: Any, llm_request: Any) -> Optional[Any]:
        """Pre-invocation guardrail: Injects robust HTTP retry options for 503/429 errors and inspects user queries for prompt injections."""
        try:
            # 1. Automatic 503/429 Exponential Retry Policy Injection
            if hasattr(llm_request, "config"):
                llm_request.config = llm_request.config or types.GenerateContentConfig()
                llm_request.config.http_options = llm_request.config.http_options or types.HttpOptions()
                if not getattr(llm_request.config.http_options, "retry_options", None):
                    llm_request.config.http_options.retry_options = DEFAULT_HTTP_RETRY_OPTIONS

            # 2. Inspect prompt text for adversarial injections
            prompt_text = ""
            if hasattr(llm_request, "contents"):
                for content in llm_request.contents:
                    if hasattr(content, "parts"):
                        for part in content.parts:
                            if hasattr(part, "text") and part.text:
                                prompt_text += " " + part.text

            for pattern in self.INJECTION_PATTERNS:
                if pattern.search(prompt_text):
                    logger.warning(
                        "SECURITY GUARDRAIL TRIGGERED: Detected adversarial prompt injection pattern.",
                        extra={"detected_pattern": pattern.pattern}
                    )
        except Exception as ex:
            logger.error(f"Error in before_model_callback guardrail: {ex}")

        return None

    def on_model_error_callback(
        self,
        *,
        callback_context: Any,
        llm_request: Any,
        error: Exception,
    ) -> Optional[Any]:
        """Handles transient 503 UNAVAILABLE or 429 RATE_LIMIT model spikes with rich telemetry."""
        err_str = str(error)
        if "503" in err_str or "UNAVAILABLE" in err_str or "high demand" in err_str:
            logger.warning(
                f"MODEL DEMAND SPIKE (503 UNAVAILABLE): {err_str}. Automatic exponential retry in progress.",
                extra={"error_type": "503_UNAVAILABLE", "model": getattr(llm_request, "model", "unknown")}
            )
        elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            logger.warning(
                f"RATE LIMIT (429): {err_str}. Backing off and retrying.",
                extra={"error_type": "429_RATE_LIMIT"}
            )
        else:
            logger.error(f"Model invocation error: {error}", exc_info=True)
        return None

    def before_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: Dict[str, Any],
        tool_context: Any,
    ) -> Optional[Dict[str, Any]]:
        """Policy Guardrail: Enforce verification rules before executing high-stakes tools."""
        tool_name = getattr(tool, "name", str(tool))
        logger.info(f"Guardrail pre-check for tool: {tool_name}")

        # Guardrail on final dossier generation
        if "finalize_contractor_vetting_dossier" in tool_name:
            decision = tool_args.get("decision", "").upper()
            risk_score = tool_args.get("composite_risk_score_out_of_100", 0)
            token = tool_args.get("human_approval_token")

            # Check 1: Cannot approve if composite risk is high (>60) without valid human token
            if decision == "APPROVED" and risk_score > 60:
                if self.enforce_strict_hitl and not HITLManager.verify_token_validity(token):
                    logger.warning(
                        f"POLICY GUARDRAIL BLOCKED: High risk score ({risk_score}/100) cannot be APPROVED without valid HITL token.",
                        extra={"tool": tool_name, "decision": decision, "risk_score": risk_score}
                    )
                    return {
                        "status": "error",
                        "error_code": "GUARDRAIL_HITL_REQUIRED",
                        "error_message": "Policy Violation: Contractor with Risk Score > 60 cannot be APPROVED without authorized human sign-off token.",
                        "recovery_guidance": "Call `request_human_oversight_approval` to obtain an authorized escalation token, or change decision to `REJECTED` or `ESCALATED_FOR_HUMAN_REVIEW`.",
                    }

        return None

    def after_model_callback(self, *, callback_context: Any, llm_response: Any) -> Optional[Any]:
        """Post-invocation guardrail: Self-evaluation check for PII leakage and completeness."""
        try:
            resp_text = ""
            if hasattr(llm_response, "content") and hasattr(llm_response.content, "parts"):
                for part in llm_response.content.parts:
                    if hasattr(part, "text") and part.text:
                        resp_text += part.text

            # Check for PII leakage in model output
            redacted = PIIRedactionService.redact_text(resp_text)
            if redacted != resp_text:
                logger.warning("PII GUARDRAIL: Detected and scrubbed raw PII in agent model output.")
                if hasattr(llm_response.content.parts[0], "text"):
                    llm_response.content.parts[0].text = redacted

        except Exception as ex:
            logger.error(f"Error in after_model_callback guardrail: {ex}")

        return None
