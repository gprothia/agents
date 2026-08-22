"""Main ADK Entrypoint for Contractor Vetting Enterprise Agent.

Exports:
- root_agent: Master coordinator agent.
- app: ADK App packaged with Guardrails Plugin.
- Sub-agents for modular invocation.
"""

from google.adk.apps import App
from .guardrails import ContractorVettingGuardrailsPlugin
from .orchestration import (
    create_compliance_agent,
    create_coordinator_agent,
    create_financial_safety_agent,
    create_past_performance_agent,
)

# Instantiate the primary coordinator agent
root_agent = create_coordinator_agent(sub_agents=True)

# Sub-agents
compliance_agent = create_compliance_agent()
financial_safety_agent = create_financial_safety_agent()
past_performance_agent = create_past_performance_agent()

# Instantiate ADK Application with Security & Policy Guardrails Plugin
app = App(
    name="contractor_vetting_agent",
    root_agent=root_agent,
    plugins=[ContractorVettingGuardrailsPlugin(enforce_strict_hitl=True)],
)
