#!/usr/bin/env python3
"""Deploy the AskHR agent to Vertex AI Agent Engine with full telemetry enabled."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path
current_dir = Path(__file__).resolve().parent
project_root = str(current_dir.parent if current_dir.name == "askhr_oauth" else current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import dotenv_values

# Explicitly load askhr_oauth/.env first
env_path = current_dir / ".env" if (current_dir / ".env").exists() else Path(project_root) / "askhr_oauth" / ".env"
local_env = dotenv_values(env_path) if env_path.exists() else {}

# Apply local env values to process environment
for k, v in local_env.items():
    if v is not None:
        os.environ[k] = str(v)

import vertexai
from google.cloud import aiplatform
from vertexai import agent_engines

try:
    from vertexai.preview.reasoning_engines import AdkApp
except ImportError:
    from vertexai.agent_engines import AdkApp  # type: ignore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
logger = logging.getLogger("deploy_askhr_agent")

PACKAGE_DIR = "askhr_oauth"


def load_requirements() -> list[str]:
    """Read requirements.txt from the askhr_oauth package directory."""
    req_path = current_dir / "requirements.txt" if (current_dir / "requirements.txt").exists() else Path(project_root) / "askhr_oauth" / "requirements.txt"
    if req_path.exists():
        lines = [
            line.strip()
            for line in req_path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if lines:
            logger.info("Loaded %d requirements from %s", len(lines), req_path)
            return lines

    return [
        "google-cloud-discoveryengine",
        "google-api-python-client",
        "google-adk>=2.4.0",
        "google-cloud-aiplatform[adk,agent_engines]>=1.126.1",
        "requests",
        "python-dotenv",
        "opentelemetry-exporter-gcp-trace",
        "opentelemetry-sdk",
        "opentelemetry-instrumentation-grpc",
        "opentelemetry-instrumentation-requests",
        "google-cloud-trace",
        "cloudpickle==3.1.2",
        "pydantic",
    ]


def build_app() -> AdkApp:
    """Import the ADK root agent and wrap it as a deployable AdkApp with tracing enabled."""
    try:
        from askhr_oauth.agent import root_agent
    except ImportError:
        from agent import root_agent  # type: ignore

    from google.adk.sessions.in_memory_session_service import InMemorySessionService

    logger.info("Loaded root_agent: %s", getattr(root_agent, "name", root_agent))
    return AdkApp(
        agent=root_agent,
        session_service_builder=InMemorySessionService,
        enable_tracing=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy AskHR to Agent Engine with Agent Gateway attachment.")
    parser.add_argument(
        "--agent-id",
        default=os.getenv("AGENT_ID"),
        help="Existing engine id or full resource name to update in place.",
    )
    parser.add_argument(
        "--display-name",
        default=os.getenv("AGENT_DISPLAY_NAME", "NewAskHR"),
        help="Display name for the deployment.",
    )
    parser.add_argument(
        "--agent-gateway",
        default=os.getenv(
            "AGENT_GATEWAY",
            "projects/bold-kit-384717/locations/us-central1/agentGateways/agent-gateway",
        ),
        help="Network Services Agent Gateway resource name.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    project = os.getenv("GOOGLE_CLOUD_PROJECT", "bold-kit-384717")
    deployment_location = os.getenv("DEPLOYMENT_LOCATION", "us-central1")

    staging_bucket = os.getenv("STAGING_BUCKET", "gs://adk-staging-bold-kit-384717")
    if not staging_bucket.startswith("gs://"):
        staging_bucket = f"gs://{staging_bucket}"

    logger.info("Project=%s  Location=%s  Bucket=%s", project, deployment_location, staging_bucket)
    logger.info("Attaching to Agent Gateway: %s", args.agent_gateway)

    import subprocess
    import google.auth
    import google.auth.credentials

    class GcloudCliCredentials(google.auth.credentials.Credentials):
        def __init__(self):
            super().__init__()
            self.refresh(None)

        def refresh(self, request):
            self.token = subprocess.check_output(["gcloud", "auth", "print-access-token"]).decode().strip()

        @property
        def valid(self):
            return bool(self.token)

        @property
        def expired(self):
            return False

    creds = GcloudCliCredentials()
    google.auth.default = lambda *args, **kwargs: (creds, project)

    aiplatform.init(project=project, location=deployment_location, staging_bucket=staging_bucket, credentials=creds)
    vertexai.init(project=project, location=deployment_location, staging_bucket=staging_bucket, credentials=creds)

    client = vertexai.Client(
        project=project,
        location=deployment_location,
        credentials=creds,
        http_options=dict(api_version="v1beta1"),
    )

    app = build_app()
    requirements = load_requirements()

    os.chdir(project_root)

    extra_packages = [
        "askhr_oauth",
        "installation_scripts/create_venv.sh",
    ]

    model_name = os.getenv("MODEL", "gemini-2.5-flash")

    env_vars = {
        "MODEL": model_name,
        "GOOGLE_GENAI_USE_VERTEXAI": "true",
        "GOOGLE_GENAI_USE_ENTERPRISE": "1",
        "AUTH_ID": os.getenv("AUTH_ID", "askhrauth_1"),
        "EMPLOYEE_API_URL": os.getenv("EMPLOYEE_API_URL", "https://employee-gateway-ave1ebyp.uc.gateway.dev"),
        "AGENT_REGISTRY_ENDPOINT_ID": os.getenv("AGENT_REGISTRY_ENDPOINT_ID", "agentregistry-00000000-0000-0000-277e-b688845989e8"),
        "VERTEX_SEARCH_APP_ID": os.getenv("VERTEX_SEARCH_APP_ID", "askhr2_1774835344122"),
        "VERTEX_SEARCH_LOCATION": os.getenv("VERTEX_SEARCH_LOCATION", "global"),
        "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
        "GOOGLE_CLOUD_TRACING_ENABLE": "true",
        "GOOGLE_CLOUD_TRACING_DEBUG": "true",
        "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true",
        "GOOGLE_CLOUD_LOCATION": "global",
        "DEPLOYMENT_LOCATION": "us-central1",
    }
    logger.info("Deploying with environment variables (Telemetry enabled): %s", env_vars)

    description = "AskHR Agent deployed on Agent Engine, attached to Agent Gateway, and registered in Agent Registry."

    deploy_config = {
        "staging_bucket": staging_bucket,
        "requirements": requirements,
        "extra_packages": extra_packages,
        "build_options": {
            "installation_scripts": [
                "installation_scripts/create_venv.sh",
            ],
        },
        "env_vars": env_vars,
        "display_name": args.display_name,
        "description": description,
        "identity_type": "AGENT_IDENTITY",
        "agent_gateway_config": {
            "agent_to_anywhere_config": {
                "agent_gateway": args.agent_gateway,
            }
        },
    }

    engine = None
    action = "Created"

    if args.agent_id:
        resource_name = args.agent_id
        if not resource_name.startswith("projects/"):
            resource_name = f"projects/{project}/locations/{deployment_location}/reasoningEngines/{args.agent_id}"
        logger.info("Attempting to update existing agent engine: %s", resource_name)
        try:
            engine = client.agent_engines.update(
                name=resource_name,
                agent=app,
                config=deploy_config,
            )
            action = "Updated"
        except Exception as e:
            logger.warning("Could not update %s in place (%s). Bootstrapping new AGENT_IDENTITY engine...", resource_name, e)
            engine = None

    if engine is None:
        logger.info("Step 1: Creating identity-only agent shell with AGENT_IDENTITY...")
        empty_config = {
            "display_name": args.display_name,
            "description": description,
            "identity_type": "AGENT_IDENTITY",
        }
        empty_engine = client.agent_engines.create(config=empty_config)
        reasoning_engine_name = empty_engine.api_resource.name
        logger.info("Identity shell created: %s", reasoning_engine_name)

        logger.info("Step 2: Updating reasoning engine %s with application code and Agent Gateway config...", reasoning_engine_name)
        engine = client.agent_engines.update(
            name=reasoning_engine_name,
            agent=app,
            config=deploy_config,
        )
        action = "Created"

    resource_name = engine.api_resource.name
    logger.info("Successfully %s agent engine: %s", action, resource_name)
    print("\n" + "=" * 60)
    print(f"DEPLOYMENT COMPLETE: {resource_name}")
    print(f"ATTACHED AGENT GATEWAY: {args.agent_gateway}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
