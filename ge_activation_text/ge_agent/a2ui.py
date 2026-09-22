"""A2UI surface builders.

A2UI lets an agent describe UI declaratively as JSON; a trusted client renders it.
For this POC we emit the same surfaceUpdate / dataModelUpdate / beginRendering shape and
render it with the tiny bundled viewer in web/a2ui_demo.html. That viewer supports the
subset used here (Column, Card, Text, MultipleChoice, Button, and a custom RecommendationCard).

In phase 1 these surfaces are sent over A2A to the ADK web renderer / a production A2UI
client instead of a static demo page. The builders below are pure functions so they can
be unit-tested and reused unchanged.
"""
from __future__ import annotations
import json


def discovery_surface(area: str, questions: list[dict]) -> list[dict]:
    """Build a discovery form surface.

    questions: [{"key","label","options":[{"label","value"}], "single":bool}]
    """
    children = ["title"]
    comps = [
        {"id": "root", "component": {"Column": {"children": {"explicitList": children}}}},
        {"id": "title", "component": {"Text": {
            "text": {"literalString": f"{area} \u00b7 a few questions"}, "usageHint": "h2"}}},
    ]
    for i, q in enumerate(questions):
        qid = f"q{i}"
        children.append(qid)
        comps.append({"id": qid, "component": {"MultipleChoice": {
            "label": {"literalString": q["label"]},
            "selections": {"path": f"/answers/{q['key']}"},
            "maxAllowedSelections": 1 if q.get("single", True) else 99,
            "options": [{"label": {"literalString": o["label"]},
                         "value": o["value"]} for o in q["options"]],
        }}})
    children.append("submit")
    comps.append({"id": "submit", "component": {"Button": {"child": "submit_t", "primary": True,
        "action": {"name": "discovery.submit", "context": [
            {"key": "answers", "value": {"path": "/answers"}}]}}}})
    comps.append({"id": "submit_t", "component": {"Text": {"text": {"literalString": "Continue"}}}})
    return [
        {"surfaceUpdate": {"surfaceId": "discovery", "components": comps}},
        {"beginRendering": {"surfaceId": "discovery", "root": "root"}},
    ]


def recommendation_surface(rec: dict) -> list[dict]:
    """Build a recommendation card surface with pros / watch-outs and approve/adjust actions."""
    comps = [
        {"id": "root", "component": {"Column": {"children": {"explicitList": ["card", "actions"]}}}},
        {"id": "card", "component": {"RecommendationCard": {
            "title": {"path": "/rec/title"},
            "summary": {"path": "/rec/summary"},
            "one_way": {"path": "/rec/one_way"},
            "pros": {"path": "/rec/pros"},
            "watchouts": {"path": "/rec/watchouts"},
            "rationale": {"path": "/rec/rationale"},
            "source_url": {"path": "/rec/source_url"}}}},
        {"id": "actions", "component": {"Row": {"children": {"explicitList": ["adjust", "approve"]}}}},
        {"id": "adjust", "component": {"Button": {"child": "adjust_t",
            "action": {"name": "recommendation.adjust", "context": []}}}},
        {"id": "adjust_t", "component": {"Text": {"text": {"literalString": "Adjust"}}}},
        {"id": "approve", "component": {"Button": {"child": "approve_t", "primary": True,
            "action": {"name": "recommendation.approve",
                       "context": [{"key": "area", "value": {"literalString": rec.get("area", "")}}]}}}},
        {"id": "approve_t", "component": {"Text": {"text": {"literalString":
            "Approve (one-way)" if rec.get("one_way") else "Approve & save"}}}},
    ]
    data = {
        "title": rec.get("title", ""), "summary": rec.get("summary", ""),
        "one_way": bool(rec.get("one_way")), "pros": rec.get("pros", []),
        "watchouts": rec.get("watchouts", []), "rationale": rec.get("rationale", ""),
        "source_url": rec.get("source_url", ""),
    }
    return [
        {"surfaceUpdate": {"surfaceId": "recommendation", "components": comps}},
        {"dataModelUpdate": {"surfaceId": "recommendation", "path": "/rec", "contents": data}},
        {"beginRendering": {"surfaceId": "recommendation", "root": "root"}},
    ]


def decision_saved_surface(saved: dict, rec: dict) -> list[dict]:
    comps = [
        {"id": "root", "component": {"Card": {"child": "col"}}},
        {"id": "col", "component": {"Column": {"children": {"explicitList": ["h", "sub", "meta"]}}}},
        {"id": "h", "component": {"Text": {"text": {"literalString": "Saved to the plan sheet"}, "usageHint": "h2"}}},
        {"id": "sub", "component": {"Text": {"text": {"literalString": rec.get("title", "")}}}},
        {"id": "meta", "component": {"Text": {"text": {"literalString":
            f"{saved.get('id')} \u00b7 status: saved \u00b7 ready for the deploy agent"}, "usageHint": "caption"}}},
    ]
    return [
        {"surfaceUpdate": {"surfaceId": "decision", "components": comps}},
        {"beginRendering": {"surfaceId": "decision", "root": "root"}},
    ]


def to_jsonl(surface: list[dict]) -> str:
    return "\n".join(json.dumps(line, ensure_ascii=False) for line in surface)
