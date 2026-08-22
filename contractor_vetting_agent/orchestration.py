"""Multi-Agent Orchestration, Hierarchical Coordinator, and Strategic Model Routing.

Implements:
1. Compliance & Identity Specialist Sub-Agent (Fast Model: gemini-2.5-flash)
2. Financial & Safety Risk Specialist Sub-Agent (Fast Model: gemini-2.5-flash)
3. Past Performance & Reference Sub-Agent (Fast Model: gemini-2.5-flash)
4. Master Contractor Vetting Coordinator Agent (Deep Reasoning Model: gemini-2.5-pro)
"""

from typing import List
from google.adk import Agent
from google.adk.agents import LlmAgent

from .config import (
    DEEP_REASONING_MODEL,
    DEFAULT_GENERATE_CONTENT_CONFIG,
    FAST_EXTRACTION_MODEL,
)
from .prompts import (
    COMPLIANCE_SPECIALIST_INSTRUCTION,
    CONTRACTOR_VETTING_COORDINATOR_INSTRUCTION,
    FINANCIAL_SAFETY_SPECIALIST_INSTRUCTION,
    PAST_PERFORMANCE_SPECIALIST_INSTRUCTION,
)
from .tools import (
    audit_workplace_safety_and_emr,
    calculate_financial_risk_and_bonding,
    fetch_past_performance_and_references,
    finalize_contractor_vetting_dossier,
    request_human_oversight_approval,
    screen_sanctions_and_debarment_lists,
    verify_contractor_license_and_insurance,
)


def create_compliance_agent() -> LlmAgent:
    """Creates the Identity & Legal Compliance Specialist Sub-Agent.

    Utilizes fast model routing (Gemini 2.5 Flash) for high-speed document
    extraction, license verification, and sanctions screening.
    """
    return Agent(
        name="compliance_specialist_agent",
        description="Specialist agent for verifying state contractor licensing, insurance policies, and federal/international sanctions lists.",
        instruction=COMPLIANCE_SPECIALIST_INSTRUCTION,
        tools=[
            verify_contractor_license_and_insurance,
            screen_sanctions_and_debarment_lists,
        ],
        model=FAST_EXTRACTION_MODEL,
        generate_content_config=DEFAULT_GENERATE_CONTENT_CONFIG,
    )


def create_financial_safety_agent() -> LlmAgent:
    """Creates the Financial Solvency & Safety Audit Specialist Sub-Agent.

    Utilizes fast model routing (Gemini 2.5 Flash) to parse financial ratios,
    surety bonding capacities, and OSHA 300/EMR safety metrics.
    """
    return Agent(
        name="financial_safety_specialist_agent",
        description="Specialist agent for auditing financial credit health, surety bonding limits, and workplace safety records/EMR.",
        instruction=FINANCIAL_SAFETY_SPECIALIST_INSTRUCTION,
        tools=[
            calculate_financial_risk_and_bonding,
            audit_workplace_safety_and_emr,
        ],
        model=FAST_EXTRACTION_MODEL,
        generate_content_config=DEFAULT_GENERATE_CONTENT_CONFIG,
    )


def create_past_performance_agent() -> LlmAgent:
    """Creates the Past Performance & Reference Audit Specialist Sub-Agent.

    Utilizes fast model routing (Gemini 2.5 Flash) for evaluating historical
    project delivery track records, cost/schedule variances, and client surveys.
    """
    return Agent(
        name="past_performance_specialist_agent",
        description="Specialist agent for retrieving and scoring historical project performance, CPARS evaluations, and customer references.",
        instruction=PAST_PERFORMANCE_SPECIALIST_INSTRUCTION,
        tools=[
            fetch_past_performance_and_references,
        ],
        model=FAST_EXTRACTION_MODEL,
        generate_content_config=DEFAULT_GENERATE_CONTENT_CONFIG,
    )


def create_coordinator_agent(sub_agents: bool = True) -> LlmAgent:
    """Creates the Master Contractor Vetting Coordinator Agent.

    Utilizes deep reasoning model routing (Gemini 2.5 Pro) for high-level
    risk synthesis, trade-off evaluation, regulatory compliance adjudication,
    and official certification dossier issuance.
    """
    sub_agent_list = [
        create_compliance_agent(),
        create_financial_safety_agent(),
        create_past_performance_agent(),
    ] if sub_agents else []

    all_tools = [
        verify_contractor_license_and_insurance,
        screen_sanctions_and_debarment_lists,
        calculate_financial_risk_and_bonding,
        audit_workplace_safety_and_emr,
        fetch_past_performance_and_references,
        request_human_oversight_approval,
        finalize_contractor_vetting_dossier,
    ]

    return Agent(
        name="contractor_vetting_coordinator",
        description="Lead Procurement Vetting & Compliance Adjudicator orchestrating full 5-pillar contractor vetting and risk qualification.",
        instruction=CONTRACTOR_VETTING_COORDINATOR_INSTRUCTION,
        tools=all_tools,
        sub_agents=sub_agent_list,
        model=DEEP_REASONING_MODEL,
        generate_content_config=DEFAULT_GENERATE_CONTENT_CONFIG,
    )
