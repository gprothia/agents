"""
agent_registry.py
Lists Vertex AI Agent Engines (Reasoning Engines) in a project/location.
"""

from __future__ import annotations
import logging

log = logging.getLogger(__name__)


def list_agent_engines(project_id: str, location: str) -> list[dict]:
    """
    Return a list of Agent Engines as dicts:
        { "id": "123456", "display_name": "my-agent", "resource_name": "projects/.../..." }

    Uses the Vertex AI Python SDK (google-cloud-aiplatform >= 1.60).
    Falls back gracefully if no engines exist or the SDK call fails.
    """
    try:
        import vertexai
        from vertexai import agent_engines  # requires google-cloud-aiplatform >= 1.60

        vertexai.init(project=project_id, location=location)
        engines = agent_engines.list()

        result = []
        for engine in engines:
            resource_name = engine.resource_name  # projects/.../reasoningEngines/123
            engine_id = resource_name.split("/")[-1]
            display_name = getattr(engine, "display_name", engine_id) or engine_id
            result.append({
                "id":            engine_id,
                "display_name":  display_name,
                "resource_name": resource_name,
            })
        return result

    except ImportError:
        # Fallback: use the REST API via google-auth + requests
        return _list_via_rest(project_id, location)
    except Exception as exc:
        log.warning("vertexai.agent_engines.list() failed: %s", exc)
        return _list_via_rest(project_id, location)


def _list_via_rest(project_id: str, location: str) -> list[dict]:
    """REST fallback using google-auth credentials."""
    try:
        import google.auth
        import google.auth.transport.requests
        import requests

        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        authed_session = google.auth.transport.requests.AuthorizedSession(creds)

        url = (
            f"https://{location}-aiplatform.googleapis.com/v1/"
            f"projects/{project_id}/locations/{location}/reasoningEngines"
        )
        resp = authed_session.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        result = []
        for engine in data.get("reasoningEngines", []):
            name = engine.get("name", "")
            engine_id = name.split("/")[-1]
            display_name = engine.get("displayName", engine_id) or engine_id
            result.append({
                "id":            engine_id,
                "display_name":  display_name,
                "resource_name": name,
            })
        return result

    except Exception as exc:
        log.error("REST fallback also failed: %s", exc)
        return []

print(list_agent_engines('bold-kit-384717', 'us-central1') )