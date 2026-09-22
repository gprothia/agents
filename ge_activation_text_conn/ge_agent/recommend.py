"""Turn discovery answers into a grounded recommendation.

Each recommendation is a plain dict the agent can present and, on approval, save to
the plan sheet. It always carries the pros, the watch-outs, whether it is a one-way
door, the rationale, the citable source, and the Terraform resource + fields it maps
to -- so the recommendation and the generated Terraform both trace to a source.
"""
from __future__ import annotations
from .playbooks import search_playbook
from . import plan_sheet


def _infra_from_plan() -> dict:
    """Return the most recent saved infra decision's value, or defaults if none saved yet."""
    for d in reversed(plan_sheet.read_decisions()):
        if d.get("area") == "infra":
            return d.get("value", {})
    return {}


def recommend_app_config(audience: str, capability: str, app_name: str = "Employee Assistant") -> dict:
    """Recommend a Gemini Enterprise app (engine) configuration.

    Args:
      audience: "all_employees" or "specific_team".
      capability: "search_summarize" or "actions".
      app_name: display name for the app.

    Returns:
      A recommendation dict (area="app").
    """
    pb = search_playbook("app_setup")
    audience = (audience or "all_employees").lower()
    capability = (capability or "search_summarize").lower()

    pros, watchouts = [], []
    if audience == "all_employees":
        pros.append("Fastest path to broad value; one simple permission scope")
    else:
        pros.append("Tight, least-privilege scope")
        watchouts.append("Narrower initial value; more apps as you expand")

    if capability == "actions":
        pros.append("App can act in connected systems (e.g. create a Jira issue)")
        watchouts.append("Requires connector actions + per-user OAuth")
        if audience == "all_employees":
            watchouts.append("Actions on an all-employee app is not recommended")
    else:
        pros.append("Read-only; lowest risk; no per-user OAuth")
        watchouts.append("Cannot create tickets or send mail (add an actions app later)")

    value = {
        "app_name": app_name,
        "audience": audience,
        "capability": capability,
        "actions_enabled": capability == "actions",
        "app_type": "APP_TYPE_INTRANET",
        "collection_id": "default_collection",
    }
    return {
        "area": "app",
        "title": f'App: "{app_name}"',
        "summary": f"{'Search & summaries' if capability=='search_summarize' else 'Search + actions'} for "
                   f"{'all staff' if audience=='all_employees' else 'a specific team'}",
        "value": value,
        "pros": pros,
        "watchouts": watchouts,
        "one_way": False,
        "rationale": "Broad value with least privilege" if audience == "all_employees"
                     else "Scoped access suited to actions",
        "source_url": pb.get("source_url", ""),
        "terraform_resource": "google_discovery_engine_search_engine",
    }


def recommend_infra_config(residency: str, encryption: str) -> dict:
    """Recommend region + encryption for the project.

    Args:
      residency: "eu", "us", or "none".
      encryption: "cmek" or "gmek".

    Returns:
      A recommendation dict (area="infra"). This is a one-way decision.
    """
    region_pb = search_playbook("region")
    enc_pb = search_playbook("encryption")
    residency = (residency or "none").lower()
    encryption = (encryption or "gmek").lower()

    location = {"eu": "eu", "us": "us", "none": "global"}.get(residency, "global")

    pros, watchouts = [], []
    if location == "eu":
        pros.append("Meets EU data residency (GDPR)")
    elif location == "us":
        pros.append("Meets US residency")
    else:
        pros.append("Simplest; broadest feature availability")
        watchouts.append("No residency guarantee")
    watchouts.append("Region cannot be changed after data stores exist")

    if encryption == "cmek":
        pros.append("You control the keys; supports third-party connectors")
        watchouts.append("Key cannot be swapped once applied; all connectors share one CMEK config")
        watchouts.append("First-party connectors use Google-managed keys (except BigQuery/GCS import)")
        watchouts.append("Cloud KMS billed continuously once registered")
    else:
        pros.append("Simplest; nothing to manage")
        watchouts.append("You do not hold the keys; can't move THIS project to CMEK later without a rebuild")

    value = {
        "location": location,
        "encryption": encryption,
        "cmek_config_id": "default" if encryption == "cmek" else None,
        # placeholder KMS key path; the real one is chosen/created during deployment
        "kms_key": (f"projects/PROJECT_ID/locations/{'europe' if location=='eu' else location}"
                    f"/keyRings/ge/cryptoKeys/gemini-enterprise") if encryption == "cmek" else None,
    }
    return {
        "area": "infra",
        "title": f"Region {location} + {'CMEK' if encryption=='cmek' else 'Google-managed keys'}",
        "summary": f"Data in '{location}', "
                   f"{'customer-managed (CMEK)' if encryption=='cmek' else 'Google-managed'} encryption",
        "value": value,
        "pros": pros,
        "watchouts": watchouts,
        "one_way": True,
        "rationale": "Residency + key-control requirements",
        "source_url": enc_pb.get("source_url", "") or region_pb.get("source_url", ""),
        "terraform_resource": "google_discovery_engine_cmek_config" if encryption == "cmek" else "(none)",
    }


