import os,re
from pathlib import Path
from dotenv import load_dotenv # <--- Added to load environment variables from .env file

# Always load .env from the askhr_oauth directory regardless of where adk run is executed
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

# Remove revoked/stale GOOGLE_APPLICATION_CREDENTIALS key from shell environment so ADC is used
if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
    del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]

import subprocess
import google.auth
import google.auth.credentials
import google.auth.transport.requests

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

try:
    _creds, _ = google.auth.default()
    _creds.refresh(google.auth.transport.requests.Request())
except Exception:
    _project = os.getenv("GOOGLE_CLOUD_PROJECT", "sunlit-segment-396117")
    try:
        _gcloud_creds = GcloudCliCredentials()
        google.auth.default = lambda *args, **kwargs: (_gcloud_creds, _project)
    except Exception:
        pass

from google.adk import Agent
from google.adk.apps import App
import pydantic

# Ensure unpickled Pydantic models (such as LlmAgent across Python/ADK versions) never fail when __pydantic_private__ is None
_orig_pydantic_getattr = pydantic.BaseModel.__getattr__

def _safe_pydantic_getattr(self, item: str):
    if getattr(self, "__pydantic_private__", None) is None:
        object.__setattr__(self, "__pydantic_private__", {})
    try:
        return _orig_pydantic_getattr(self, item)
    except (KeyError, TypeError):
        if item.startswith("_"):
            return None
        raise

pydantic.BaseModel.__getattr__ = _safe_pydantic_getattr


print(os.getenv("GOOGLE_GENAI_USE_VERTEXAI"), os.getenv("GOOGLE_CLOUD_PROJECT"))
#from google.adk.tools.agent_tool import AgentTool
#AgentTool.propagate_grounding_metadata = False


from .prompts import (
    ROOT_AGENT_INSTRUCTION,
    POLICY_SEARCH_INSTRUCTION,
    GET_INFO_INSTRUCTION,
    UPDATE_INFO_INSTRUCTION
)

from .tools import (
    search_hr_policy,
    get_employee_info,
    update_employee_info,
    get_user_context
)

MODEL = os.getenv("MODEL", "gemini-2.5-flash")


# Sub-Agent 1: Policy Search Agent
policy_search_agent = Agent(
    name="policy_search_agent",
    description="Search and answer questions regarding company HR policies, benefits, and rules.",
    instruction=POLICY_SEARCH_INSTRUCTION,
    tools=[search_hr_policy],
    model=MODEL
)

# Sub-Agent 2: Employee Info Retrieval Agent
get_info_agent = Agent(
    name="get_info_agent",
    description="Retrieve personal employee information such as leave balance, address, or remote status.",
    instruction=GET_INFO_INSTRUCTION,
    tools=[get_employee_info],
    model=MODEL
)

# Sub-Agent 3: Employee Info Update Agent
update_info_agent = Agent(
    name="update_info_agent",
    description="Update personal employee information such as contact details or address.",
    instruction=UPDATE_INFO_INSTRUCTION,
    tools=[update_employee_info],
    model=MODEL
)

# Root Agent: AskHR Orchestrator
# Natively passing sub-agents as tools or directly depends on ADK version.
# For Google ADK, agents can be passed into the 'sub_agents' parameter of the orchestrator, or directly mapped.
# We will use the 'sub_agents' parameter to enable multi-agent routing.
# Root Agent: AskHR Orchestrator
# Natively passing sub-agents is not supported. We wrap them in AgentTool.
root_agent = Agent(
    name="askhr_agent",
    instruction=ROOT_AGENT_INSTRUCTION,
    before_agent_callback=get_user_context,
    sub_agents=[policy_search_agent, get_info_agent, update_info_agent],
    model=MODEL
)

app = App(name="askhr", root_agent=root_agent)
#app = root_agent
#testcommit
