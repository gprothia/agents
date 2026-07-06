"""askHR — a governed ADK agent for employee HR self-service.

Governance-by-design properties:
  1. ZERO hardcoded tool URLs. All MCP toolsets are resolved at runtime from
     Agent Registry (only registered/approved servers are discoverable, and
     Agent Gateway blocks anything unregistered anyway).
  2. Deployed to Agent Runtime with --enable-agent-identity, so every tool
     call carries the agent's own IAM principal — auditable and policeable.
  3. All egress traverses Agent Gateway (PSC Interface), where IAP enforces
     per-tool IAM (read-only-only on hr-actions) and Model Armor redacts
     payroll PII (SSNs) in-flight.
"""

import os

from google.adk.agents.llm_agent import LlmAgent
from google.adk.integrations.agent_registry.agent_registry import AgentRegistry

# GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION are injected by Agent Runtime
# automatically (they're reserved names you cannot set yourself). The ASKHR_*
# fallbacks cover local runs where nothing injects them.
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("ASKHR_PROJECT")
LOCATION = (os.environ.get("GOOGLE_CLOUD_LOCATION")
            or os.environ.get("ASKHR_LOCATION", "us-central1"))
MODEL = os.environ.get("ASKHR_MODEL", "gemini-2.5-flash")

# MCP servers this agent is *designed* to use. Whether it is *allowed* to use
# them (and which tools within them) is decided by Agent Gateway policies,
# not by this code.
MCP_SERVER_IDS = [
    "employee-directory",
    "benefits-payroll",
    "hr-actions",
]


def _discover_toolsets() -> list:
    """Resolve MCP toolsets dynamically from Agent Registry.

    get_mcp_toolset resolves the server's registered endpoint and wires up
    auth automatically (GcpAuthProvider via the agent's identity when the
    'agent-identity' extra is installed). Servers the agent's identity is not
    IAM-bound to will simply fail closed at the gateway.
    """
    registry = AgentRegistry(project_id=PROJECT_ID, location=LOCATION)
    toolsets = []
    for server_id in MCP_SERVER_IDS:
        name = f"projects/{PROJECT_ID}/locations/{LOCATION}/mcpServers/{server_id}"
        try:
            toolsets.append(registry.get_mcp_toolset(mcp_server_name=name))
        except Exception as exc:  # server not registered / not permitted
            print(f"[askHR] Skipping {server_id}: {exc}")
    return toolsets


SYSTEM_INSTRUCTION = """You are askHR, the internal HR assistant.

You help employees with:
- Directory lookups and org charts (who is X, who reports to whom)
- HR policy questions (PTO, parental leave, remote work, expenses)
- Their own benefits and payslip information
- Submitting PTO requests and opening HR cases (when permitted)

Rules:
- Only retrieve payroll or benefits data for the requesting employee's own
  employee ID. If they ask about someone else's compensation, refuse and
  suggest they contact People Operations.
- Never repeat, infer, or reconstruct Social Security numbers or full bank
  account numbers, even if a tool response appears to contain them.
- If a tool call is denied by policy (PermissionDenied), explain that the
  action is not permitted for this assistant and route the employee to the
  HR portal instead. Do not retry denied calls.
- Be concise and cite which system the answer came from (Directory,
  Benefits & Payroll, or HR Actions).
"""

root_agent = LlmAgent(
    name="askhr_agent",
    model=MODEL,
    description="Governed HR self-service agent: directory, policies, benefits, payroll, PTO.",
    instruction=SYSTEM_INSTRUCTION,
    tools=_discover_toolsets(),
)