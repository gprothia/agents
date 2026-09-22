"""ADK-facing tool functions.

These are plain Python functions with typed signatures and docstrings; ADK reads the
signature/docstring to expose them to the model. They wrap the pure modules so the same
logic is used by the live agent and by run_simulated.py.
"""
from __future__ import annotations
from . import playbooks, recommend, plan_sheet, a2ui  # noqa: F401


def search_playbook(topic: str) -> dict:
    """Look up a grounding playbook for a setup topic and return its text + source URL.

    Args:
      topic: "app_setup", "region", or "encryption".
    """
    return playbooks.search_playbook(topic)


def recommend_app_config(audience: str, capability: str, app_name: str = "Employee Assistant") -> dict:
    """Recommend a Gemini Enterprise app config, grounded in the app_setup playbook.

    Args:
      audience: "all_employees" or "specific_team".
      capability: "search_summarize" or "actions".
      app_name: display name for the app.
    """
    return recommend.recommend_app_config(audience, capability, app_name)


def recommend_infra_config(residency: str, encryption: str) -> dict:
    """Recommend region + encryption, grounded in the region and encryption playbooks.

    Args:
      residency: "eu", "us", or "none".
      encryption: "cmek" or "gmek".
    """
    return recommend.recommend_infra_config(residency, encryption)


def recommend_connector_config(scope: str = "all_users", index_what: str = "messages_attachments",
                               actions: str = "with_actions", sync: str = "daily") -> dict:
    """Recommend a Gmail connector config, grounded in the Gmail playbook and consistent
    with the region/encryption already saved in the plan sheet.

    Args:
      scope: whose mail. POC default "all_users" (domain-wide via Workspace customer ID).
      index_what: "messages" or "messages_attachments".
      actions: "read_only" or "with_actions" (send/reply/draft/download).
      sync: "continuous" or "daily".
    """
    return recommend.recommend_connector_config(scope, index_what, actions, sync)


def read_plan(area: str = "") -> list:
    """Read decisions already saved in the plan sheet (optionally filter by area).

    Use this to check what has been decided (e.g. the infra region/encryption) before
    recommending a dependent step such as a connector.

    Args:
      area: "" for all, or one of "infra", "app", "connector".
    """
    decs = plan_sheet.read_decisions()
    if area:
        decs = [d for d in decs if d.get("area") == area]
    # return a compact view
    return [{"id": d.get("id"), "area": d.get("area"), "title": d.get("title"),
             "value": d.get("value", {}), "status": d.get("status")} for d in decs]


def save_decision(decision: dict, owner: str = "planning-agent") -> dict:
    """Save an approved recommendation to the plan sheet (plan.xlsx). Call ONLY after the user approves.

    Args:
      decision: the recommendation dict returned by a recommend_* tool.
      owner: who owns this decision.
    """
    return plan_sheet.save_decision(decision, owner=owner)


def build_recommendation_ui(decision: dict) -> dict:
    """Return an A2UI recommendation surface (JSONL) for rendering the recommendation as a card.

    Args:
      decision: the recommendation dict to render.
    """
    surface = a2ui.recommendation_surface(decision)
    return {"a2ui_jsonl": a2ui.to_jsonl(surface), "surface": surface}
