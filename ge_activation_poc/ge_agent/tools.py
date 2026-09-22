"""ADK-facing tool functions.

These are plain Python functions with typed signatures and docstrings; ADK reads the
signature/docstring to expose them to the model. They wrap the pure modules so the same
logic is used by the live agent and by run_simulated.py.
"""
from __future__ import annotations
from . import playbooks, recommend, plan_sheet, a2ui


DISCOVERY_QUESTIONS = {
    "infra": [
        {
            "key": "residency",
            "label": "Where must your Gemini Enterprise data live?",
            "single": True,
            "options": [
                {"label": "European Union (EU)", "value": "eu"},
                {"label": "United States (US)", "value": "us"},
                {"label": "No strict residency requirement", "value": "none"},
            ],
        },
        {
            "key": "encryption",
            "label": "How should your data be encrypted?",
            "single": True,
            "options": [
                {"label": "Customer-Managed Encryption Keys (CMEK)", "value": "cmek"},
                {"label": "Google-Managed Encryption Keys (GMEK)", "value": "gmek"},
            ],
        },
    ],
    "app_setup": [
        {
            "key": "audience",
            "label": "Who will use the first Gemini Enterprise application?",
            "single": True,
            "options": [
                {"label": "All Employees (Company-wide)", "value": "all_employees"},
                {"label": "A Specific Team / Department", "value": "specific_team"},
            ],
        },
        {
            "key": "capability",
            "label": "What should the application do?",
            "single": True,
            "options": [
                {"label": "Search & Summarize Enterprise Knowledge", "value": "search_summarize"},
                {"label": "Take Actions & Execute Workflows", "value": "actions"},
            ],
        },
    ],
}


def build_discovery_ui(area: str) -> dict:
    """Build an A2UI interactive discovery form surface for 'infra' or 'app_setup'.

    Args:
      area: "infra" (for infrastructure: residency + encryption) or "app_setup" (audience + capability).
    """
    key = "infra" if "infra" in area.lower() else "app_setup"
    questions = DISCOVERY_QUESTIONS[key]
    title = "Infrastructure Setup" if key == "infra" else "Application Setup"
    surface = a2ui.discovery_surface(title, questions)
    return {
        "area": key,
        "a2ui_jsonl": a2ui.to_jsonl(surface),
        "surface": surface,
    }


def search_playbook(topic: str) -> dict:
    """Look up a grounding playbook for a setup topic and return its text + source URL.

    Args:
      topic: "app_setup", "region", or "encryption".
    """
    return playbooks.search_playbook(topic)


def recommend_app_config(audience: str, capability: str, app_name: str = "Employee Assistant") -> dict:
    """Recommend a Gemini Enterprise app config, grounded in the app_setup playbook, with A2UI card surface.

    Args:
      audience: "all_employees" or "specific_team".
      capability: "search_summarize" or "actions".
      app_name: display name for the app.
    """
    rec = recommend.recommend_app_config(audience, capability, app_name)
    surface = a2ui.recommendation_surface(rec)
    rec["a2ui_jsonl"] = a2ui.to_jsonl(surface)
    rec["surface"] = surface
    return rec


def recommend_infra_config(residency: str, encryption: str) -> dict:
    """Recommend region + encryption, grounded in the region and encryption playbooks, with A2UI card surface.

    Args:
      residency: "eu", "us", or "none".
      encryption: "cmek" or "gmek".
    """
    rec = recommend.recommend_infra_config(residency, encryption)
    surface = a2ui.recommendation_surface(rec)
    rec["a2ui_jsonl"] = a2ui.to_jsonl(surface)
    rec["surface"] = surface
    return rec


def save_decision(decision: dict, owner: str = "planning-agent") -> dict:
    """Save an approved recommendation to the plan sheet (plan.xlsx) and return an A2UI confirmation surface. Call ONLY after the user approves.

    Args:
      decision: the recommendation dict returned by a recommend_* tool.
      owner: who owns this decision.
    """
    saved = plan_sheet.save_decision(decision, owner=owner)
    surface = a2ui.decision_saved_surface(saved, decision)
    saved["a2ui_jsonl"] = a2ui.to_jsonl(surface)
    saved["surface"] = surface
    return saved


def build_recommendation_ui(decision: dict) -> dict:
    """Return an A2UI recommendation surface (JSONL) for rendering the recommendation as a card.

    Args:
      decision: the recommendation dict to render.
    """
    surface = a2ui.recommendation_surface(decision)
    return {"a2ui_jsonl": a2ui.to_jsonl(surface), "surface": surface}

