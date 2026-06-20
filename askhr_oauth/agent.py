import os
from dotenv import load_dotenv # <--- Added to load environment variables from .env file
from google.adk import Agent

load_dotenv() # <--- Added to load environment variables from .env file
from google.adk.tools.agent_tool import AgentTool

# Monkey-patch AgentTool to fix missing attribute bug in some ADK versions
AgentTool.propagate_grounding_metadata = False

from prompts import ( # <--- Changed from .prompts to avoid relative import error
    ROOT_AGENT_INSTRUCTION,
    POLICY_SEARCH_INSTRUCTION,
    GET_INFO_INSTRUCTION,
    UPDATE_INFO_INSTRUCTION
)

from tools import ( # <--- Changed from .tools to avoid relative import error
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

app = root_agent
#testcommit
