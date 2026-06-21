#!/usr/bin/env python3
"""
Deploy the AskHR agent to Vertex AI Agent Engine.

Behavior:
    - If an agent id is provided (via --agent-id or the AGENT_ID env var),
      the existing deployment is UPDATED in place.
    - If no agent id is provided, a NEW Agent Engine is CREATED.

Usage:
    python deploy_agent.py                       # create new (no id)
    python deploy_agent.py --agent-id 1234567890 # update existing
    AGENT_ID=1234567890 python deploy_agent.py   # update via env var

Config is read from the environment (e.g. a .env file):
    GOOGLE_CLOUD_PROJECT      required  - GCP project id
    DEPLOYMENT_LOCATION       optional  - region (default: us-central1)
    STAGING_BUCKET            required  - gs://... bucket for staging
    AGENT_DISPLAY_NAME        optional  - display name for the deployment
    AGENT_ID                  optional  - existing engine id -> triggers update

NOTE ON SDK VERSIONS:
    The Agent Engine SDK surface has moved around across releases. The two
    spots most likely to differ in your installed version are flagged with
    "VERIFY" comments below: the AdkApp import path and the create/update
    keyword (`agent_engine=`). Confirm them against your installed
    google-cloud-aiplatform before relying on this in CI.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path to make askhr_oauth package importable
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv

import vertexai
from vertexai import agent_engines

# VERIFY: import path for AdkApp differs by SDK version. Try the common ones.
try:
    from vertexai.preview.reasoning_engines import AdkApp
except ImportError:  # pragma: no cover - newer/older layouts
    from vertexai.agent_engines import AdkApp  # type: ignore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
logger = logging.getLogger("deploy_agent")

# Directory of the agent package that must be bundled with the deployment.
# Adjust if your root_agent lives elsewhere.
PACKAGE_DIR = "askhr_oauth"

# Default requirements if no requirements.txt is found next to this script.
DEFAULT_REQUIREMENTS = [
    "google-adk>=1.27.4",
    "google-cloud-aiplatform[adk,agent_engines]",
    "google-cloud-discoveryengine",
    "python-dotenv",
    "requests",
]


def load_requirements() -> list[str]:
    """Read requirements.txt from the package directory, next to this script, or fall back to defaults."""
    # First check package directory (askhr_oauth)
    req_path = Path(__file__).parent.parent / PACKAGE_DIR / "requirements.txt"
    if not req_path.exists():
        # Fall back to next to the script
        req_path = Path(__file__).parent / "requirements.txt"
        
    if req_path.exists():
        lines = [
            line.strip()
            for line in req_path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if lines:
            logger.info("Loaded %d requirements from %s", len(lines), req_path)
            return lines
    logger.info("Using built-in default requirements")
    return DEFAULT_REQUIREMENTS


def build_app() -> AdkApp:
    """Import the ADK root agent and wrap it as a deployable AdkApp."""
    # Import here (not at module top) so config/env is loaded first and any
    # import error surfaces with a clear message.
    try:
        from askhr_oauth.agent import root_agent
    except ImportError:
        # Fallback if run from inside the package directory.
        from agent import root_agent  # type: ignore

    logger.info("Loaded root_agent: %s", getattr(root_agent, "name", root_agent))
    return AdkApp(agent=root_agent, enable_tracing=True)


def full_resource_name(agent_id: str, project: str, location: str) -> str:
    """Accept either a bare engine id or a full resource path and normalize it."""
    if agent_id.startswith("projects/"):
        return agent_id
    return (
        f"projects/{project}/locations/{location}/reasoningEngines/{agent_id}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy AskHR to Agent Engine.")
    parser.add_argument(
        "--agent-id",
        default=os.getenv("AGENT_ID"),
        help="Existing engine id or full resource name. If omitted, a new "
        "engine is created.",
    )
    parser.add_argument(
        "--display-name",
        default=os.getenv("AGENT_DISPLAY_NAME", "AskHR Agent"),
        help="Display name for the deployment.",
    )
    return parser.parse_args()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        logger.error("Missing required environment variable: %s", name)
        sys.exit(1)
    return value


def main() -> None:
    load_dotenv()
    args = parse_args()

    project = require_env("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("DEPLOYMENT_LOCATION", "us-central1")
    staging_bucket = require_env("STAGING_BUCKET")
    if not staging_bucket.startswith("gs://"):
        staging_bucket = f"gs://{staging_bucket}"

    logger.info("Project=%s  Location=%s  Bucket=%s", project, location, staging_bucket)

    vertexai.init(project=project, location=location, staging_bucket=staging_bucket)

    app = build_app()
    requirements = load_requirements()
    extra_packages = [PACKAGE_DIR]

    if args.agent_id:
        resource_name = full_resource_name(args.agent_id, project, location)
        logger.info("Updating existing agent: %s", resource_name)
        # VERIFY: keyword is `agent_engine=` in current SDK; older builds used
        # `reasoning_engine=`. Swap if your version complains.
        remote_app = agent_engines.update(
            resource_name=resource_name,
            agent_engine=app,
            requirements=requirements,
            extra_packages=extra_packages,
            display_name=args.display_name,
        )
        action = "Updated"
    else:
        logger.info("No agent id provided - creating a new agent.")
        remote_app = agent_engines.create(
            agent_engine=app,
            requirements=requirements,
            extra_packages=extra_packages,
            display_name=args.display_name,
        )
        action = "Created"

    resource_name = getattr(remote_app, "resource_name", remote_app)
    logger.info("%s agent engine: %s", action, resource_name)
    print(resource_name)


if __name__ == "__main__":
    main()
