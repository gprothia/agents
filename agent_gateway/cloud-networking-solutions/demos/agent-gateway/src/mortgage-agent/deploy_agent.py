# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Deploy the mortgage assistant agent to Vertex AI Agent Engine.

Uses the vertexai.agent_engines SDK with build_options to deploy the agent
and work around the .venv/bin/python platform bug.

The agent discovers its MCP tools at runtime by listing `mcpServers` in the
Agent Registry for `--project` / `--region`, so no per-service URL or URI
flags are needed here.

Usage:
    # Create a new agent
    python deploy_agent.py --project=PROJECT_ID --region=us-central1

    # Update an existing agent in-place
    python deploy_agent.py --project=PROJECT_ID --region=us-central1 \
        --update=projects/PROJECT/locations/REGION/reasoningEngines/ENGINE_ID

    # Create with PSC Interface and agent identity
    python deploy_agent.py --project=PROJECT_ID --region=us-central1 \
        --network-attachment=projects/PROJECT/regions/REGION/networkAttachments/NAME \
        --enable-agent-identity

    # Pin the model endpoint to a specific location (default: global)
    python deploy_agent.py --project=PROJECT_ID --region=us-central1 \
        --model-endpoint-location=us-central1
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
import tempfile


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy mortgage assistant agent to Vertex AI Agent Engine")
    parser.add_argument(
        "--project",
        default=os.environ.get("PROJECT_ID"),
        help="GCP project ID (default: $PROJECT_ID)",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("REGION", "us-central1"),
        help="GCP region (default: $REGION or us-central1)",
    )
    parser.add_argument(
        "--staging-bucket",
        default=None,
        help="GCS bucket for staging (default: gs://PROJECT-staging)",
    )
    parser.add_argument(
        "--display-name",
        default="Mortgage Assistant Agent",
        help="Display name for the deployed agent",
    )
    parser.add_argument(
        "--update",
        default=None,
        metavar="RESOURCE_NAME",
        help="Update an existing agent in-place instead of creating a new one. "
        "Pass the full resource name "
        "(e.g. projects/PROJECT/locations/REGION/reasoningEngines/ENGINE_ID)",
    )
    parser.add_argument(
        "--network-attachment",
        default=None,
        help="Network attachment for PSC Interface (full path or name)",
    )
    parser.add_argument(
        "--dns-peering-domain",
        default=None,
        help="DNS domain for PSC-I DNS peering (e.g. internal.example.com.)",
    )
    parser.add_argument(
        "--dns-peering-target-project",
        default=None,
        help="Project hosting the target VPC network for DNS peering",
    )
    parser.add_argument(
        "--dns-peering-target-network",
        default=None,
        help="VPC network name for DNS peering",
    )
    parser.add_argument(
        "--agent-gateway",
        default=None,
        help="Agent Gateway resource name (e.g. projects/PROJECT/locations/REGION/agentGateways/GATEWAY_ID)",
    )
    parser.add_argument(
        "--enable-agent-identity",
        action="store_true",
        help="Enable agent identity (per-agent least-privilege credentials)",
    )
    parser.add_argument(
        "--mcp-invoker-sa",
        default=os.environ.get("MCP_INVOKER_SA_EMAIL"),
        help=(
            "Email of the service account the deployed agent impersonates to mint "
            "OIDC ID tokens for MCP Cloud Run calls. The agent's identity must hold "
            "roles/iam.serviceAccountTokenCreator on this SA, and this SA must hold "
            "roles/run.invoker on each MCP Cloud Run service. Sourced from terraform "
            "output `agent_mcp_invoker_email`. Default: $MCP_INVOKER_SA_EMAIL."
        ),
    )
    parser.add_argument(
        "--model",
        default="gemini-2.5-flash",
        help="Gemini model name for the agent (default: gemini-2.5-flash)",
    )
    parser.add_argument(
        "--model-endpoint-location",
        default="global",
        help="Location passed to the agent as GOOGLE_CLOUD_LOCATION (default: global)",
    )
    parser.add_argument(
        "--registry-filter",
        default=None,
        help="Optional Google API list-filter expression for MCP registry",
    )
    parser.add_argument(
        "--registry-endpoint",
        default=None,
        help="Override the Agent Registry base URL",
    )
    args = parser.parse_args()

    if not args.project:
        parser.error("--project is required (or set $PROJECT_ID)")

    description = (
        "ADK mortgage assistant agent connecting to legacy DMS, income verification, and corporate email services."
    )

    staging_bucket = args.staging_bucket or f"gs://{args.project}-staging"

    # Ensure the agent package is importable
    agent_dir = os.path.dirname(os.path.abspath(__file__))
    if agent_dir not in sys.path:
        sys.path.insert(0, agent_dir)

    print("Deploying mortgage assistant agent to Agent Engine...")
    print(f"  Project:        {args.project}")
    print(f"  Region:         {args.region}")
    print(f"  Model:          {args.model}")
    print(f"  Model endpoint: {args.model_endpoint_location}")
    print(f"  Registry scope: {args.project}/{args.region}")
    if args.registry_endpoint:
        print(f"  Registry endpoint (override): {args.registry_endpoint}")
    if args.registry_filter:
        print(f"  Registry filter: {args.registry_filter}")
    print(f"  Display name:   {args.display_name}")
    print(f"  Staging bucket: {staging_bucket}")
    print(f"  Mode:           {'update' if args.update else 'create'}")
    if args.agent_gateway:
        print(f"  Agent Gateway:  {args.agent_gateway}")
    if args.update:
        print(f"  Resource name:  {args.update}")
    if args.network_attachment:
        print(f"  Network attachment: {args.network_attachment}")
    if args.enable_agent_identity:
        print("  Agent identity:     enabled")
    if args.mcp_invoker_sa:
        print(f"  MCP invoker SA:     {args.mcp_invoker_sa}")
    print()

    # Configure the agent module's runtime environment. These are read at
    # `from agent.agent import root_agent` time below, so they must be set
    # before the import — not just in the deployed agent's env_vars.
    os.environ["MODEL_NAME"] = args.model
    os.environ["MCP_REGISTRY_PROJECT"] = args.project
    os.environ["MCP_REGISTRY_LOCATION"] = args.region
    if args.registry_filter:
        os.environ["MCP_REGISTRY_FILTER"] = args.registry_filter
    if args.registry_endpoint:
        os.environ["MCP_REGISTRY_ENDPOINT"] = args.registry_endpoint
    if args.mcp_invoker_sa:
        os.environ["MCP_INVOKER_SA_EMAIL"] = args.mcp_invoker_sa

    import vertexai

    vertexai.init(
        project=args.project,
        location=args.region,
        staging_bucket=staging_bucket,
    )

    client = vertexai.Client(
        project=args.project,
        location=args.region,
        http_options=dict(api_version="v1beta1"),
    )

    from agent.agent import root_agent
    from agent.otel_setup import InstrumentedAdkApp

    app = InstrumentedAdkApp(agent=root_agent, enable_tracing=True)

    # Build PSC-I and agent identity config
    config = {}
    if args.network_attachment:
        psc_config = {"network_attachment": args.network_attachment}
        if args.dns_peering_domain:
            psc_config["dns_peering_configs"] = [
                {
                    "domain": args.dns_peering_domain,
                    "target_project": args.dns_peering_target_project or args.project,
                    "target_network": args.dns_peering_target_network,
                }
            ]
        config["psc_interface_config"] = psc_config
    if args.enable_agent_identity:
        config["identity_type"] = "AGENT_IDENTITY"
    if args.agent_gateway:
        config["agent_gateway_config"] = {"agent_to_anywhere_config": {"agent_gateway": args.agent_gateway}}

    agent_src = os.path.join(agent_dir, "agent")
    staging_dir = tempfile.mkdtemp(prefix="agent_deploy_")
    original_cwd = os.getcwd()

    try:
        shutil.copytree(
            agent_src,
            os.path.join(staging_dir, "agent"),
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
        )

        # Create installation_scripts/ with a workaround for the
        # platform bug where .venv/bin/python doesn't exist in the
        # base image but the Dockerfile's compileall step expects it.
        scripts_dir = os.path.join(staging_dir, "installation_scripts")
        os.makedirs(scripts_dir)
        script_path = os.path.join(scripts_dir, "create_venv.sh")
        with open(script_path, "w") as f:
            f.write("#!/bin/bash\n")
            f.write("# Workaround: create a proper .venv for the compileall\n")
            f.write("# step (step 20/21). The base image's Dockerfile runs:\n")
            f.write("#   .venv/bin/python -m compileall \\\n")
            f.write('#     "$(.venv/bin/python -c \\"import site; print(site.getsitepackages()[0])\\")"\n')
            f.write("# A plain symlink causes site.getsitepackages()[0] to\n")
            f.write("# return /usr/local/lib/python3.12/site-packages/ which\n")
            f.write("# is root-owned => PermissionError as appuser.\n")
            f.write("# Fix: create pyvenv.cfg so Python treats .venv/ as a\n")
            f.write("# virtualenv with writable site-packages.\n")
            f.write("set -e\n")
            f.write("PYTHON3=$(which python3)\n")
            f.write(
                "PY_VER=$(python3 -c 'import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")')\n"
            )
            f.write("mkdir -p /code/.venv/bin\n")
            f.write("mkdir -p /code/.venv/lib/python${PY_VER}/site-packages\n")
            f.write('ln -sf "$PYTHON3" /code/.venv/bin/python\n')
            f.write('ln -sf "$PYTHON3" /code/.venv/bin/python3\n')
            f.write("cat > /code/.venv/pyvenv.cfg << PYCFG\n")
            f.write("home = $(dirname $PYTHON3)\n")
            f.write("include-system-site-packages = true\n")
            f.write("PYCFG\n")
            f.write('echo "Created .venv virtualenv (site-packages: /code/.venv/lib/python${PY_VER}/site-packages)"\n')
        os.chmod(script_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP)

        os.chdir(staging_dir)

        env_vars = {
            "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
            "GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES": "false",
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true",
            "OTEL_TRACES_SAMPLER": "parentbased_traceidratio",
            "OTEL_TRACES_SAMPLER_ARG": "1.0",
            "GOOGLE_GENAI_USE_VERTEXAI": "True",
            "GOOGLE_CLOUD_LOCATION": args.model_endpoint_location,
            "MODEL_NAME": args.model,
            "MCP_REGISTRY_PROJECT": args.project,
            "MCP_REGISTRY_LOCATION": args.region,
            **({"MCP_REGISTRY_FILTER": args.registry_filter} if args.registry_filter else {}),
            **({"MCP_REGISTRY_ENDPOINT": args.registry_endpoint} if args.registry_endpoint else {}),
            **({"MCP_INVOKER_SA_EMAIL": args.mcp_invoker_sa} if args.mcp_invoker_sa else {}),
        }
        # Filter out empty or None values to prevent Vertex AI from complaining
        # about "Required field is not set" for environment variables.
        filtered_env_vars = {k: v for k, v in env_vars.items() if v}

        deploy_config = dict(
            staging_bucket=staging_bucket,
            requirements=[
                "google-cloud-aiplatform",
                "google-adk[a2a,agent-identity]>=1.29.0",
                "mcp>=1.9.0",
                "opentelemetry-sdk",
                "opentelemetry-exporter-gcp-trace",
                "cloudpickle",
                "pydantic",
            ],
            extra_packages=[
                "agent",
                "installation_scripts/create_venv.sh",
            ],
            build_options={
                "installation_scripts": [
                    "installation_scripts/create_venv.sh",
                ],
            },
            env_vars=filtered_env_vars,
            display_name=args.display_name,
            description=description,
            min_instances=2,
            resource_limits={"cpu": "4", "memory": "8Gi"},
        )

        if config:
            deploy_config.update(config)

        if args.update:
            engine = client.agent_engines.update(name=args.update, agent=app, config=deploy_config)
        else:
            engine = client.agent_engines.create(agent=app, config=deploy_config)
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(staging_dir, ignore_errors=True)

    reasoning_engine_name = engine.api_resource.name

    print()
    if args.update:
        print(f"Agent updated: {reasoning_engine_name}")
    else:
        print(f"Agent deployed: {reasoning_engine_name}")
        print()
        print("Set the resource name in your terraform.tfvars:")
        print(f'  agent_engine_resource_name = "{reasoning_engine_name}"')
        if args.enable_agent_identity:
            print("\nAgent identity enabled. Grant IAM to the agent's principal shown above.")


if __name__ == "__main__":
    main()
