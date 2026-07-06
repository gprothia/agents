import google.auth
from google.auth.transport.requests import AuthorizedSession
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
    print(resp.json())
    if resp.status_code >= 400:
        print(f"\nGateway PATCH failed ({resp.status_code}): {resp.text}",
              file=sys.stderr)
        print("If the error mentions an unknown field, your project's preview "
              "build may use a different config path — compare with:\n"
              "https://docs.cloud.google.com/gemini-enterprise-agent-platform/"
              "scale/runtime/agent-gateway-runtime-deploy", file=sys.stderr)
        resp.raise_for_status()
    return resp.json()

attach_gateway(
    project="bold-kit-384717", 
    region="us-central1", 
    engine_id="3213791673884606464", 
    gateway="projects/851970768145/locations/us-central1/agentGateways/agent-gateway")

