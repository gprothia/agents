"""GE Activation Agent - Discovery & Planning (POC).

Run with:  adk web        (from the project root, pick "ge_agent")
       or:  adk run ge_agent

Requires GOOGLE_API_KEY (or Vertex config) in the environment / .env.
"""
from __future__ import annotations

try:
    from google.adk.agents import LlmAgent
except Exception as e:  # pragma: no cover - lets the rest of the project import without ADK
    LlmAgent = None

from .tools import (
    search_playbook,
    recommend_app_config,
    recommend_infra_config,
    save_decision,
    build_recommendation_ui,
)

MODEL = "gemini-2.5-flash"

INSTRUCTION = """
You are the GE Activation Agent, a consultant that guides a customer through setting up
Gemini Enterprise. For the POC you handle two areas: APP SETUP and INFRASTRUCTURE
(region + encryption). You do NOT do Jira yet.

Work through each area with the SAME three-beat pattern:

1) DISCOVERY - ask the user a few plain-language questions for the area. Keep it short;
   ask what you need, one area at a time. Do not assume answers.
     - App setup: who will use the first app (all employees / a specific team), and what
       should it do (search & summarize / take actions).
     - Infrastructure: where must data live (EU / US / no requirement), and how should
       data be encrypted (customer-managed CMEK / Google-managed).

2) RECOMMENDATION - call search_playbook for the area first so your advice is grounded,
   then call recommend_app_config or recommend_infra_config with the user's answers.
   Present the recommendation clearly: the recommended choice, the PROS, and the
   WATCH-OUTS. If it is a one-way decision, say so plainly and explain why it can't be
   undone. Cite the source_url. You may call build_recommendation_ui to produce the A2UI
   card if a UI is available.

3) DECISION - ask the user to approve or adjust. Only AFTER explicit approval, call
   save_decision with the recommendation. Confirm it was saved (its id) and that it is
   ready for the deployment agent. Never call save_decision before the user approves,
   and be especially careful with one-way decisions.

Suggested order: do INFRASTRUCTURE first (it's a one-way door), then APP SETUP. After
both are saved, tell the user the plan sheet is ready and the deployment agent can
generate and apply the Terraform.

Never invent product facts; if the playbook doesn't cover something, say so.
"""

if LlmAgent is not None:
    root_agent = LlmAgent(
        model=MODEL,
        name="ge_activation_agent",
        description="Consultant agent that plans Gemini Enterprise app and infra setup and saves decisions to the plan sheet.",
        instruction=INSTRUCTION,
        tools=[
            search_playbook,
            recommend_app_config,
            recommend_infra_config,
            build_recommendation_ui,
            save_decision,
        ],
    )
else:  # pragma: no cover
    root_agent = None
