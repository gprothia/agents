#!/usr/bin/env python3
"""Deploy GE Activation Agent to Vertex AI Agent Engine (Reasoning Engine).

Deploys the ADK App to Google Cloud Vertex AI in project bold-kit-384717,
with Cloud Tracing and telemetry enabled.
"""

import logging
import os
import sys
from pathlib import Path

# Ensure clean ADC authentication
if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ and not os.path.exists(os.environ["GOOGLE_APPLICATION_CREDENTIALS"]):
    del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]

# Add project root to sys.path
current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from dotenv import load_dotenv
import vertexai
from vertexai import agent_engines

try:
    from vertexai.preview.reasoning_engines import AdkApp
except ImportError:
    from vertexai.agent_engines import AdkApp  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
logger = logging.getLogger("deploy_ge_activation_agent")

PACKAGE_DIR = "ge_agent"

import google.adk

REQUIREMENTS = [
    f"google-adk=={getattr(google.adk, '__version__', '1.14.1')}",
    "google-cloud-aiplatform[adk,agent_engines]>=1.126.1",
    "cloudpickle==3.1.2",
    "openpyxl>=3.1.5",
    "python-dotenv>=1.0.0",
    "pydantic",
]


def main() -> None:
    env_path = current_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    project = os.getenv("GOOGLE_CLOUD_PROJECT", os.getenv("GCP_PROJECT", "bold-kit-384717"))
    location = os.getenv("GOOGLE_CLOUD_LOCATION", os.getenv("GCP_LOCATION", "us-central1"))
    staging_bucket = os.getenv("STAGING_BUCKET", f"gs://adk-staging-{project}")

    if not staging_bucket.startswith("gs://"):
        staging_bucket = f"gs://{staging_bucket}"

    logger.info("Initializing Vertex AI (project=%s, location=%s, bucket=%s)", project, location, staging_bucket)
    vertexai.init(project=project, location=location, staging_bucket=staging_bucket)

    from ge_agent.agent import root_agent

    logger.info("Loaded root_agent: %s (Model: %s)", getattr(root_agent, "name", root_agent), getattr(root_agent, "model", "default"))
    app = AdkApp(agent=root_agent, enable_tracing=True)

    env_vars = {
        "GOOGLE_GENAI_USE_VERTEXAI": "true",
        "GCP_PROJECT": project,
        "GCP_LOCATION": location,
        "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
        "GOOGLE_CLOUD_TRACING_ENABLE": "true",
        "GOOGLE_CLOUD_TRACING_DEBUG": "true",
        "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true",
    }

    import argparse
    parser = argparse.ArgumentParser(description="Deploy or update GE Activation Agent on Vertex AI Agent Engine.")
    parser.add_argument(
        "--agent-id",
        default=os.getenv("AGENT_ID"),
        help="Existing reasoning engine ID or resource name to update in place.",
    )
    parser.add_argument(
        "--display-name",
        default=os.getenv("AGENT_DISPLAY_NAME", "GE Activation Agent"),
        help="Display name for the deployment.",
    )
    args = parser.parse_args()

    os.chdir(current_dir)
    extra_packages = [PACKAGE_DIR]

    if args.agent_id:
        resource_name = args.agent_id
        if not resource_name.startswith("projects/"):
            resource_name = f"projects/{project}/locations/{location}/reasoningEngines/{args.agent_id}"
        logger.info("Updating existing Vertex AI Agent Engine instance: %s ...", resource_name)
        remote_app = agent_engines.update(
            resource_name=resource_name,
            agent_engine=app,
            requirements=REQUIREMENTS,
            extra_packages=extra_packages,
            display_name=args.display_name,
            description="Consultant agent that plans Gemini Enterprise app and infra setup and saves decisions to the plan sheet.",
            env_vars=env_vars,
        )
        action = "Updated"
    else:
        logger.info("Creating new Vertex AI Agent Engine instance for GE Activation Agent...")
        remote_app = agent_engines.create(
            agent_engine=app,
            requirements=REQUIREMENTS,
            extra_packages=extra_packages,
            display_name=args.display_name,
            description="Consultant agent that plans Gemini Enterprise app and infra setup and saves decisions to the plan sheet.",
            env_vars=env_vars,
        )
        action = "Created"

    resource_name = getattr(remote_app, "resource_name", remote_app)
    logger.info("🎉 Successfully %s GE Activation Agent to Agent Engine: %s", action, resource_name)
    print("\n" + "=" * 70)
    print(f"DEPLOYMENT COMPLETE: {action.upper()}")
    print(f"RESOURCE_NAME: {resource_name}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
