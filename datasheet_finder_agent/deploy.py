#!/usr/bin/env python3
"""Deploy ComponentIQ Datasheet Finder agent to Vertex AI Agent Engine."""

import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
import vertexai
from vertexai import agent_engines
try:
    from vertexai.preview.reasoning_engines import AdkApp
except ImportError:
    from vertexai.agent_engines import AdkApp  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
logger = logging.getLogger("deploy_datasheet_agent")

PACKAGE_DIR = "datasheet_finder_agent"

REQUIREMENTS = [
    "google-adk>=2.4.0",
    "google-cloud-aiplatform[adk,agent_engines]>=1.126.1",
    "python-dotenv",
    "requests"
]

def main() -> None:
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)

    project = os.getenv("GCP_PROJECT", "bold-kit-384717")
    location = os.getenv("GCP_LOCATION", "us-central1")
    staging_bucket = os.getenv("STAGING_BUCKET", "gs://adk-staging-bold-kit-384717")

    if not staging_bucket.startswith("gs://"):
        staging_bucket = f"gs://{staging_bucket}"

    logger.info("Initializing Vertex AI (project=%s, location=%s, bucket=%s)", project, location, staging_bucket)
    vertexai.init(project=project, location=location, staging_bucket=staging_bucket)

    from datasheet_finder_agent.agent import root_agent

    logger.info("Loaded root_agent: %s", getattr(root_agent, "name", root_agent))
    app = AdkApp(agent=root_agent, enable_tracing=True)

    env_vars = {
        "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
        "GOOGLE_CLOUD_TRACING_ENABLE": "true",
        "GOOGLE_CLOUD_TRACING_DEBUG": "true",
        "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"
    }

    logger.info("Creating Agent Engine instance for ComponentIQ...")
    remote_app = agent_engines.create(
        agent_engine=app,
        requirements=REQUIREMENTS,
        extra_packages=[PACKAGE_DIR],
        display_name="ComponentIQ Datasheet Finder Agent",
        env_vars=env_vars,
    )

    resource_name = getattr(remote_app, "resource_name", remote_app)
    logger.info("🎉 Successfully deployed Agent Engine: %s", resource_name)
    print(f"DEPLOYMENT_RESOURCE={resource_name}")

if __name__ == "__main__":
    main()
