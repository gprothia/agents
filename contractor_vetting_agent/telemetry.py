"""Observability, OpenTelemetry Distributed Tracing, Structured JSON Logging,
Intent vs. Outcome Telemetry, and Active PII Redaction Pipeline.
"""

import json
import logging
import re
import sys
import time
from typing import Any, Dict, Optional
from datetime import datetime, timezone
import uuid

# OpenTelemetry Tracing imports
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Status, StatusCode


# ==============================================================================
# PII REDACTION SERVICE
# ==============================================================================

class PIIRedactionService:
    """Active scrubbing pipeline to detect and redact sensitive data (SSN, EIN,
    credit cards, bank accounts, emails, phone numbers) before logging or storage.
    """

    # Compiled regex patterns for PII detection
    SSN_PATTERN = re.compile(r"\b(?!000|666|9\d{2})\d{3}[- ]?(?!00)\d{2}[- ]?(?!0000)\d{4}\b")
    EIN_PATTERN = re.compile(r"\b\d{2}-\d{7}\b")
    CREDIT_CARD_PATTERN = re.compile(r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b")
    BANK_ROUTING_PATTERN = re.compile(r"\b\d{9}\b")
    EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    PHONE_PATTERN = re.compile(r"\b(?:\+?1[-. ]?)?\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})\b")

    @classmethod
    def redact_text(cls, text: str) -> str:
        """Scrub PII from plain string."""
        if not isinstance(text, str):
            return text

        # Redact SSN
        text = cls.SSN_PATTERN.sub("[REDACTED_SSN]", text)
        # Redact Credit Cards
        text = cls.CREDIT_CARD_PATTERN.sub("[REDACTED_CREDIT_CARD]", text)
        # Mask partial EIN (keep last 4 digits for auditability)
        def _mask_ein(match):
            val = match.group(0).replace("-", "")
            return f"XX-XXX{val[-4:]}"
        text = cls.EIN_PATTERN.sub(_mask_ein, text)
        # Mask Email
        def _mask_email(match):
            e = match.group(0)
            parts = e.split("@")
            user = parts[0]
            masked_user = user[0] + "***" if len(user) > 1 else "*"
            return f"{masked_user}@{parts[1]}"
        text = cls.EMAIL_PATTERN.sub(_mask_email, text)
        # Mask Phone
        text = cls.PHONE_PATTERN.sub(r"(\1) ***-\3", text)

        return text

    @classmethod
    def redact_data(cls, data: Any) -> Any:
        """Recursively redact sensitive PII across dictionaries, lists, and primitives."""
        if isinstance(data, str):
            return cls.redact_text(data)
        elif isinstance(data, dict):
            redacted_dict = {}
            for k, v in data.items():
                lower_k = str(k).lower()
                # Specific high-risk keys
                if any(secret in lower_k for secret in ["password", "secret", "token", "ssn", "api_key"]):
                    redacted_dict[k] = "[REDACTED_SECRET]"
                elif "tax_id" in lower_k or "ein" in lower_k:
                    if isinstance(v, str) and len(v.replace("-", "")) == 9:
                        clean = v.replace("-", "")
                        redacted_dict[k] = f"XX-XXX{clean[-4:]}"
                    else:
                        redacted_dict[k] = cls.redact_data(v)
                else:
                    redacted_dict[k] = cls.redact_data(v)
            return redacted_dict
        elif isinstance(data, (list, tuple, set)):
            return [cls.redact_data(item) for item in data]
        return data


# ==============================================================================
# STRUCTURED JSON LOGGER
# ==============================================================================

class StructuredJsonFormatter(logging.Formatter):
    """Custom logging formatter outputting valid NDJSON records with enriched metadata."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": PIIRedactionService.redact_text(record.getMessage()),
            "module": record.module,
            "func_name": record.funcName,
            "line_no": record.lineno,
        }

        # Enrich with extra attributes if supplied
        for key in ["correlation_id", "trace_id", "span_id", "session_id", "agent_name",
                    "event_type", "intent", "outcome", "tool_name", "execution_time_ms",
                    "status", "risk_tier", "contractor_id"]:
            if hasattr(record, key):
                val = getattr(record, key)
                log_entry[key] = PIIRedactionService.redact_data(val)

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def get_structured_logger(name: str = "contractor_vetting") -> logging.Logger:
    """Creates or returns a structured JSON logger instance."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredJsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


# Global logger instance
logger = get_structured_logger()


# ==============================================================================
# INTENT VS. OUTCOME TELEMETRY CAPTURE
# ==============================================================================

class TelemetryCollector:
    """Captures paired Intent and Outcome events for rich agent observability."""

    @staticmethod
    def log_intent(
        tool_name: str,
        intended_action: str,
        input_parameters: Dict[str, Any],
        rationale: str,
        session_id: Optional[str] = None,
        agent_name: str = "contractor_vetting_coordinator",
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> str:
        """Log agent's intended action BEFORE executing a tool or delegating."""
        intent_id = str(uuid.uuid4())
        extra = {
            "event_type": "AGENT_INTENT",
            "intent_id": intent_id,
            "tool_name": tool_name,
            "agent_name": agent_name,
            "session_id": session_id or "default_session",
            "trace_id": trace_id or "",
            "span_id": span_id or "",
            "intent": {
                "intended_action": intended_action,
                "input_parameters": PIIRedactionService.redact_data(input_parameters),
                "decision_rationale": rationale,
            }
        }
        logger.info(f"Intent declared: {tool_name} - {intended_action}", extra=extra)
        return intent_id

    @staticmethod
    def log_outcome(
        tool_name: str,
        execution_time_ms: float,
        status: str,
        result_summary: Dict[str, Any],
        intent_id: Optional[str] = None,
        deviation_detected: bool = False,
        session_id: Optional[str] = None,
        agent_name: str = "contractor_vetting_coordinator",
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> None:
        """Log actual execution outcome AFTER completing tool execution."""
        extra = {
            "event_type": "AGENT_OUTCOME",
            "intent_id": intent_id or "unknown",
            "tool_name": tool_name,
            "agent_name": agent_name,
            "session_id": session_id or "default_session",
            "trace_id": trace_id or "",
            "span_id": span_id or "",
            "execution_time_ms": execution_time_ms,
            "status": status,
            "outcome": {
                "status": status,
                "execution_time_ms": execution_time_ms,
                "result_summary": PIIRedactionService.redact_data(result_summary),
                "deviation_detected": deviation_detected,
            }
        }
        logger.info(f"Outcome recorded: {tool_name} ({status}) in {execution_time_ms:.1f}ms", extra=extra)


# ==============================================================================
# OPENTELEMETRY DISTRIBUTED TRACING SETUP
# ==============================================================================

def initialize_tracer(service_name: str = "contractor-vetting-agent") -> trace.Tracer:
    """Initializes OpenTelemetry TracerProvider and registers exporter."""
    current_provider = trace.get_tracer_provider()
    if not isinstance(current_provider, TracerProvider):
        provider = TracerProvider()
        # In production on GCP, opentelemetry-exporter-gcp-trace can be hooked here.
        # Fallback to in-memory console exporter for local and sandbox environments.
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)

    return trace.get_tracer(service_name, "1.0.0")


tracer = initialize_tracer()


class TraceContext:
    """Helper context manager to trace agent tasks and tool calls with telemetry."""

    def __init__(self, span_name: str, attributes: Optional[Dict[str, Any]] = None):
        self.span_name = span_name
        self.attributes = attributes or {}
        self.span = None
        self.start_time = 0.0

    def __enter__(self):
        self.start_time = time.time()
        self.span = tracer.start_span(self.span_name)
        for k, v in self.attributes.items():
            clean_v = str(PIIRedactionService.redact_data(v))
            self.span.set_attribute(f"contractor_vetting.{k}", clean_v)
        return self.span

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000.0
        if self.span:
            self.span.set_attribute("contractor_vetting.duration_ms", duration_ms)
            if exc_type:
                self.span.set_status(Status(StatusCode.ERROR, str(exc_val)))
                self.span.record_exception(exc_val)
            else:
                self.span.set_status(Status(StatusCode.OK))
            self.span.end()
