"""Deploy askHR to Agent Runtime and bind it to the Agent Gateway.

Strategy (robust across SDK versions):
  1. agent_engines.create() with only widely-supported kwargs.
     psc_interface_config is attempted and gracefully skipped if the
     installed SDK doesn't know it (with a loud warning + remediation).
  2. Gateway binding is done AFTER creation via the documented REST PATCH:
       spec.deploymentSpec.agentGatewayConfig.agentToAnywhereConfig.agentGateway
     This avoids preview-only flat kwargs like `agent_gateway` /
     `enable_agent_identity`, which vary between SDK builds and raise
     TypeError on versions that don't have them.
  3. Agent Identity: on current Agent Runtime preview builds, deployed
     agents receive an Agent Identity automatically; verify in
     Console -> Agent Platform -> your agent -> Identity, and see
     https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity

Usage:
  uv run python deploy_agent.py \
    --project $PROJECT_ID --region us-central1 \
    --agent-gateway projects/$PROJECT_ID/locations/us-central1/agentGateways/askhr-agent-gateway \
    --network-attachment projects/$PROJECT_ID/regions/us-central1/networkAttachments/askhr-psc-attachment \
    --mcp-invoker-sa askhr-mcp-invoker@$PROJECT_ID.iam.gserviceaccount.com
"""

import argparse
import sys

import google.auth
from google.auth.transport.requests import AuthorizedSession

import vertexai
from vertexai import agent_engines

from askhr_agent.agent import root_agent

REQUIREMENTS = [
    "google-cloud-aiplatform",
    "google-adk[a2a,agent-identity]>=1.29.0",
    "mcp>=1.9.0",
    "opentelemetry-sdk",
    "opentelemetry-exporter-gcp-trace",
]


def create_agent(args) -> "agent_engines.AgentEngine":
    """Create the runtime with stable kwargs; degrade gracefully on preview ones."""
    kwargs = dict(
        agent_engine=root_agent,
        display_name=args.agent_name,
        description="askHR: governed HR self-service agent",
        requirements=REQUIREMENTS,
        extra_packages=["./askhr_agent"],
        # NOTE: GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION are RESERVED —
        # Agent Runtime injects them automatically. Only custom vars here.
        env_vars={
            "ASKHR_PROJECT": args.project,
            "ASKHR_LOCATION": args.region,
        },
        #service_account=args.mcp_invoker_sa,
        psc_interface_config={"network_attachment": args.network_attachment},
    )
    try:
        return agent_engines.create(**kwargs)
    except TypeError as exc:
        # Older SDKs may not know psc_interface_config / service_account.
        # Drop the offending kwarg(s) one at a time so the deploy proceeds,
        # but tell the user exactly what to do about it.
        msg = str(exc)
        for optional in ("psc_interface_config", "service_account"):
            if optional in msg and optional in kwargs:
                print(f"\nWARNING: your google-cloud-aiplatform SDK does not "
                      f"support '{optional}'. Deploying WITHOUT it.")
                if optional == "psc_interface_config":
                    print("  -> Without the network attachment the agent's egress "
                          "will NOT route through your VPC/gateway. Upgrade first:\n"
                          "     pip install -U 'google-cloud-aiplatform[agent_engines]'\n"
                          "  or attach it afterwards via REST "
                          "(spec.deploymentSpec.pscInterfaceConfig).")
                kwargs.pop(optional)
                return create_agent_with(kwargs)
        raise


def create_agent_with(kwargs):
    try:
        return agent_engines.create(**kwargs)
    except TypeError:
        # Recurse through remaining optional kwargs if several are unsupported.
        return create_agent_from_retry(kwargs)


def create_agent_from_retry(kwargs):
    for optional in ("psc_interface_config", "service_account"):
        kwargs.pop(optional, None)
    return agent_engines.create(**kwargs)


def attach_gateway(project: str, region: str, engine_id: str, gateway: str) -> dict:
    """Bind the egress Agent Gateway via the documented REST PATCH."""
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(creds)
    url = (f"https://{region}-aiplatform.googleapis.com/v1beta1/"
           f"projects/{project}/locations/{region}/reasoningEngines/{engine_id}")
    body = {
        "spec": {
            "identityType": "AGENT_IDENTITY",  # <-- Required for Agent Gateway
            "deploymentSpec": {
                "agentGatewayConfig": {
                    "agentToAnywhereConfig": {"agentGateway": gateway}
                }
            }
        }
    }
    resp = session.patch(
        url,
        params={"updateMask": "spec.deploymentSpec.agentGatewayConfig,spec.identityType"},
        json=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    if resp.status_code >= 400:
        print(f"\nGateway PATCH failed ({resp.status_code}): {resp.text}",
              file=sys.stderr)
        print("If the error mentions an unknown field, your project's preview "
              "build may use a different config path — compare with:\n"
              "https://docs.cloud.google.com/gemini-enterprise-agent-platform/"
              "scale/runtime/agent-gateway-runtime-deploy", file=sys.stderr)
        resp.raise_for_status()
    return resp.json()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--project", required=True)
    p.add_argument("--region", default="us-central1")
    p.add_argument("--agent-name", default="askhr-agent")
    p.add_argument("--agent-gateway", required=True,
                   help="projects/PROJECT/locations/REGION/agentGateways/NAME")
    p.add_argument("--network-attachment", required=True,
                   help="projects/PROJECT/regions/REGION/networkAttachments/NAME")
    p.add_argument("--mcp-invoker-sa", required=True)
    args = p.parse_args()

    vertexai.init(project=args.project, location=args.region,
                  staging_bucket=f"gs://{args.project}-askhr-staging")

    remote_agent = create_agent(args)
    engine_id = remote_agent.resource_name.split("/")[-1]
    print("Deployed:", remote_agent.resource_name)
    print("Agent ID (numeric):", engine_id)

    print("\nAttaching Agent Gateway (egress) via REST PATCH ...")
    attach_gateway(args.project, args.region, engine_id, args.agent_gateway)
    print("Gateway attached:", args.agent_gateway)

    print("\nNext steps:")
    print("  1. Verify Agent Identity in Console -> Agent Platform -> agent -> Identity")
    print("  2. export AGENT_ID=" + engine_id)
    print("  3. bash scripts/06_grant_governance_policies.sh")


if __name__ == "__main__":
    main()