def recommend_connector_config(scope: str = "all_users", index_what: str = "messages_attachments",
                               actions: str = "with_actions", sync: str = "daily") -> dict:
    """Recommend a Gmail connector configuration, grounded in the Gmail playbook.

    Reads the region + encryption already saved in the plan sheet so the connector is
    consistent with the infrastructure decision (encryption is only configurable for
    us/eu locations).

    Args:
      scope: whose mail. POC: "all_users" (domain-wide via Workspace customer ID).
      index_what: "messages" or "messages_attachments".
      actions: "read_only" or "with_actions" (send/reply/draft/download).
      sync: "continuous" or "daily".
    """
    pb = search_playbook("connector_gmail")
    infra = _infra_from_plan()
    location = infra.get("location", "eu")
    encryption = infra.get("encryption", "gmek")
    with_actions = (actions or "with_actions").lower() == "with_actions"
    attachments = "attachment" in (index_what or "")

    entities = ["messages"] + (["attachments"] if attachments else [])
    action_list = ["send", "reply", "draft", "download_attachment"] if with_actions else []

    pros = [
        "ACL-aware: users only see mail they already have access to",
        "First-party Workspace connector \u2014 domain-wide via your Workspace customer ID",
    ]
    if with_actions:
        pros.append("Assistant can send, reply and draft email end-to-end inside GE")
    if attachments:
        pros.append("Attachment content is searchable")

    watchouts = [
        "Workspace only \u2014 personal @gmail.com accounts are not supported",
        "Admin must enable Smart features (Workspace + other Google products)",
        "Admin must allowlist the Google-managed OAuth app",
    ]
    if with_actions:
        watchouts.append("Actions require a one-time admin OAuth consent; write actions act as the user")
    if location not in ("us", "eu"):
        watchouts.append(f"Location is '{location}' \u2014 encryption is only configurable for us/eu; "
                         "consider setting residency before connecting Gmail")
    if encryption == "cmek":
        watchouts.append("First-party Gmail largely uses Google-managed keys even under CMEK")

    value = {
        "data_source": "google_mail",
        "scope": scope,
        "location": location,
        "encryption": encryption,
        "entities": entities,
        "actions_enabled": with_actions,
        "actions": action_list,
        "refresh_interval": "0s" if (sync or "").lower() == "continuous" else "86400s",
        "connector_name": "gmail",
    }
    return {
        "area": "connector",
        "title": "Gmail connector \u2192 data store \u201cgmail\u201d",
        "summary": f"Domain-wide Gmail \u00b7 {'messages + attachments' if attachments else 'messages'} \u00b7 "
                   f"{'read + actions' if with_actions else 'read-only'} \u00b7 {location}",
        "value": value,
        "pros": pros,
        "watchouts": watchouts,
        "one_way": False,
        "rationale": "Guided first-party Gmail setup, ACL-aware, consistent with the region/encryption decision",
        "source_url": pb.get("source_url", ""),
        "terraform_resource": "google_discovery_engine_data_connector",
        # prerequisites the agent should confirm are done before saving
        "prerequisites": [
            "Google Workspace (not personal @gmail.com); you have the Workspace customer ID",
            "Smart features ON in Workspace AND in other Google products",
            "Google-managed OAuth app allowlisted by a Workspace admin",
            "Identity provider configured (Google Identity / GSUITE)",
            "For actions: admin ready to complete the one-time OAuth consent",
        ],
    }
