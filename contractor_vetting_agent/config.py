"""Configuration management and secure Google Cloud Secret Manager integration.

Adheres to:
- GCP Project: bold-kit-384717
- Vertex AI foundational models via ADC (no API keys)
- Strategic Model Routing (Flash for fast verification, Pro for deep synthesis)
- Secure secret injection via Secret Manager
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load local .env if present
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

# ==============================================================================
# GCP ENVIRONMENT SETTINGS
# ==============================================================================

GCP_PROJECT: str = os.getenv("GCP_PROJECT", "bold-kit-384717")
GCP_LOCATION: str = os.getenv("GCP_LOCATION", "us-central1")
STAGING_BUCKET: str = os.getenv("STAGING_BUCKET", f"gs://adk-staging-{GCP_PROJECT}")
DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(Path(__file__).resolve().parent / "vetting_records.db"))

from google.genai import types

# ==============================================================================
# STRATEGIC MODEL ROUTING CONFIGURATION
# ==============================================================================

# Fast model for rapid tool checks, document extraction, format validation
FAST_EXTRACTION_MODEL: str = os.getenv("FAST_EXTRACTION_MODEL", os.getenv("MODEL", "gemini-2.5-flash"))

# High-capability reasoning model for coordinator synthesis, policy arbitration, and dossier adjudication
DEEP_REASONING_MODEL: str = os.getenv("DEEP_REASONING_MODEL", os.getenv("MODEL", "gemini-2.5-pro"))

# Default agent model
DEFAULT_AGENT_MODEL: str = DEEP_REASONING_MODEL

# ==============================================================================
# ROBUST HTTP RETRY CONFIGURATION (503 UNAVAILABLE, 429, 500, 502, 504)
# ==============================================================================

RETRY_STATUS_CODES = [408, 429, 500, 502, 503, 504]

DEFAULT_HTTP_RETRY_OPTIONS = types.HttpRetryOptions(
    attempts=7,
    initial_delay=5.0,
    max_delay=120.0,
    exp_base=2.0,
    http_status_codes=RETRY_STATUS_CODES,
)

DEFAULT_HTTP_OPTIONS = types.HttpOptions(
    retry_options=DEFAULT_HTTP_RETRY_OPTIONS
)

DEFAULT_GENERATE_CONTENT_CONFIG = types.GenerateContentConfig(
    http_options=DEFAULT_HTTP_OPTIONS
)


# ==============================================================================
# SECURE SECRET MANAGER HELPER
# ==============================================================================

class SecretManagerHelper:
    """Secure injection helper for Google Cloud Secret Manager.

    Retrieves runtime credentials, external API keys, or compliance webhook tokens
    directly from Google Cloud Secret Manager in project bold-kit-384717 using ADC,
    avoiding hardcoded secrets in the codebase.
    """

    _client = None

    @classmethod
    def _get_client(cls):
        if cls._client is None:
            try:
                from google.cloud import secretmanager
                cls._client = secretmanager.SecretManagerServiceClient()
            except Exception:
                cls._client = False
        return cls._client

    @classmethod
    def get_secret(cls, secret_id: str, default: Optional[str] = None, version_id: str = "latest") -> Optional[str]:
        """Fetch secret payload from Secret Manager or fallback to environment."""
        # Check environment variable first (useful for local dev and CI tests)
        env_val = os.getenv(secret_id.upper())
        if env_val:
            return env_val

        client = cls._get_client()
        if client:
            try:
                name = f"projects/{GCP_PROJECT}/secrets/{secret_id}/versions/{version_id}"
                response = client.access_secret_version(request={"name": name})
                return response.payload.data.decode("UTF-8")
            except Exception:
                pass

        return default
