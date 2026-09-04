"""Load and search the local grounding playbooks.

For a POC this is deliberately simple: plain-text keyword lookup over a handful of
markdown files. In phase 1 this becomes retrieval over Vertex AI Search / a GE data
store built from the full Gemini Enterprise documentation, refreshed nightly.
"""
from __future__ import annotations
import os
import re
from functools import lru_cache

_pkg_dir = os.path.dirname(__file__)
_parent_dir = os.path.dirname(_pkg_dir)
_possible_dirs = [
    os.path.join(_pkg_dir, "grounding"),
    os.path.join(_parent_dir, "grounding"),
    os.path.join(os.getcwd(), "grounding"),
]
GROUNDING_DIR = next((d for d in _possible_dirs if os.path.isdir(d)), _possible_dirs[0])

# topic -> filename
_TOPIC_FILES = {
    "app_setup": "app_setup.md",
    "region": "region.md",
    "encryption": "encryption_cmek.md",
}


@lru_cache(maxsize=None)
def _read(fname: str) -> str:
    path = os.path.join(GROUNDING_DIR, fname)
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _source_url(text: str) -> str:
    m = re.search(r"source_url:\s*(\S+)", text)
    return m.group(1) if m else ""


def search_playbook(topic: str) -> dict:
    """Return the grounding playbook for a setup topic.

    Args:
      topic: one of "app_setup", "region", "encryption" (case-insensitive; a few
        aliases such as "cmek" or "residency" are also accepted).

    Returns:
      A dict with the matched topic, the full playbook markdown text, and the
      citable source URL. If nothing matches, returns a result with found=False.
    """
    key = (topic or "").strip().lower()
    aliases = {"cmek": "encryption", "encrypt": "encryption",
               "residency": "region", "location": "region",
               "app": "app_setup", "apps": "app_setup"}
    key = aliases.get(key, key)
    fname = _TOPIC_FILES.get(key)
    if not fname:
        return {"found": False, "topic": topic,
                "available_topics": list(_TOPIC_FILES.keys())}
    text = _read(fname)
    return {"found": True, "topic": key, "text": text, "source_url": _source_url(text)}


def list_topics() -> list[str]:
    return list(_TOPIC_FILES.keys())
